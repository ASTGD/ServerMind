"""AI service — command planning, script generation, and output explanation.

The prompts live here; the actual model call is routed through ``llm_service``, which
talks to whichever provider the instance is configured for (Anthropic / OpenAI /
Gemini / OpenAI-compatible) — see Update 20, multi-provider AI.
"""
from __future__ import annotations

import json
import logging
import re

from app.models.server import Server
from app.services import llm_service

logger = logging.getLogger(__name__)


# ── System prompts ────────────────────────────────────────────────────────────

_CHAT_SYSTEM = """\
You are ServerAlly AI, an expert server administrator.
You help non-technical users manage their servers safely using natural language.

SERVER CONTEXT:
- Name: {server_name}
- OS: {os_type} {os_version}
- Platform: {connection_type}
- Shell: {shell}
- Architecture: {arch}

LANGUAGE: Respond in {user_language}. User may write in {user_language}.

RULES:
1. Use the correct shell for the OS — bash for Linux/Unix, PowerShell for Windows
2. For Linux: apt (Ubuntu/Debian), dnf (Fedora/RHEL), yum (CentOS 7)
3. For Windows: winget or chocolatey for packages, Get-Service for services
4. Always check if software is already installed before installing
5. Always include a verification step after installation
6. Never suggest commands that risk data loss without flagging risk_level as 'high'
7. If ambiguous, ask ONE clarifying question before proceeding
8. Keep explanations friendly and jargon-free — user is non-technical
9. Respond entirely in the user's language including technical explanations

ALWAYS RESPOND WITH VALID JSON ONLY (no markdown, no explanation outside JSON):
{{
  "intent_understood": "...",
  "clarification_needed": null,
  "plan_summary": "...",
  "commands": [
    {{
      "cmd": "exact command string",
      "description": "plain language explanation",
      "risk_level": "low | medium | high",
      "requires_confirmation": false
    }}
  ],
  "estimated_duration_seconds": 30,
  "post_execution_message": "...",
  "follow_up_suggestions": ["...", "..."]
}}
"""

_HOSTING_NOTE = """\

HOSTING MODE: This is a managed control-panel account ({panel_type}), not a shell.
You CANNOT run bash/PowerShell commands here. Return an EMPTY "commands" array and
put step-by-step control-panel UI instructions (or the matching ServerAlly panel
action — create site, issue SSL, create database/email) in "plan_summary" and
"post_execution_message" instead. Never output shell commands for hosting accounts.
"""

_FLEET_SYSTEM = """\
You are ServerAlly AI, a friendly assistant for a NON-TECHNICAL user who manages a fleet of servers.
You can see all of the user's servers (below). Help them across their whole fleet.

THE USER'S SERVERS:
{server_list}

LANGUAGE: Respond in {user_language}. The user may write in {user_language}.

WHAT YOU DO HERE (fleet overview):
- Answer questions across servers (which need attention, are low on disk, need updates, etc.).
- Recommend the right playbook or approach for a goal.
- Explain concepts and guide the user through the product (adding servers, backups, security…).
- Help the user decide which server to act on.

IMPORTANT:
- You are in the fleet overview, NOT connected to a shell — do NOT output shell commands to run here.
- To actually run something on a specific server, tell the user to open that server (name it); the
  per-server assistant will run it safely with a preview and approval.
- Be concise, warm, and jargon-free. Use the servers' real names. If the user has no servers, help
  them add their first one.

RESPOND WITH VALID JSON ONLY (no markdown, no text outside JSON):
{{
  "answer": "your reply in plain language (short lines / simple lists are fine)",
  "follow_up_suggestions": ["short suggestion", "short suggestion"]
}}
"""

_EXPLAIN_SYSTEM = """\
You are ServerAlly AI. A user just ran server commands.
Summarize what happened in 2-3 sentences in plain, friendly language.
Respond in {user_language}.
Focus on: what was accomplished, any important output, and what to do next if relevant.
Keep it short and jargon-free. Output plain text only, no JSON.
"""

_SCHEDULE_SYSTEM = """\
Convert a natural language schedule description into a cron expression.

Examples (input → cron):
  "every night at 2am"               → 0 2 * * *
  "every Sunday at midnight"         → 0 0 * * 0
  "every hour"                       → 0 * * * *
  "every 15 minutes"                 → */15 * * * *
  "first day of every month at 3am"  → 0 3 1 * *
  "every weekday at 9am"             → 0 9 * * 1-5
  "twice a day"                      → 0 9,21 * * *
  "every 5 minutes"                  → */5 * * * *
  "every day at noon"                → 0 12 * * *

RESPOND WITH VALID JSON ONLY (no markdown, no text outside JSON):
{{"cron_expression": "...", "human_description": "Plain English of the schedule"}}
"""

_SCRIPT_SYSTEM = """\
You are ServerAlly Script Generator.
Create production-ready scripts for server administration.

Target OS: {os_family}
Shell: {shell}
User language: {user_language}

For bash scripts:
- Start with: #!/bin/bash
- Strict mode: set -euo pipefail
- Use trap for cleanup where appropriate
- Check prerequisites before running
- Clear echo progress messages

For PowerShell scripts:
- Start with: #Requires -Version 5.1
- Set-StrictMode -Version Latest
- $ErrorActionPreference = 'Stop'
- try/catch error handling
- Write-Host for progress messages

For both script types:
- Header comment: title, description, author: ServerAlly AI
- User-configurable variables section at the top with comments
- Inline comments on non-obvious steps
- Meaningful success/failure messages
- Success summary at the end

RESPOND WITH VALID JSON ONLY (no markdown fences, no text outside JSON):
{{
  "title": "Short descriptive title",
  "description": "One sentence description",
  "script_type": "bash or powershell",
  "estimated_runtime_seconds": 30,
  "variables": [
    {{"name": "VAR_NAME", "label": "Human-readable label", "default": "default_value", "required": true}}
  ],
  "script": "full script content",
  "post_run_instructions": "What to do after running, or empty string",
  "warnings": []
}}
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_json(raw: str) -> str:
    """Strip markdown code fences if present."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
    return raw.strip()


# ── Public API ────────────────────────────────────────────────────────────────

async def plan_commands(
    user_input: str,
    server: Server,
    user_language: str = "en",
) -> dict:
    """Ask Claude to produce a command plan for the user's request."""
    system = _CHAT_SYSTEM.format(
        server_name=server.name,
        os_type=server.os_type or "linux",
        os_version=server.os_version or "",
        connection_type=server.connection_type,
        shell=server.shell,
        arch=server.arch or "unknown",
        user_language=user_language,
    )
    if server.connection_type == "hosting":
        system += _HOSTING_NOTE.format(panel_type=server.panel_type or "control panel")

    raw = _extract_json(await llm_service.complete(system, user_input, max_tokens=2048))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("AI plan JSON parse error: %s\nRaw: %r", exc, raw[:500])
        raise ValueError(f"AI returned invalid JSON: {exc}") from exc


async def fleet_chat(user_input: str, servers: list[Server], user_language: str = "en") -> dict:
    """Fleet-wide advisory chat — answers across all the user's servers (read-only, no
    command execution). Returns {"answer": str, "follow_up_suggestions": list[str]}."""
    if servers:
        lines = []
        for s in servers:
            os_ = f"{s.os_type or 'unknown'}{(' ' + s.os_version) if s.os_version else ''}"
            lines.append(
                f"- {s.name} — {os_}, {s.connection_type}, status: {s.status or 'unknown'} ({s.host})"
            )
        server_list = "\n".join(lines)
    else:
        server_list = "(no servers connected yet)"

    system = _FLEET_SYSTEM.format(server_list=server_list, user_language=user_language)
    raw = _extract_json(await llm_service.complete(system, user_input, max_tokens=1024))
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # Advisory answers are free-form — fall back to the raw text rather than erroring.
        return {"answer": raw, "follow_up_suggestions": []}
    return data


async def explain_output(
    plan_summary: str,
    output: str,
    user_language: str = "en",
) -> str:
    """Generate a plain-language explanation of the command output."""
    system = _EXPLAIN_SYSTEM.format(user_language=user_language)
    prompt = f"Plan: {plan_summary}\n\nOutput:\n{output[:3000]}"

    return (await llm_service.complete(system, prompt, max_tokens=512)).strip()


async def parse_schedule(human_input: str) -> dict:
    """Convert natural language schedule description to a cron expression via Claude."""
    raw = _extract_json(await llm_service.complete(_SCHEDULE_SYSTEM, human_input, max_tokens=128))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("AI schedule JSON parse error: %s\nRaw: %r", exc, raw[:200])
        raise ValueError(f"AI returned invalid JSON: {exc}") from exc


async def generate_script(
    request: str,
    os_family: str = "linux",
    user_language: str = "en",
) -> dict:
    """Ask Claude to generate a complete server administration script."""
    shell = "powershell" if os_family == "windows" else "bash"
    system = _SCRIPT_SYSTEM.format(
        os_family=os_family,
        shell=shell,
        user_language=user_language,
    )

    raw = _extract_json(await llm_service.complete(system, request, max_tokens=4096))
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("AI script JSON parse error: %s\nRaw: %r", exc, raw[:500])
        raise ValueError(f"AI returned invalid JSON: {exc}") from exc

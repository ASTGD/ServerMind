"""AI service — Claude API integration for command planning and output explanation."""
from __future__ import annotations

import json
import logging
import re

from anthropic import AsyncAnthropic

from app.config import settings
from app.models.server import Server

logger = logging.getLogger(__name__)

_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


# ── System prompts ────────────────────────────────────────────────────────────

_CHAT_SYSTEM = """\
You are ServerMind AI, an expert server administrator.
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

_EXPLAIN_SYSTEM = """\
You are ServerMind AI. A user just ran server commands.
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
You are ServerMind Script Generator.
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
- Header comment: title, description, author: ServerMind AI
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

    message = await _get_client().messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=2048,
        system=system,
        messages=[{"role": "user", "content": user_input}],
    )

    raw = _extract_json(message.content[0].text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("AI plan JSON parse error: %s\nRaw: %r", exc, raw[:500])
        raise ValueError(f"AI returned invalid JSON: {exc}") from exc


async def explain_output(
    plan_summary: str,
    output: str,
    user_language: str = "en",
) -> str:
    """Generate a plain-language explanation of the command output."""
    system = _EXPLAIN_SYSTEM.format(user_language=user_language)
    prompt = f"Plan: {plan_summary}\n\nOutput:\n{output[:3000]}"

    message = await _get_client().messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=512,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


async def parse_schedule(human_input: str) -> dict:
    """Convert natural language schedule description to a cron expression via Claude."""
    message = await _get_client().messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=128,
        system=_SCHEDULE_SYSTEM,
        messages=[{"role": "user", "content": human_input}],
    )
    raw = _extract_json(message.content[0].text)
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

    message = await _get_client().messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": request}],
    )

    raw = _extract_json(message.content[0].text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("AI script JSON parse error: %s\nRaw: %r", exc, raw[:500])
        raise ValueError(f"AI returned invalid JSON: {exc}") from exc

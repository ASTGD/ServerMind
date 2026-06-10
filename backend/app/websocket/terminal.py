"""WebSocket handlers — interactive terminal and AI chat with streaming execution."""
from __future__ import annotations

import asyncio
import json
import logging
import socket as _socket
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import paramiko
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.command_log import CommandLog
from app.models.playbook import Playbook, PlaybookRun, UserScript
from app.models.server import Server
from app.models.user import User
from app.services import ai_service, connection_manager, safety_service
from app.services import ssh_service, team_service
from app.services.playbook_service import substitute_variables
from app.services.auth_service import decode_token

logger = logging.getLogger(__name__)
router = APIRouter()

_pty_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="pty")


# ── Auth helper ───────────────────────────────────────────────────────────────

async def _auth_and_get_server(
    token: str, server_id: str, *, need_execute: bool = False
) -> Server | None:
    """Decode JWT and return the server the user may access.

    Resolves ownership *or* team access. When ``need_execute`` is set, the user
    must have execute permission (owners/admins/operators-with-grant) — viewers
    are rejected (CLAUDE.md security rule 7).
    """
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    user_id = payload.get("sub")

    async with AsyncSessionLocal() as db:
        try:
            uid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return None
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if user is None:
            return None
        access = await team_service.get_access(db, user, server_id)
        if access is None:
            return None
        if need_execute and not access.can_execute:
            return None
        return access.server


# ── Terminal WebSocket ────────────────────────────────────────────────────────

def _read_channel(channel: paramiko.Channel) -> bytes | None:
    """Blocking read from a Paramiko channel. Returns None on close."""
    channel.settimeout(0.3)
    try:
        data = channel.recv(4096)
        return data if data else None
    except _socket.timeout:
        # No data within timeout; channel still open
        return b""
    except Exception:
        return None


@router.websocket("/ws/terminal/{server_id}")
async def terminal_ws(
    websocket: WebSocket,
    server_id: str,
    token: str = Query(default=""),
) -> None:
    """Bidirectional interactive terminal over WebSocket."""
    server = await _auth_and_get_server(token, server_id, need_execute=True)
    if not server:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Interactive PTY shells are SSH-only. WinRM/hosting have no PTY — those
    # users should use the AI Chat tab (which streams command execution).
    if server.connection_type != "ssh":
        await websocket.accept()
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "Interactive terminal is only available for SSH servers. "
                       "Use the AI Chat tab to run commands on this server.",
        }))
        await websocket.close()
        return

    await websocket.accept()

    try:
        channel = await ssh_service.open_shell(
            str(server.id), server.host, server.port,
            server.username, server.auth_type, server.encrypted_cred,
        )
    except Exception as exc:
        await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        await websocket.close()
        return

    loop = asyncio.get_event_loop()

    async def _ssh_to_ws() -> None:
        """Read SSH output and forward to WebSocket."""
        while True:
            data = await loop.run_in_executor(_pty_executor, lambda: _read_channel(channel))
            if data is None:
                break
            if data:
                await websocket.send_bytes(data)

    async def _ws_to_ssh() -> None:
        """Read WebSocket messages and forward to SSH channel."""
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "input":
                payload = msg.get("data", "")
                await loop.run_in_executor(
                    _pty_executor,
                    lambda p=payload: channel.sendall(p.encode("utf-8", errors="replace")),
                )
            elif msg.get("type") == "resize":
                cols = int(msg.get("cols", 80))
                rows = int(msg.get("rows", 24))
                await loop.run_in_executor(
                    _pty_executor,
                    lambda c=cols, r=rows: channel.resize_pty(width=c, height=r),
                )

    tasks = [
        asyncio.ensure_future(_ssh_to_ws()),
        asyncio.ensure_future(_ws_to_ssh()),
    ]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
    except WebSocketDisconnect:
        for t in tasks:
            t.cancel()
    except Exception as exc:
        logger.warning("Terminal WS error for server %s: %s", server_id, exc)
        for t in tasks:
            t.cancel()
    finally:
        try:
            channel.close()
        except Exception:
            pass


# ── Chat WebSocket ────────────────────────────────────────────────────────────

@router.websocket("/ws/chat/{server_id}")
async def chat_ws(
    websocket: WebSocket,
    server_id: str,
    token: str = Query(default=""),
) -> None:
    """AI chat with streaming command execution."""
    server = await _auth_and_get_server(token, server_id, need_execute=True)
    if not server:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()

    try:
        await _chat_loop(websocket, server)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("Chat WS error for server %s", server_id)
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass


async def _chat_loop(ws: WebSocket, server: Server) -> None:
    """Main chat loop — processes user messages until disconnect."""
    os_family = "windows" if server.connection_type == "winrm" else "linux"

    while True:
        raw = await ws.receive_text()
        msg = json.loads(raw)

        if msg.get("type") != "message":
            continue

        user_input: str = msg.get("content", "").strip()
        user_language: str = msg.get("language", "en")
        if not user_input:
            continue

        await _handle_message(ws, server, user_input, user_language, os_family)


async def _handle_message(
    ws: WebSocket,
    server: Server,
    user_input: str,
    user_language: str,
    os_family: str,
) -> None:
    """Plan, validate, execute and explain one user message."""
    # ── 1. AI planning ────────────────────────────────────────────────────────
    await ws.send_text(json.dumps({"type": "thinking"}))

    try:
        plan = await ai_service.plan_commands(user_input, server, user_language)
    except Exception as exc:
        await ws.send_text(json.dumps({"type": "error", "message": f"AI error: {exc}"}))
        return

    # If AI needs clarification, return early
    if plan.get("clarification_needed"):
        await ws.send_text(json.dumps({
            "type": "clarification",
            "message": plan["clarification_needed"],
        }))
        return

    commands: list[dict] = plan.get("commands", [])

    # ── 2. Safety check ───────────────────────────────────────────────────────
    safety = safety_service.validate_plan(commands, os_family)
    if safety.status == "blocked":
        log = await _save_log(server, user_input, user_language, plan, "", "blocked")
        await ws.send_text(json.dumps({
            "type": "blocked",
            "log_id": str(log.id),
            "reason": safety.reason,
            "pattern": safety.pattern,
        }))
        return

    requires_approval = (
        safety.status == "confirm"
        or any(c.get("requires_confirmation") for c in commands)
    )
    risk_level = safety_service.highest_risk(commands)

    # ── 3. Send plan ──────────────────────────────────────────────────────────
    await ws.send_text(json.dumps({
        "type": "plan",
        "plan_summary": plan.get("plan_summary", ""),
        "commands": commands,
        "requires_approval": requires_approval,
        "risk_level": risk_level,
        "estimated_duration_seconds": plan.get("estimated_duration_seconds", 30),
    }))

    # ── 4. Wait for approval if required ─────────────────────────────────────
    if requires_approval:
        approval_event = asyncio.Event()
        approved = {"value": False}

        raw = await ws.receive_text()
        decision = json.loads(raw)
        if decision.get("type") == "approve":
            approved["value"] = True
        else:
            log = await _save_log(server, user_input, user_language, plan, "", "cancelled")
            await ws.send_text(json.dumps({"type": "cancelled", "log_id": str(log.id)}))
            return

    # ── 5. Execute commands ───────────────────────────────────────────────────
    full_output: list[str] = []
    t0 = time.monotonic()
    overall_status = "success"

    for idx, cmd_item in enumerate(commands):
        cmd = cmd_item.get("cmd", "")
        await ws.send_text(json.dumps({
            "type": "command_start",
            "index": idx,
            "total": len(commands),
            "cmd": cmd,
            "description": cmd_item.get("description", ""),
        }))

        cmd_output: list[str] = []
        cmd_t0 = time.monotonic()
        exit_code = 0

        try:
            stream = await connection_manager.execute_stream(server, cmd)
            async for line in stream:
                cmd_output.append(line)
                full_output.append(line)
                await ws.send_text(json.dumps({
                    "type": "output",
                    "data": line + "\n",
                    "stream": "stdout",
                }))
        except Exception as exc:
            error_line = f"ERROR: {exc}"
            cmd_output.append(error_line)
            full_output.append(error_line)
            await ws.send_text(json.dumps({
                "type": "output",
                "data": error_line + "\n",
                "stream": "stderr",
            }))
            exit_code = 1
            overall_status = "failed"

        duration_ms = int((time.monotonic() - cmd_t0) * 1000)
        await ws.send_text(json.dumps({
            "type": "command_done",
            "index": idx,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
        }))

        if exit_code != 0 and overall_status != "failed":
            overall_status = "partial"

    # ── 6. Explain output ─────────────────────────────────────────────────────
    execution_ms = int((time.monotonic() - t0) * 1000)
    raw_output = "\n".join(full_output)

    try:
        explanation = await ai_service.explain_output(
            plan.get("plan_summary", ""),
            raw_output,
            user_language,
        )
    except Exception:
        explanation = plan.get("post_execution_message", "Commands completed.")

    # ── 7. Save to DB ─────────────────────────────────────────────────────────
    log = await _save_log(
        server, user_input, user_language, plan, raw_output, overall_status,
        execution_ms=execution_ms,
    )

    await ws.send_text(json.dumps({
        "type": "execution_complete",
        "log_id": str(log.id),
        "status": overall_status,
        "explanation": explanation,
        "follow_up_suggestions": plan.get("follow_up_suggestions", []),
    }))


# ── DB helper ─────────────────────────────────────────────────────────────────

async def _save_log(
    server: Server,
    user_input: str,
    user_language: str,
    plan: dict,
    output: str,
    status: str,
    execution_ms: int | None = None,
) -> CommandLog:
    """Persist a command log entry."""
    commands = plan.get("commands", [])
    risk_level = safety_service.highest_risk(commands) if commands else "low"

    async with AsyncSessionLocal() as db:
        log = CommandLog(
            server_id=server.id,
            user_id=server.user_id,
            user_input=user_input,
            user_language=user_language,
            ai_plan=plan,
            commands=commands,
            output=output or None,
            status=status,
            ai_explanation=plan.get("post_execution_message"),
            risk_level=risk_level,
            execution_ms=execution_ms,
        )
        db.add(log)
        await db.commit()
        await db.refresh(log)
        return log


# ── Playbook Run WebSocket ─────────────────────────────────────────────────────

@router.websocket("/ws/playbook-run/{server_id}")
async def playbook_run_ws(
    websocket: WebSocket,
    server_id: str,
    token: str = Query(default=""),
) -> None:
    """Stream playbook script execution over WebSocket."""
    server = await _auth_and_get_server(token, server_id, need_execute=True)
    if not server:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()

    try:
        raw = await websocket.receive_text()
        msg = json.loads(raw)
        if msg.get("type") != "run":
            await websocket.send_text(json.dumps({"type": "error", "message": "Expected run message"}))
            await websocket.close()
            return

        playbook_id_str = msg.get("playbook_id")
        user_script_id_str = msg.get("user_script_id")
        variables: dict = msg.get("variables") or {}

        async with AsyncSessionLocal() as db:
            script: str | None = None
            run_title: str = "Script"
            playbook_id_val: uuid.UUID | None = None
            user_script_id_val: uuid.UUID | None = None

            if playbook_id_str:
                try:
                    pid = uuid.UUID(playbook_id_str)
                except ValueError:
                    pid = None
                if pid:
                    result = await db.execute(select(Playbook).where(Playbook.id == pid))
                    playbook = result.scalar_one_or_none()
                    if playbook:
                        playbook_id_val = playbook.id
                        run_title = playbook.title
                        if server.connection_type == "winrm" and playbook.script_powershell:
                            script = playbook.script_powershell
                        elif playbook.script_bash:
                            script = playbook.script_bash

            elif user_script_id_str:
                try:
                    usid = uuid.UUID(user_script_id_str)
                except ValueError:
                    usid = None
                if usid:
                    result = await db.execute(
                        select(UserScript).where(
                            UserScript.id == usid,
                            UserScript.user_id == server.user_id,
                        )
                    )
                    user_script = result.scalar_one_or_none()
                    if user_script:
                        user_script_id_val = user_script.id
                        run_title = user_script.title
                        script = user_script.script_content

            if not script:
                await websocket.send_text(json.dumps({"type": "error", "message": "Script not found or no compatible script for this OS"}))
                await websocket.close()
                return

            script = substitute_variables(script, variables)

            # Create run record
            run = PlaybookRun(
                server_id=server.id,
                user_id=server.user_id,
                playbook_id=playbook_id_val,
                user_script_id=user_script_id_val,
                variables_used=variables,
                status="running",
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)

        await websocket.send_text(json.dumps({
            "type": "started",
            "run_id": str(run.id),
            "title": run_title,
        }))

        # Execute script and stream output
        output_lines: list[str] = []
        overall_status = "success"
        t0 = time.monotonic()

        try:
            stream = await connection_manager.execute_stream(server, script)
            async for line in stream:
                output_lines.append(line)
                await websocket.send_text(json.dumps({
                    "type": "output",
                    "data": line + "\n",
                }))
        except Exception as exc:
            error_line = f"ERROR: {exc}"
            output_lines.append(error_line)
            overall_status = "failed"
            await websocket.send_text(json.dumps({
                "type": "output",
                "data": error_line + "\n",
            }))

        execution_ms = int((time.monotonic() - t0) * 1000)
        full_output = "\n".join(output_lines)

        # Update run record
        async with AsyncSessionLocal() as db:
            from sqlalchemy import update as sa_update
            from datetime import datetime, timezone
            await db.execute(
                sa_update(PlaybookRun)
                .where(PlaybookRun.id == run.id)
                .values(
                    status=overall_status,
                    output=full_output,
                    completed_at=datetime.now(timezone.utc),
                )
            )
            # Increment run_count only for official playbooks
            if playbook_id_val:
                await db.execute(
                    sa_update(Playbook)
                    .where(Playbook.id == playbook_id_val)
                    .values(run_count=Playbook.run_count + 1)
                )
            await db.commit()

        await websocket.send_text(json.dumps({
            "type": "complete",
            "run_id": str(run.id),
            "status": overall_status,
            "execution_ms": execution_ms,
        }))

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("Playbook run WS error for server %s", server_id)
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass

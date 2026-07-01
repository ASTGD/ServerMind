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

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.command_log import CommandLog
from app.models.playbook import Playbook, PlaybookRun, UserScript
from app.models.server import Server
from app.models.user import User
from app.services import ai_service, connection_manager, safety_service
from app.services import ssh_service, team_service
from app.services.rate_limit_service import check_command_rate
from app.services.redis_service import get_redis
from app.services.playbook_service import substitute_variables
from app.workers.playbook_tasks import run_chat_task, run_log_key, run_playbook_task
from app.services.ssh_service import STALL_NOTE, CommandError, CommandStalled
from app.services.auth_service import decode_token

logger = logging.getLogger(__name__)


# Worker-availability probe (Risk 2 — graceful fallback). Cached briefly so we
# don't ping the broker on every run start.
_worker_probe: dict[str, object] = {"ts": -999.0, "ok": False}
_WORKER_PROBE_TTL = 10.0


async def _worker_available() -> bool:
    """True if at least one Celery worker responds to a ping. Lets the durable
    (celery) execution path fall back to inline when no worker is running, instead
    of enqueuing a task nothing will process (which would hang the run)."""
    now = time.monotonic()
    if now - float(_worker_probe["ts"]) < _WORKER_PROBE_TTL:
        return bool(_worker_probe["ok"])
    try:
        from app.celery_app import celery
        replies = await asyncio.to_thread(celery.control.ping, timeout=0.5)
        ok = bool(replies)
    except Exception:  # noqa: BLE001 — broker down / any error ⇒ treat as no worker
        ok = False
    _worker_probe["ts"] = now
    _worker_probe["ok"] = ok
    return ok
router = APIRouter()

_pty_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="pty")


# ── Auth helper ───────────────────────────────────────────────────────────────

async def _auth_and_get_server(
    token: str, ticket: str, server_id: str, *, need_execute: bool = False
) -> tuple[User, Server] | None:
    """Authenticate a WebSocket and return (user, server) the user may access.

    Prefers a single-use Redis ``ticket`` (keeps the JWT out of the URL); falls
    back to a JWT ``token`` in the query string (deprecated). Resolves ownership
    *or* team access. When ``need_execute`` is set the user must have execute
    permission — viewers are rejected (CLAUDE.md rule 7).
    """
    via_ticket = bool(ticket)
    token_tv = 0
    if via_ticket:
        try:
            user_id = await get_redis().getdel(f"ws_ticket:{ticket}")
        except Exception:  # noqa: BLE001 — no Redis ⇒ can't validate a ticket
            user_id = None
    else:
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        token_tv = payload.get("tv", 0)

    if not user_id:
        return None

    async with AsyncSessionLocal() as db:
        try:
            uid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return None
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if user is None or not user.is_active:
            return None
        if not via_ticket and token_tv != user.token_version:
            return None
        if need_execute and settings.REQUIRE_EMAIL_VERIFICATION and not user.is_verified:
            return None
        access = await team_service.get_access(db, user, server_id)
        if access is None:
            return None
        if need_execute and not access.can_execute:
            return None
        return user, access.server


async def _auth_user(token: str, ticket: str) -> User | None:
    """Authenticate a WebSocket to a user (no server scope) — for the fleet assistant."""
    via_ticket = bool(ticket)
    token_tv = 0
    if via_ticket:
        try:
            user_id = await get_redis().getdel(f"ws_ticket:{ticket}")
        except Exception:  # noqa: BLE001
            user_id = None
    else:
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            return None
        user_id = payload.get("sub")
        token_tv = payload.get("tv", 0)
    if not user_id:
        return None
    async with AsyncSessionLocal() as db:
        try:
            uid = uuid.UUID(user_id)
        except (ValueError, TypeError):
            return None
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if user is None or not user.is_active:
            return None
        if not via_ticket and token_tv != user.token_version:
            return None
        return user


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
    ticket: str = Query(default=""),
) -> None:
    """Bidirectional interactive terminal over WebSocket."""
    auth = await _auth_and_get_server(token, ticket, server_id, need_execute=True)
    if not auth:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    _user, server = auth

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
    ticket: str = Query(default=""),
) -> None:
    """AI chat with streaming command execution."""
    auth = await _auth_and_get_server(token, ticket, server_id, need_execute=True)
    if not auth:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    user, server = auth
    await websocket.accept()

    try:
        await _chat_loop(websocket, server, str(user.id))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("Chat WS error for server %s", server_id)
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass


async def _chat_loop(ws: WebSocket, server: Server, user_id: str) -> None:
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

        if not await check_command_rate(user_id, str(server.id)):
            await ws.send_text(json.dumps({
                "type": "error",
                "message": "Rate limit reached — wait a minute before sending more commands.",
            }))
            continue

        await _handle_message(ws, server, user_input, user_language, os_family)


# ── Fleet chat WebSocket (global assistant, advisory) ─────────────────────────

@router.websocket("/ws/chat")
async def fleet_chat_ws(
    websocket: WebSocket,
    token: str = Query(default=""),
    ticket: str = Query(default=""),
) -> None:
    """Fleet-wide AI assistant — advisory chat across all of the user's servers.

    Not scoped to one server and does NOT execute commands: it answers questions,
    recommends playbooks, and guides the user. Actual execution stays in the
    per-server assistant (``/ws/chat/{server_id}``) where safety + approval live.
    """
    user = await _auth_user(token, ticket)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await websocket.accept()
    try:
        await _fleet_loop(websocket, user)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.exception("Fleet chat WS error")
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass


def _resolve_handoff(handoff: object, servers: list[Server]) -> dict | None:
    """Match the AI's suggested server name to a real server the user owns.

    Returns {server_id, server_name, prompt} the frontend can act on, or None if the
    name doesn't match a server (so we never hand off to something that isn't there)."""
    if not isinstance(handoff, dict):
        return None
    name = str(handoff.get("server", "")).strip().lower()
    prompt = str(handoff.get("prompt", "")).strip()
    if not name or not prompt:
        return None
    match = next((s for s in servers if s.name.strip().lower() == name), None)
    if match is None:
        match = next(
            (s for s in servers if name in s.name.strip().lower() or s.name.strip().lower() in name),
            None,
        )
    if match is None:
        return None
    return {"server_id": str(match.id), "server_name": match.name, "prompt": prompt}


async def _fleet_loop(ws: WebSocket, user: User) -> None:
    while True:
        raw = await ws.receive_text()
        msg = json.loads(raw)
        if msg.get("type") != "message":
            continue
        text = msg.get("content", "").strip()
        lang = msg.get("language", "en")
        if not text:
            continue

        await ws.send_text(json.dumps({"type": "thinking"}))
        async with AsyncSessionLocal() as db:
            servers = await team_service.accessible_servers(db, user)
        try:
            data = await ai_service.fleet_chat(text, servers, lang)
        except Exception as exc:  # noqa: BLE001
            await ws.send_text(json.dumps({"type": "error", "message": f"AI error: {exc}"}))
            continue
        await ws.send_text(json.dumps({
            "type": "answer",
            "content": data.get("answer", ""),
            "suggestions": data.get("follow_up_suggestions", []),
            "handoff": _resolve_handoff(data.get("handoff"), servers),
        }))


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

    # ── 5. Execute ────────────────────────────────────────────────────────────
    # Durable worker path (when a Celery worker is up): create the log up front (so
    # it has an id to stream and cancel against), enqueue the worker, and tail its
    # log — survives client disconnects (Update 15, slice 4). If the flag is on but
    # no worker responds, fall back to inline so the run never hangs (Risk 2).
    use_celery = settings.EXECUTION_BACKEND == "celery" and await _worker_available()
    if settings.EXECUTION_BACKEND == "celery" and not use_celery:
        logger.warning("EXECUTION_BACKEND=celery but no worker responded — running chat inline")
    if use_celery:
        async with AsyncSessionLocal() as db:
            log = CommandLog(
                server_id=server.id,
                user_id=server.user_id,
                user_input=user_input,
                user_language=user_language,
                ai_plan=plan,
                commands=commands,
                status="running",
                risk_level=risk_level,
            )
            db.add(log)
            await db.commit()
            await db.refresh(log)
        # Tell the client the run's id up front so it can offer a Stop button.
        await ws.send_text(json.dumps({"type": "run_started", "log_id": str(log.id)}))
        run_chat_task.delay(str(log.id), str(server.id), commands, plan, user_language)
        await _stream_chat_log(ws, str(log.id))
        return

    # Inline path (default) — execute in this process.
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
        except CommandStalled as exc:
            if exc.last_output:
                cmd_output.append(exc.last_output)
                full_output.append(exc.last_output)
                await ws.send_text(json.dumps({
                    "type": "output", "data": exc.last_output + "\n", "stream": "stdout",
                }))
            full_output.append(STALL_NOTE)
            await ws.send_text(json.dumps({"type": "output", "data": STALL_NOTE + "\n", "stream": "stdout"}))
            exit_code = 1
            overall_status = "stalled"
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

        if exit_code != 0 and overall_status not in ("failed", "stalled"):
            overall_status = "partial"
        if overall_status == "stalled":
            break

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

_RUN_POLL_INTERVAL = 0.4
_RUN_MAX_POLLS = 9000  # ~60 min safety bound


_TERMINAL_RUN_STATUSES = ("success", "failed", "partial", "cancelled", "blocked", "stalled")


async def _tail_log(
    websocket: WebSocket,
    run_id: str,
    terminal_types: tuple[str, ...],
    finished,
) -> None:
    """Replay + live-tail run:{run_id}:log to the client until a terminal message.

    Uniform for fresh runs and reconnects (replay from the start of the buffered
    log, then follow live appends). ``finished(run_id)`` is consulted when the log
    is empty/expired: it returns ``None`` (run not found), or ``(replay_output,
    terminal_msg)`` — a non-None ``terminal_msg`` means the run already ended, so
    replay any stored output then send that message."""
    key = run_log_key(run_id)
    r = get_redis()
    cursor = 0
    sent_any = False
    idle = 0
    for _ in range(_RUN_MAX_POLLS):
        items = await r.lrange(key, cursor, -1)
        if items:
            cursor += len(items)
            sent_any = True
            idle = 0
            for raw in items:
                await websocket.send_text(raw)
                try:
                    if json.loads(raw).get("type") in terminal_types:
                        return
                except (ValueError, TypeError):
                    pass
        else:
            idle += 1
            # Every ~2s with no new entries, check whether the run already finished
            # (log expired, or the worker died without a final message).
            if idle % 5 == 0:
                fb = await finished(run_id)
                if fb is None:
                    await websocket.send_text(json.dumps({"type": "error", "message": "Run not found"}))
                    return
                replay_output, terminal_msg = fb
                if terminal_msg is not None:
                    if not sent_any and replay_output:
                        await websocket.send_text(json.dumps({"type": "output", "data": replay_output + "\n"}))
                    await websocket.send_text(json.dumps(terminal_msg))
                    return
        await asyncio.sleep(_RUN_POLL_INTERVAL)
    await websocket.send_text(json.dumps({"type": "error", "message": "Run stream timed out"}))


async def _playbook_finished(run_id: str):
    async with AsyncSessionLocal() as db:
        run = (
            await db.execute(select(PlaybookRun).where(PlaybookRun.id == uuid.UUID(run_id)))
        ).scalar_one_or_none()
    if run is None:
        return None
    if run.status in _TERMINAL_RUN_STATUSES:
        return run.output, {"type": "complete", "run_id": run_id, "status": run.status}
    return None, None


async def _chat_finished(run_id: str):
    async with AsyncSessionLocal() as db:
        log = (
            await db.execute(select(CommandLog).where(CommandLog.id == uuid.UUID(run_id)))
        ).scalar_one_or_none()
    if log is None:
        return None
    if log.status in _TERMINAL_RUN_STATUSES:
        return log.output, {
            "type": "execution_complete", "log_id": run_id, "status": log.status,
            "explanation": log.ai_explanation or "",
            "follow_up_suggestions": (log.ai_plan or {}).get("follow_up_suggestions", []),
        }
    return None, None


async def _stream_run_log(websocket: WebSocket, run_id: str) -> None:
    """Tail a playbook run's log until ``complete`` (or the DB shows it finished)."""
    await _tail_log(websocket, run_id, ("complete",), _playbook_finished)


async def _stream_chat_log(websocket: WebSocket, log_id: str) -> None:
    """Tail an AI-chat run's log until ``execution_complete`` (or DB-finished)."""
    await _tail_log(websocket, log_id, ("execution_complete",), _chat_finished)


async def _relay_celery_run(
    websocket: WebSocket, run_id: str, server_id: str, script: str
) -> None:
    """Enqueue the durable worker task, then tail its output log to the client.
    The worker keeps running even if the client drops (Update 15)."""
    run_playbook_task.delay(run_id, server_id, script)
    await _stream_run_log(websocket, run_id)


async def _attach_run(websocket: WebSocket, server: Server, run_id: str | None) -> None:
    """Reconnect to an existing run on the same server and resume its stream."""
    if not run_id:
        await websocket.send_text(json.dumps({"type": "error", "message": "Missing run_id"}))
        return
    try:
        rid = uuid.UUID(run_id)
    except (ValueError, TypeError):
        await websocket.send_text(json.dumps({"type": "error", "message": "Invalid run_id"}))
        return
    async with AsyncSessionLocal() as db:
        run = (await db.execute(select(PlaybookRun).where(PlaybookRun.id == rid))).scalar_one_or_none()
    if run is None or str(run.server_id) != str(server.id):
        await websocket.send_text(json.dumps({"type": "error", "message": "Run not found"}))
        return
    await websocket.send_text(json.dumps({"type": "started", "run_id": run_id, "title": "Reconnected"}))
    await _stream_run_log(websocket, run_id)


@router.websocket("/ws/playbook-run/{server_id}")
async def playbook_run_ws(
    websocket: WebSocket,
    server_id: str,
    token: str = Query(default=""),
    ticket: str = Query(default=""),
) -> None:
    """Stream playbook script execution over WebSocket."""
    auth = await _auth_and_get_server(token, ticket, server_id, need_execute=True)
    if not auth:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    user, server = auth
    await websocket.accept()
    if not await check_command_rate(str(user.id), str(server.id)):
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": "Rate limit reached — wait a minute before running more.",
        }))
        await websocket.close()
        return

    try:
        raw = await websocket.receive_text()
        msg = json.loads(raw)
        mtype = msg.get("type")
        if mtype == "attach":
            await _attach_run(websocket, server, msg.get("run_id"))
            return
        if mtype != "run":
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

            # OS guard (Update 21): refuse a playbook built for another OS family.
            from app.services.playbook_service import infer_supported_os, os_matches
            _supported = infer_supported_os(script)
            if not os_matches(server, _supported):
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": (
                        f"This playbook is built for {', '.join(_supported or [])} — "
                        f"{server.name} runs {server.os_type or 'an unknown OS'}. Use a matching server."
                    ),
                }))
                await websocket.close()
                return

            # Guard against a duplicate: if this same playbook/script is already
            # running on this server, attach to that run instead of starting another.
            dup_q = select(PlaybookRun.id).where(
                PlaybookRun.server_id == server.id, PlaybookRun.status == "running",
            )
            dup_q = (
                dup_q.where(PlaybookRun.playbook_id == playbook_id_val)
                if playbook_id_val is not None
                else dup_q.where(PlaybookRun.user_script_id == user_script_id_val)
            )
            existing_id = (
                await db.execute(dup_q.order_by(PlaybookRun.started_at.desc()))
            ).scalars().first()

            if existing_id is None:
                # Create run record (secret-named inputs encrypted at rest)
                from app.services.secret_vars import encrypt_variables
                run = PlaybookRun(
                    server_id=server.id,
                    user_id=server.user_id,
                    playbook_id=playbook_id_val,
                    user_script_id=user_script_id_val,
                    variables_used=encrypt_variables(variables),
                    status="running",
                )
                db.add(run)
                await db.commit()
                await db.refresh(run)

        if existing_id is not None:
            await websocket.send_text(json.dumps({
                "type": "output",
                "data": "ℹ This playbook is already running on this server — attaching to it.\n",
            }))
            await _attach_run(websocket, server, str(existing_id))
            return

        await websocket.send_text(json.dumps({
            "type": "started",
            "run_id": str(run.id),
            "title": run_title,
        }))

        if settings.EXECUTION_BACKEND == "celery":
            if await _worker_available():
                await _relay_celery_run(websocket, str(run.id), str(server.id), script)
                return
            logger.warning("EXECUTION_BACKEND=celery but no worker responded — running playbook inline")

        # Execute script and stream output
        output_lines: list[str] = []
        overall_status = "success"
        t0 = time.monotonic()

        cancel_key = f"run:{run.id}:cancel"
        try:
            stream = await connection_manager.execute_stream(server, script)
            async for line in stream:
                if await get_redis().exists(cancel_key):
                    overall_status = "cancelled"
                    await websocket.send_text(json.dumps({"type": "output", "data": "⏹ Cancelled by user\n"}))
                    break
                output_lines.append(line)
                await websocket.send_text(json.dumps({
                    "type": "output",
                    "data": line + "\n",
                }))
        except CommandStalled as exc:
            overall_status = "stalled"
            if exc.last_output:
                output_lines.append(exc.last_output)
                await websocket.send_text(json.dumps({"type": "output", "data": exc.last_output + "\n"}))
            output_lines.append(STALL_NOTE)
            await websocket.send_text(json.dumps({"type": "output", "data": STALL_NOTE + "\n"}))
        except CommandError:
            overall_status = "failed"  # the script's own output already explains the failure
        except Exception as exc:
            error_line = f"ERROR: {exc}"
            output_lines.append(error_line)
            overall_status = "failed"
            await websocket.send_text(json.dumps({
                "type": "output",
                "data": error_line + "\n",
            }))

        await get_redis().delete(cancel_key)
        execution_ms = int((time.monotonic() - t0) * 1000)
        full_output = "\n".join(output_lines)

        # Update run record — capture a short failure reason for inline display.
        from app.services.playbook_service import extract_failure_reason
        failure_reason = (
            extract_failure_reason(output_lines)
            if overall_status in ("failed", "stalled") else None
        )
        async with AsyncSessionLocal() as db:
            from sqlalchemy import update as sa_update
            from datetime import datetime, timezone
            await db.execute(
                sa_update(PlaybookRun)
                .where(PlaybookRun.id == run.id)
                .values(
                    status=overall_status,
                    output=full_output,
                    failure_reason=failure_reason,
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

        async with AsyncSessionLocal() as db:
            from app.services.notification_service import create_run_notification
            await create_run_notification(db, run.id)

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

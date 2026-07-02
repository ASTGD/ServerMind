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
from app.services import ai_context_service, ai_service, connection_manager, safety_service
from app.services import memory_service, metering_service, skill_service, ssh_service
from app.services import team_service, terminal_session_service
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


async def _auth_user(token: str, ticket: str, *, need_verified: bool = False) -> User | None:
    """Authenticate a WebSocket to a user (no server scope) — for the fleet assistant.

    ``need_verified`` mirrors the per-server execution gate (``_auth_and_get_server``):
    when set and email verification is required, an unverified user is rejected.
    """
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
        if need_verified and settings.REQUIRE_EMAIL_VERIFICATION and not user.is_verified:
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
    sid: str = Query(default=""),
) -> None:
    """Bidirectional interactive terminal over WebSocket.

    Backed by a persistent session (terminal_session_service): the shell survives a
    WebSocket drop, so a client reconnecting with the same ``sid`` re-attaches to the
    same shell and gets its buffered scrollback replayed."""
    auth = await _auth_and_get_server(token, ticket, server_id, need_execute=True)
    if not auth:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    user, server = auth

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

    # One persistent shell per (user, server, sid). Reconnecting with the same sid
    # re-attaches instead of opening a fresh login.
    key = f"{user.id}:{server.id}:{sid or 'default'}"

    async def _opener() -> paramiko.Channel:
        return await ssh_service.open_shell(
            str(server.id), server.host, server.port,
            server.username, server.auth_type, server.encrypted_cred,
        )

    try:
        session, _is_new = await terminal_session_service.get_or_create(key, _opener)
    except Exception as exc:
        await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        await websocket.close()
        return

    snap, q = terminal_session_service.attach(session)
    # Reset the client screen, then replay the authoritative scrollback — reconstructs
    # the view on reconnect; a harmless no-op on a fresh terminal.
    try:
        await websocket.send_text(json.dumps({"type": "reset"}))
        if snap:
            await websocket.send_bytes(snap)
    except Exception:
        terminal_session_service.detach(session, q)
        return

    closed_by_client = False

    async def _pump_out() -> None:
        while True:
            await websocket.send_bytes(await q.get())

    async def _pump_in() -> None:
        nonlocal closed_by_client
        while True:
            msg = json.loads(await websocket.receive_text())
            mtype = msg.get("type")
            if mtype == "input":
                await terminal_session_service.write(session, msg.get("data", ""))
            elif mtype == "resize":
                await terminal_session_service.resize(
                    session, int(msg.get("cols", 80)), int(msg.get("rows", 24))
                )
            elif mtype == "close":
                closed_by_client = True
                return

    tasks = [asyncio.ensure_future(_pump_out()), asyncio.ensure_future(_pump_in())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("Terminal WS error for server %s: %s", server_id, exc)
    finally:
        for t in tasks:
            t.cancel()
        if closed_by_client:
            terminal_session_service.close(session)      # tab closed → end the shell now
        else:
            terminal_session_service.detach(session, q)  # network drop → keep alive to reconnect


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


def _page_context_from(msg: dict) -> str | None:
    """Pull the optional 'what page the user is looking at' hint off a chat message.

    App-supplied and untrusted, so we only accept a plain string; the AI layer frames it
    as background info (never instructions) and caps its length.
    """
    val = msg.get("page_context")
    if not isinstance(val, str):
        return None
    val = val.strip()
    return val or None


def _history_from(msg: dict) -> list[dict] | None:
    """Pull the optional recent-chat-turns list off a chat message (conversation memory).

    Client-supplied and untrusted: only well-formed {"role","content"} string pairs
    survive, capped to the last 8 turns; the AI layer caps lengths again and frames the
    turns as context (never instructions to act on).
    """
    val = msg.get("history")
    if not isinstance(val, list):
        return None
    turns: list[dict] = []
    for item in val:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue
        content = content.strip()
        if content:
            turns.append({"role": role, "content": content})
    return turns[-8:] or None


async def _maybe_generate_script(spec: object, user_language: str) -> dict | None:
    """If Ally emitted a script-generation request, produce the script and return it for the
    client. This only WRITES a script (text); it is never executed. Returns None if there's
    no valid request or generation fails.
    """
    if not isinstance(spec, dict):
        return None
    request = spec.get("request")
    if not isinstance(request, str) or not request.strip():
        return None
    os_family = spec.get("os_family") or "linux"
    if os_family not in ("linux", "windows", "both"):
        os_family = "linux"
    try:
        return await ai_service.generate_script(request.strip(), os_family, user_language)
    except Exception as exc:  # noqa: BLE001
        logger.warning("fleet script generation failed: %s", exc)
        return None


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
        page_context = _page_context_from(msg)
        history = _history_from(msg)
        if not user_input:
            continue

        if not await check_command_rate(user_id, str(server.id)):
            await ws.send_text(json.dumps({
                "type": "error",
                "message": "Rate limit reached — wait a minute before sending more commands.",
            }))
            continue

        # AI quota gate (docs/AI-METERING.md §4) — per-server chat draws from the
        # server OWNER's pool (§8 team pooling). The wall only blocks when
        # ENFORCE_AI_QUOTA is on; otherwise this is a no-op numbers check.
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, server.user_id)
                g = await metering_service.gate(db, owner) if owner else None
        except Exception as exc:  # noqa: BLE001 — gate failure must not kill chat
            logger.warning("quota gate failed for server %s: %s", server.id, exc)
            g = None
        if g and not g.allowed:
            await ws.send_text(json.dumps({
                "type": "quota_exceeded",
                "used": g.used, "limit": g.limit, "resets_at": g.resets_at,
                "message": metering_service.quota_message(g),
            }))
            continue

        await _handle_message(
            ws, server, user_input, user_language, os_family, page_context, history,
            acting_user_id=user_id,
        )


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


def _resolve_batch(batch: object, servers: list[Server]) -> dict | None:
    """Match the AI's suggested server names (a multi-server action) to real owned
    servers → {prompt, targets:[{server_id, server_name}]}, deduped. None if nothing matches."""
    if not isinstance(batch, dict):
        return None
    names = batch.get("servers")
    prompt = str(batch.get("prompt", "")).strip()
    if not prompt or not isinstance(names, list) or not names:
        return None
    by_name = {s.name.strip().lower(): s for s in servers}
    targets: list[dict] = []
    seen: set = set()
    for n in names:
        key = str(n).strip().lower()
        s = by_name.get(key)
        if s is None:
            s = next(
                (sv for sv in servers if key and (key in sv.name.strip().lower() or sv.name.strip().lower() in key)),
                None,
            )
        if s is not None and s.id not in seen:
            seen.add(s.id)
            targets.append({"server_id": str(s.id), "server_name": s.name})
    if not targets:
        return None
    return {"prompt": prompt, "targets": targets}


async def _fleet_loop(ws: WebSocket, user: User) -> None:
    while True:
        raw = await ws.receive_text()
        msg = json.loads(raw)
        if msg.get("type") != "message":
            continue
        text = msg.get("content", "").strip()
        lang = msg.get("language", "en")
        page_context = _page_context_from(msg)
        history = _history_from(msg)
        if not text:
            continue

        # AI quota gate (docs/AI-METERING.md §4) — fleet chat draws from the acting
        # user's own pool. Only blocks when ENFORCE_AI_QUOTA is on.
        try:
            async with AsyncSessionLocal() as db:
                g = await metering_service.gate(db, user)
        except Exception as exc:  # noqa: BLE001 — gate failure must not kill chat
            logger.warning("quota gate failed (fleet): %s", exc)
            g = None
        if g and not g.allowed:
            await ws.send_text(json.dumps({
                "type": "quota_exceeded",
                "used": g.used, "limit": g.limit, "resets_at": g.resets_at,
                "message": metering_service.quota_message(g),
            }))
            continue

        await ws.send_text(json.dumps({"type": "thinking"}))
        async with AsyncSessionLocal() as db:
            servers = await team_service.accessible_servers(db, user)
            # Ally Brain Phase 4 — real health numbers per server, so "which server
            # needs attention?" is answered with data. Phase 5 — what Ally remembers
            # about this user. Best-effort: never blocks chat.
            health = None
            memories = None
            try:
                health = await ai_context_service.build_fleet_health(db, servers)
                memories = await memory_service.block_for_user(db, user.id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("fleet context build failed: %s", exc)
        # Meter the whole fleet turn (answer + any inline script generation) = 1 action.
        tok = metering_service.start_collection()
        try:
            data = await ai_service.fleet_chat(
                text, servers, lang, page_context=page_context, history=history,
                health=health, memories=memories,
            )
        except Exception as exc:  # noqa: BLE001
            calls = metering_service.finish_collection(tok)
            if calls:  # tokens may have been spent before our error — ledger at 0 actions
                async with AsyncSessionLocal() as db:
                    await metering_service.record(
                        db, user_id=user.id, feature="fleet_chat", calls=calls,
                        actions=0, status="provider_error",
                    )
            await ws.send_text(json.dumps({"type": "error", "message": f"AI error: {exc}"}))
            continue
        # Ally Brain Phase 5 — save a user-scoped note when Ally marked one.
        if data.get("remember"):
            async with AsyncSessionLocal() as db:
                await memory_service.save_from_ai(
                    db, user_id=user.id, remember=data.get("remember"), server_id=None,
                )
        # If Ally decided the user wants a reusable script written, generate it now and
        # attach it — the frontend shows it with "Save to My Scripts" / "Open in editor".
        # This only WRITES a script (text); it is never executed here.
        generated = await _maybe_generate_script(data.get("script"), lang)
        calls = metering_service.finish_collection(tok)
        if calls:
            async with AsyncSessionLocal() as db:
                await metering_service.record(
                    db, user_id=user.id, feature="fleet_chat", calls=calls,
                )
        await ws.send_text(json.dumps({
            "type": "answer",
            "content": data.get("answer", ""),
            "suggestions": data.get("follow_up_suggestions", []),
            "handoff": _resolve_handoff(data.get("handoff"), servers),
            "batch": _resolve_batch(data.get("batch"), servers),
            "script": generated,
        }))


# ── Batch WebSocket (cross-server actions, Phase 3) ───────────────────────────

_BATCH_MAX = 25


async def _run_on_server(server: Server, prompt: str, lang: str) -> tuple[str, str]:
    """Plan + safety + execute one prompt on one server (inline). Returns (status,
    explanation). Reuses the per-server pipeline; hard-blocked commands are refused."""
    os_family = "windows" if server.connection_type == "winrm" else "linux"
    try:
        plan = await ai_service.plan_commands(prompt, server, lang)
    except Exception as exc:  # noqa: BLE001
        return "failed", f"Couldn't plan this action: {exc}"
    if plan.get("clarification_needed"):
        return "skipped", str(plan["clarification_needed"])
    commands = plan.get("commands", [])
    if not commands:
        return "skipped", plan.get("plan_summary") or "Nothing to run on this server."

    safety = safety_service.validate_plan(commands, os_family)
    if safety.status == "blocked":
        await _save_log(server, prompt, lang, plan, "", "blocked")
        return "blocked", safety.reason or "Blocked by the safety policy."

    full_output: list[str] = []
    status = "success"
    for cmd_item in commands:
        cmd = cmd_item.get("cmd", "")
        try:
            stream = await connection_manager.execute_stream(server, cmd)
            async for line in stream:
                full_output.append(line)
        except CommandStalled as exc:
            if exc.last_output:
                full_output.append(exc.last_output)
            full_output.append(STALL_NOTE)
            status = "stalled"
            break
        except Exception as exc:  # noqa: BLE001
            full_output.append(f"ERROR: {exc}")
            status = "failed"

    raw = "\n".join(full_output)
    try:
        explanation = await ai_service.explain_output(plan.get("plan_summary", ""), raw, lang)
    except Exception:  # noqa: BLE001
        explanation = plan.get("post_execution_message") or plan.get("plan_summary") or "Done."
    await _save_log(server, prompt, lang, plan, raw, status)
    return status, explanation


@router.websocket("/ws/batch")
async def batch_ws(
    websocket: WebSocket,
    token: str = Query(default=""),
    ticket: str = Query(default=""),
) -> None:
    """Run one action across several servers — each through the per-server pipeline
    (plan + safety + execute). Approval is the user's explicit 'run' on a reviewed set."""
    user = await _auth_user(token, ticket, need_verified=True)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await websocket.accept()
    try:
        await _batch_run(websocket, user)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.exception("Batch WS error")
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass


async def _batch_run(ws: WebSocket, user: User) -> None:
    raw = await ws.receive_text()
    msg = json.loads(raw)
    if msg.get("type") != "run":
        return
    server_ids = [str(s) for s in (msg.get("server_ids") or [])][:_BATCH_MAX]
    prompt = str(msg.get("prompt", "")).strip()
    lang = msg.get("language", "en")
    if not prompt or not server_ids:
        await ws.send_text(json.dumps({"type": "error", "message": "Nothing to run."}))
        return

    # AI quota gate (docs/AI-METERING.md §2) — a batch costs 1 action PER server, from
    # the acting user's pool. Checked once up front; only blocks when enforcement is on.
    try:
        async with AsyncSessionLocal() as db:
            g = await metering_service.gate(db, user)
    except Exception as exc:  # noqa: BLE001
        logger.warning("quota gate failed (batch): %s", exc)
        g = None
    if g and g.enforced and g.used + len(server_ids) > g.limit:
        await ws.send_text(json.dumps({
            "type": "quota_exceeded",
            "used": g.used, "limit": g.limit, "resets_at": g.resets_at,
            "message": (
                f"This batch needs {len(server_ids)} actions but you have "
                f"{max(0, g.limit - g.used)} left this month. "
                f"Your allowance resets on {g.resets_at}."
            ),
        }))
        return

    counts: dict[str, int] = {}
    for sid in server_ids:
        async with AsyncSessionLocal() as db:
            access = await team_service.get_access(db, user, sid)
        if access is None or not access.can_execute:
            counts["blocked"] = counts.get("blocked", 0) + 1
            await ws.send_text(json.dumps({
                "type": "server_done", "server_id": sid, "server_name": "(no access)",
                "status": "blocked", "explanation": "You don't have execute access to this server.",
            }))
            continue
        server = access.server
        await ws.send_text(json.dumps({
            "type": "server_start", "server_id": sid, "server_name": server.name,
        }))
        if not await check_command_rate(str(user.id), sid):
            counts["failed"] = counts.get("failed", 0) + 1
            await ws.send_text(json.dumps({
                "type": "server_done", "server_id": sid, "server_name": server.name,
                "status": "failed", "explanation": "Rate limit reached for this server — try again shortly.",
            }))
            continue
        # Meter this server's model calls — 1 action per target server (§2).
        tok = metering_service.start_collection()
        status, explanation = await _run_on_server(server, prompt, lang)
        calls = metering_service.finish_collection(tok)
        if calls:
            async with AsyncSessionLocal() as db:
                await metering_service.record(
                    db, user_id=user.id, feature="batch", calls=calls, server_id=server.id,
                )
        counts[status] = counts.get(status, 0) + 1
        await ws.send_text(json.dumps({
            "type": "server_done", "server_id": sid, "server_name": server.name,
            "status": status, "explanation": explanation,
        }))

    await ws.send_text(json.dumps({"type": "batch_complete", "counts": counts}))


async def _handle_message(
    ws: WebSocket,
    server: Server,
    user_input: str,
    user_language: str,
    os_family: str,
    page_context: str | None = None,
    history: list[dict] | None = None,
    acting_user_id: str | None = None,
) -> None:
    """Metered wrapper (docs/AI-METERING.md) — collects every model call made for this
    one user message (plan → execute → explain = 1 action) and writes the ledger,
    billed to the server owner's pool. Metering never blocks the message itself.

    Also matches an Ally Skill (Phase A): a deterministic trigger match picks the
    expert procedure for this kind of task; the slug is tagged on the ledger rows."""
    skill = skill_service.match(user_input, server.os_type)
    if skill:
        logger.info("ally skill matched: %s (server=%s)", skill.slug, server.id)
    tok = metering_service.start_collection()
    try:
        await _handle_message_inner(
            ws, server, user_input, user_language, os_family, page_context, history,
            acting_user_id=acting_user_id, skill=skill,
        )
    finally:
        calls = metering_service.finish_collection(tok)
        if calls:
            async with AsyncSessionLocal() as db:
                await metering_service.record(
                    db, user_id=server.user_id, feature="chat",
                    calls=calls, server_id=server.id,
                    skill=skill.slug if skill else None,
                )


async def _handle_message_inner(
    ws: WebSocket,
    server: Server,
    user_input: str,
    user_language: str,
    os_family: str,
    page_context: str | None = None,
    history: list[dict] | None = None,
    acting_user_id: str | None = None,
    skill: skill_service.Skill | None = None,
) -> None:
    """Plan, validate, execute and explain one user message."""
    # ── 1. AI planning ────────────────────────────────────────────────────────
    await ws.send_text(json.dumps({"type": "thinking"}))

    # Ally Brain Phase 3 — attach what ServerAlly already knows about this server
    # (metrics, security grade, installs, recent activity), and Phase 5 — what Ally
    # remembers (server notes + the acting user's preferences). Best-effort: a
    # context failure must never block the chat itself.
    server_profile = None
    memories = None
    try:
        async with AsyncSessionLocal() as db:
            server_profile = await ai_context_service.build_server_profile(db, server)
            memories = await memory_service.block_for_server(
                db, server.id, acting_user_id or server.user_id
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat context build failed for %s: %s", server.id, exc)

    try:
        plan = await ai_service.plan_commands(
            user_input, server, user_language, page_context, history,
            server_profile=server_profile, memories=memories, skill=skill,
        )
    except Exception as exc:
        await ws.send_text(json.dumps({"type": "error", "message": f"AI error: {exc}"}))
        return

    # Ally Brain Phase 5 — if Ally decided this turn is worth remembering, save the
    # note (server-scoped; preferences go user-scoped). Secret-filtered, best-effort.
    if plan.get("remember"):
        async with AsyncSessionLocal() as db:
            await memory_service.save_from_ai(
                db,
                user_id=acting_user_id or server.user_id,
                remember=plan.get("remember"),
                server_id=server.id,
            )

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

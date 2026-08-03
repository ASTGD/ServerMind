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
from app.services import ai_context_service, ai_service, connection_manager, llm_service, safety_service
from app.services import file_service, live_look_service, memory_service, metering_service, scout_service, skill_service
from app.services import mission_service, runbook_service
from app.websocket import mission_runner
from app.services import ssh_service, team_service, terminal_session_service
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
            expected_fingerprint=server.fingerprint,
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
    """AI chat locked to one server (the ServerDetail chat tab / older clients).
    Same loop as the unified socket, with a fixed target."""
    auth = await _auth_and_get_server(token, ticket, server_id, need_execute=True)
    if not auth:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    user, server = auth
    await websocket.accept()

    try:
        await _unified_loop(websocket, user, fixed_server=server)
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
    for attempt in (1, 2):  # one retry — a single malformed reply shouldn't lose the script
        try:
            return await ai_service.generate_script(request.strip(), os_family, user_language)
        except Exception as exc:  # noqa: BLE001
            logger.warning("fleet script generation failed (attempt %d): %s", attempt, exc)
    return None


async def _resolve_execute_target(user: User, server_id: object) -> Server | str | None:
    """Resolve a per-message server target on the unified socket.

    Returns the Server when the user may EXECUTE on it, a plain-English error string
    when they may not (Rule 7: viewers never execute; email verification honored),
    or None when no target was given (fleet scope)."""
    if not server_id or not isinstance(server_id, str):
        return None
    if settings.REQUIRE_EMAIL_VERIFICATION and not user.is_verified:
        return "Please verify your email before running commands on a server."
    async with AsyncSessionLocal() as db:
        access = await team_service.get_access(db, user, server_id)
    if access is None:
        return "You don't have access to that server."
    if not access.can_execute:
        return "You don't have permission to run commands on that server."
    return access.server


async def _unified_loop(ws: WebSocket, user: User, fixed_server: Server | None = None) -> None:
    """ONE Ally socket ("one Ally, one thread" Stage 2) — fleet questions and
    server-scoped work on the same connection. Each ``message``/``mission_start``
    may carry a ``server_id``; access is resolved PER MESSAGE, so a pending plan or
    a running mission stays bound server-side to the server it was made for, no
    matter what the client switches to. ``fixed_server`` pins the target (the
    per-server endpoint) and per-message ids are ignored there."""
    hub = _MissionHub(ws)
    pending_frame: dict | None = None
    try:
        while True:
            if pending_frame is not None:
                msg, pending_frame = pending_frame, None
            else:
                msg = json.loads(await ws.receive_text())
            mtype = msg.get("type")

            # Control frames for a RUNNING mission (Pass 2: several may stream at once
            # as workspace cards) — routed by mission_id, never blocking the chat loop.
            if _MissionHub.is_control(msg):
                hub.route(msg)
                continue

            # Ally Missions — the user clicked Start on a mission offer. The home server
            # is optional: a fleet-offered mission may span several servers.
            if mtype == "mission_start":
                home: Server | None = fixed_server
                if home is None:
                    resolved = await _resolve_execute_target(user, msg.get("server_id"))
                    if isinstance(resolved, str):
                        await ws.send_text(json.dumps({"type": "error", "message": resolved}))
                        continue
                    home = resolved
                # Phase 4: run DETACHED — a background task pumped to this client. If
                # the client leaves, the task keeps running. Attach (subscribe) BEFORE
                # the task can yield so the first events can't be missed.
                runner = mission_runner.create()
                runner.model = llm_service.manual_model(msg.get("model"))  # Ally model picker
                hub.attach(runner)
                runner.task = asyncio.create_task(_run_mission_detached(
                    runner, user, home_server=home, goal=str(msg.get("goal", "")),
                    skill_slug=msg.get("skill"), user_language=msg.get("language", "en"),
                ))
                continue

            # Resume an interrupted mission from its saved transcript (Phase 3), detached.
            if mtype == "mission_resume":
                mid = msg.get("mission_id")
                async with AsyncSessionLocal() as db:
                    m = await mission_service.get_for_user(db, user, str(mid)) if mid else None
                if m is None:
                    await ws.send_text(json.dumps({"type": "error", "message": "Mission not found."}))
                    continue
                if m.status != "interrupted":
                    await ws.send_text(json.dumps({
                        "type": "error", "message": "This mission isn't resumable (it already finished)."}))
                    continue
                home = None
                if m.server_id is not None:
                    resolved = await _resolve_execute_target(user, str(m.server_id))
                    if isinstance(resolved, str):
                        await ws.send_text(json.dumps({"type": "error", "message": resolved}))
                        continue
                    home = resolved
                runner = mission_runner.create()
                runner.model = llm_service.manual_model(msg.get("model"))  # Ally model picker
                hub.attach(runner)
                runner.task = asyncio.create_task(_run_mission_detached(
                    runner, user, home_server=home, goal=m.goal, skill_slug=m.skill_slug,
                    user_language=msg.get("language", "en"),
                    resume={"mission_id": m.id, "steps": mission_service.steps_of(m)},
                ))
                continue

            # Attach to a mission running in the background (Phase 4) — reconnect + watch.
            if mtype == "mission_attach":
                mid = str(msg.get("mission_id") or "")
                async with AsyncSessionLocal() as db:
                    m = await mission_service.get_for_user(db, user, mid) if mid else None
                if m is None:
                    await ws.send_text(json.dumps({"type": "error", "message": "Mission not found."}))
                    continue
                runner = mission_runner.get(mid)
                if runner is not None and not runner.done:
                    # Still running here: replay current state, re-show any pending
                    # approval prompt (so a client attaching mid-approval can act),
                    # then pump live events alongside everything else.
                    await _replay_mission_to(ws, m)
                    if runner.awaiting_decision and runner.pending_approval:
                        await ws.send_text(json.dumps(
                            {**runner.pending_approval, "mission_id": runner.mission_id}))
                    hub.attach(runner)
                elif m.status == "interrupted":
                    await ws.send_text(json.dumps({
                        "type": "error", "message": "This mission was interrupted — use Resume."}))
                else:
                    # Already finished — show its final state.
                    await _replay_mission_to(ws, m)
                    await ws.send_text(json.dumps({
                        "type": "mission_complete" if m.status == "complete"
                        else "mission_blocked" if m.status == "blocked"
                        else "mission_failed" if m.status == "failed" else "mission_stopped",
                        "mission_id": str(m.id),
                        "summary": m.summary or "Mission finished.",
                        "verified": m.verified, "steps_used": m.steps_used,
                        "reason": m.summary or "", "caveat": m.summary or "",
                        "result": mission_service.result_of(m),
                    }))
                continue

            if mtype != "message":
                continue

            user_input: str = msg.get("content", "").strip()
            user_language: str = msg.get("language", "en")
            page_context = _page_context_from(msg)
            history = _history_from(msg)
            if not user_input:
                continue

            server = fixed_server
            if server is None:
                resolved = await _resolve_execute_target(user, msg.get("server_id"))
                if isinstance(resolved, str):
                    await ws.send_text(json.dumps({"type": "error", "message": resolved}))
                    continue
                server = resolved

            # No target → the fleet path (advisory; may offer handoffs, batches, missions).
            if server is None:
                await _fleet_answer(ws, user, user_input, user_language, page_context, history)
                continue

            if not await check_command_rate(str(user.id), str(server.id)):
                await ws.send_text(json.dumps({
                    "type": "error",
                    "message": "Rate limit reached — wait a minute before sending more commands.",
                }))
                continue

            # AI quota gate (docs/AI-METERING.md §4) — per-server chat draws from the
            # server OWNER's pool (§8 team pooling). The wall only blocks when
            # ENFORCE_PLAN_LIMITS is on; otherwise this is a no-op numbers check.
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

            os_family = "windows" if server.connection_type == "winrm" else "linux"
            # Ally's model picker (Auto/Manual): a pinned choice ('fast'/'smart'/'expert'/
            # 'genius') overrides the ladder for THIS message's planning; None → Auto.
            pinned_model = llm_service.manual_model(msg.get("model"))
            pending_frame = await _handle_message(
                ws, server, user_input, user_language, os_family, page_context, history,
                acting_user_id=str(user.id), mission_control=hub, model=pinned_model,
            )
    finally:
        # Client gone (or loop error): stop pumping. Missions keep running detached.
        hub.close()


# ── Fleet chat WebSocket (global assistant, advisory) ─────────────────────────

@router.websocket("/ws/chat")
async def fleet_chat_ws(
    websocket: WebSocket,
    token: str = Query(default=""),
    ticket: str = Query(default=""),
) -> None:
    """THE Ally socket — one connection for the whole conversation.

    Messages without a ``server_id`` take the fleet path (advisory: answers,
    handoffs, batches, mission offers). Messages WITH a ``server_id`` run the full
    per-server pipeline (plan → safety → approval → execute), with access resolved
    per message — so one continuous chat can act on different servers in turn."""
    user = await _auth_user(token, ticket)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    await websocket.accept()
    try:
        await _unified_loop(websocket, user)
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unified chat WS error")
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass


def _match_server_by_name(name: object, servers: list[Server]) -> Server | None:
    """Resolve ONE server from an AI-provided name. Exact (case-insensitive) match wins;
    a substring match is used ONLY when it is UNAMBIGUOUS (exactly one server). An
    ambiguous name — e.g. 'prod-db' when both 'prod-db' and 'prod-db-replica' exist —
    returns None rather than guessing, because an action on the wrong server is never
    acceptable (the red-team's bidirectional-substring collision)."""
    key = str(name or "").strip().lower()
    if not key:
        return None
    exact = next((s for s in servers if s.name.strip().lower() == key), None)
    if exact is not None:
        return exact
    fuzzy = [s for s in servers if key in s.name.strip().lower() or s.name.strip().lower() in key]
    return fuzzy[0] if len(fuzzy) == 1 else None


def _resolve_handoff(handoff: object, servers: list[Server]) -> dict | None:
    """Match the AI's suggested server name to a real server the user owns.

    Returns {server_id, server_name, prompt} the frontend can act on, or None if the
    name doesn't match a server (so we never hand off to something that isn't there)."""
    if not isinstance(handoff, dict):
        return None
    prompt = str(handoff.get("prompt", "")).strip()
    if not prompt:
        return None
    match = _match_server_by_name(handoff.get("server"), servers)
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
    targets: list[dict] = []
    seen: set = set()
    for n in names:
        s = _match_server_by_name(n, servers)
        if s is not None and s.id not in seen:
            seen.add(s.id)
            targets.append({"server_id": str(s.id), "server_name": s.name})
    if not targets:
        return None
    return {"prompt": prompt, "targets": targets}


def _resolve_mission_offer(mission: object, servers: list[Server]) -> dict | None:
    """Validate a fleet mission offer from the AI: a goal plus an optional home server
    (matched by name, like handoffs). Returns {goal, server_id|None, server_name|None}."""
    if not isinstance(mission, dict):
        return None
    goal = str(mission.get("goal", "")).strip()
    if not goal:
        return None
    match = _match_server_by_name(mission.get("server"), servers) if mission.get("server") else None
    return {
        "goal": goal[:500],
        "server_id": str(match.id) if match else None,
        "server_name": match.name if match else None,
    }


def _clean_options(options: object) -> list[str]:
    """Sanitize AI-supplied clarification options into short, tappable answer strings
    (proactivity Track C). Keeps at most 4, drops blanks/dupes, caps length — so a
    malformed or runaway list can never bloat the frame or the UI."""
    if not isinstance(options, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for o in options:
        text = str(o).strip()
        if not text:
            continue
        text = text[:120]
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= 4:
            break
    return out


def _resolve_ask_servers(names: object, servers: list[Server]) -> list[dict]:
    """Map the AI's candidate server NAMES → real owned servers as {id, name} chips for
    a "which server did you mean?" clarification. Deduped, capped, real matches only (a
    name that isn't one of the user's servers is dropped, so a click always targets a
    server they can actually reach)."""
    if not isinstance(names, list) or not names:
        return []
    out: list[dict] = []
    seen: set = set()
    for n in names:
        s = _match_server_by_name(n, servers)
        if s is not None and s.id not in seen:
            seen.add(s.id)
            out.append({"id": str(s.id), "name": s.name})
        if len(out) >= 6:
            break
    return out


async def _fleet_answer(
    ws: WebSocket,
    user: User,
    text: str,
    lang: str,
    page_context: str | None,
    history: list[dict] | None,
) -> None:
    """One fleet-scoped turn (no server target): advisory answer that may carry a
    handoff, a batch, a generated script, or a mission OFFER."""
    # AI quota gate (docs/AI-METERING.md §4) — fleet chat draws from the acting
    # user's own pool. Only blocks when ENFORCE_PLAN_LIMITS is on.
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
        return

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
        return
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

    # "Which server do you mean?" — when the ask needs a specific server and Ally can't
    # tell which, it clarifies with clickable candidate chips (the frontend sets focus +
    # retries on click). Only real, reachable servers become chips.
    ask = _resolve_ask_servers(data.get("ask_servers"), servers)
    if ask:
        await ws.send_text(json.dumps({
            "type": "clarification",
            "message": data.get("answer") or "Which server do you mean?",
            "ask_servers": ask,
        }))
        return

    # A multi-step job → offer a mission (Stage 2: may span several servers; the
    # user starts it with one click and the mission loop takes over).
    mission = _resolve_mission_offer(data.get("mission"), servers)
    if mission:
        await ws.send_text(json.dumps({
            "type": "mission_offer",
            "goal": mission["goal"],
            "skill": None,
            "server_id": mission["server_id"],
            "server_name": mission["server_name"],
            "message": data.get("answer", ""),
        }))
        return

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
    # The batch path is fire-and-forget across many servers — it has NO per-server
    # approval prompt, so anything the safety policy flags for CONFIRMATION (a recursive
    # delete, a remote-code-execute, a data-file wipe, …) must NOT auto-run here. Refuse
    # it and point the user at the per-server assistant, which runs it with a preview +
    # approval. (Without this, confirm-level commands ran unattended on every box.)
    if safety.status == "confirm":
        await _save_log(server, prompt, lang, plan, "", "blocked")
        return "blocked", (
            "This action needs your approval before it runs, so I didn't run it in a "
            "batch. Open this server directly and I'll do it with a preview and your OK."
        )
    # A step the AI itself flagged high-risk / requires_confirmation is likewise not for
    # the unattended batch path.
    if any(c.get("requires_confirmation") or c.get("risk_level") == "high" for c in commands):
        await _save_log(server, prompt, lang, plan, "", "blocked")
        return "blocked", (
            "This looked risky, so I didn't run it unattended across servers. Open this "
            "server directly and I'll walk you through it with a preview and approval."
        )

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


# ── Ally Missions (docs/ALLY-MISSIONS.md) ─────────────────────────────────────

_MISSION_BUDGET = skill_service.MISSION_BUDGET_DEFAULT  # default; a mission-mode skill may raise it
_MISSION_TAIL_CHARS = 1200
_MISSION_ROSTER_MAX = 15

# A `wait` step lets a mission poll a long-running background job (an install, a
# service coming up) WITHOUT burning the step budget — but bounded so a mission can
# never hang: ≤5 min per wait, ≤1 h and ≤60 waits total across the whole mission.
_WAIT_MAX_SECONDS = 300
_WAIT_TOTAL_MAX = 3600
_WAIT_MAX_STEPS = 60


def _wait_plan(seconds_raw: object, wait_step_count: int, total_wait: int) -> tuple[bool, int]:
    """(allowed, clamped_seconds) for a wait step. Clamps the ask to [1, 5 min] and
    refuses once the per-mission wait budget (step count or total seconds) is spent.
    Pure + testable — the actual sleep/stream stays in the loop."""
    try:
        seconds = int(seconds_raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        seconds = 0
    seconds = max(1, min(_WAIT_MAX_SECONDS, seconds))
    allowed = (wait_step_count + 1) <= _WAIT_MAX_STEPS and (total_wait + seconds) <= _WAIT_TOTAL_MAX
    return allowed, seconds


class _MissionHub:
    """The missions THIS connection is watching (Pass 2 — concurrent workspace cards).

    Replaces the old blocking bridge: each started/resumed/attached mission gets a
    small pump task that forwards the runner's events to the socket, so N missions
    stream live while the main loop keeps handling chat. Mission-control frames
    (approve / reject / mission_stop) are routed by ``mission_id`` — and ONLY to
    runners attached through this hub's access-checked paths, never the global
    registry, so a frame can't reach another user's mission."""

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws
        self._runners: list[mission_runner.MissionRunner] = []
        self._pumps: set[asyncio.Task] = set()
        # Sends can now overlap (pumps + the main loop); a message-level lock keeps
        # the new concurrent path defensive regardless of the ASGI ws backend.
        self._send_lock = asyncio.Lock()

    def attach(self, runner: mission_runner.MissionRunner) -> None:
        """Subscribe + start pumping a runner's events to this client. Subscribing is
        synchronous (before the mission task ever yields) so the first events — e.g.
        ``mission_started`` — can't be missed."""
        if runner in self._runners:
            return
        q = runner.subscribe()
        self._runners.append(runner)

        async def _pump() -> None:
            try:
                while True:
                    event = await q.get()
                    if event is mission_runner.ENDED:
                        return
                    async with self._send_lock:
                        await self._ws.send_text(json.dumps(event))
            except Exception:  # socket gone — the main loop's receive notices; just stop
                pass

        t = asyncio.create_task(_pump())
        self._pumps.add(t)

        def _done(_t: asyncio.Task) -> None:
            # Runs even if the pump was cancelled before it ever started — the
            # subscription must never outlive the pump (unsubscribe is idempotent).
            runner.unsubscribe(q)
            self._pumps.discard(_t)

        t.add_done_callback(_done)

    def _find(self, mission_id: object) -> mission_runner.MissionRunner | None:
        mid = str(mission_id or "").strip()
        live = [r for r in self._runners if not r.done]
        if mid:
            return next((r for r in live if r.mission_id == mid), None)
        # No id (older client / a mission whose row couldn't be created): only safe
        # when exactly one mission is live — otherwise the frame is ambiguous.
        return live[0] if len(live) == 1 else None

    def route(self, msg: dict) -> bool:
        """Deliver a mission-control frame to its mission. Returns True if handled."""
        t = msg.get("type")
        runner = self._find(msg.get("mission_id"))
        if runner is None:
            return False
        if t in ("approve", "reject"):
            return runner.provide_decision(msg)
        if t in ("mission_stop", "cancel"):
            runner.request_stop()
            return True
        return False

    @staticmethod
    def is_control(msg: dict) -> bool:
        """Frames meant for a RUNNING mission, not the chat turn. An id-less
        approve/cancel stays a plan decision (handled inside the plan wait) — unless
        it carries the ``mission: true`` marker (a mission whose row couldn't be
        persisted has no id; the sole-live-runner fallback routes it)."""
        t = msg.get("type")
        if t == "mission_stop":
            return True
        if t not in ("approve", "reject", "cancel"):
            return False
        return bool(msg.get("mission_id")) or bool(msg.get("mission"))

    def close(self) -> None:
        """Client is gone — stop pumping. The missions themselves keep running
        (Phase 4: detached); a client can re-attach later."""
        for t in list(self._pumps):
            t.cancel()


async def _mission_roster(user: User, home_server: Server | None) -> list[Server]:
    """The servers this mission may act on — thin session-owning wrapper over the
    canonical team_service.mission_roster (shared with build_chat_context)."""
    async with AsyncSessionLocal() as db:
        return await team_service.mission_roster(db, user, home_server, _MISSION_ROSTER_MAX)


def _step_target(step: dict, roster_by_id: dict[str, Server], home: Server | None) -> Server | None:
    """Resolve a mission step's target server. Unknown/missing ids fall back to the
    home server (single-server missions keep working even if the model omits the id);
    with no home and no valid id the step has no target."""
    sid = str(step.get("server_id") or "").strip()
    if sid and sid in roster_by_id:
        return roster_by_id[sid]
    return home


def _validate_transfer(
    step: dict, roster_by_id: dict[str, Server]
) -> tuple[Server, str, Server, str] | str:
    """Check a transfer step's endpoints against the roster. Returns (src, src_path,
    dst, dst_path) or a plain-English error string. Transfers are SFTP → SSH only."""
    src = roster_by_id.get(str(step.get("from_server_id") or "").strip())
    dst = roster_by_id.get(str(step.get("to_server_id") or "").strip())
    src_path = str(step.get("from_path") or "").strip()
    dst_path = str(step.get("to_path") or "").strip()
    if src is None or dst is None:
        return "transfer endpoints must be servers from the mission's server list"
    if not src_path.startswith("/") or not dst_path.startswith("/"):
        return "transfer paths must be absolute (/…)"
    if src.connection_type != "ssh" or dst.connection_type != "ssh":
        return "transfers work between SSH servers only"
    if str(src.id) == str(dst.id):
        return "source and destination are the same server — use a shell command instead"
    return src, src_path, dst, dst_path


async def _mission_execute(server: Server, cmd: str) -> tuple[int, str, str]:
    """Run one mission step; returns (exit_code, output_tail, note). Output is
    captured (not streamed) — step tails go to the UI and the transcript."""
    lines: list[str] = []
    exit_code, note = 0, ""
    try:
        stream = await connection_manager.execute_stream(server, cmd)
        async for line in stream:
            lines.append(line)
    except CommandStalled as exc:
        if exc.last_output:
            lines.append(exc.last_output)
        lines.append(STALL_NOTE)
        exit_code, note = 1, "stalled"
    except CommandError as exc:
        # CommandError carries the real exit status on .exit_code — args[0] is the
        # human message ("command exited with status 1"), NOT an int. A non-zero exit
        # is normal for a verification step (grep/dpkg finding nothing), so this must
        # never crash the mission.
        exit_code = exc.exit_code if isinstance(getattr(exc, "exit_code", None), int) else 1
        note = "non-zero exit"
    except Exception as exc:  # noqa: BLE001
        lines.append(f"ERROR: {exc}")
        exit_code, note = 1, "error"
    tail = "\n".join(lines)[-_MISSION_TAIL_CHARS:]
    return exit_code, tail, note


# Verification gate: how many gather↔verdict rounds the verifier gets, how many
# read-only checks per round, and how many times the executor may be sent back to
# close a gap the verifier found before we finish honestly. All bounded so the gate
# can never loop or run up cost.
_VERIFY_ROUNDS = 2
_VERIFY_MAX_CHECKS = 4
_VERIFY_MAX_ATTEMPTS = 2


async def _verify_mission_complete(
    ws: WebSocket,
    *,
    home_server: Server | None,
    roster: list[Server],
    roster_by_id: dict[str, Server],
    goal: str,
    skill: skill_service.Skill | None,
    steps: list[dict],
    user_language: str,
    home_id: str | None,
    budget: int,
) -> tuple[str, str, list[dict]]:
    """Independent (adversarial) check that a self-declared 'done' mission is REALLY
    done. Asks the verifier what would PROVE the goal, runs those checks strictly
    READ-ONLY (streamed as `verifying` steps), then returns (verdict, reason, gathered):
    'confirmed' only when fresh evidence proves the goal, else 'unverified' with an
    honest reason. Best-effort — any error resolves to 'unverified' (never a false
    success), and it never crashes the shared socket."""
    gathered: list[dict] = []
    verdict, reason = "unverified", ""
    for round_no in range(_VERIFY_ROUNDS + 1):  # +1 = a forced final-verdict call
        rounds_left = max(0, _VERIFY_ROUNDS - 1 - round_no)
        try:
            result = await ai_service.verify_mission(
                goal, roster, steps + gathered, skill, user_language,
                home_id=home_id, rounds_left=rounds_left,
            )
        except Exception as exc:  # noqa: BLE001 — verification must never break the mission
            logger.warning("mission verification failed: %s", exc)
            return (
                "unverified",
                "I couldn't run my own verification, so I can't confirm this is fully "
                "done — please double-check.",
                gathered,
            )
        verdict = result.get("verdict", "unverified")
        reason = str(result.get("reason", "") or "")
        checks = result.get("checks") or []
        # Final verdict reached (no checks) or no more gathering allowed → stop.
        if not checks or round_no >= _VERIFY_ROUNDS:
            break
        ran_any = False
        for check in checks[:_VERIFY_MAX_CHECKS]:
            cmd = str(check.get("cmd", "")).strip()
            target = _step_target(check, roster_by_id, home_server)
            index = len(steps) + len(gathered) + 1
            if not cmd or target is None:
                continue
            why = str(check.get("why", "") or "")[:200]
            desc = f"Verifying: {why}" if why else "Verifying the result"
            # A verification check may ONLY observe. Anything mutating is skipped
            # (recorded so the verifier sees it wasn't run) — never executed.
            if not safety_service.is_read_only_command(cmd):
                gathered.append({
                    "server": target.name, "description": desc, "cmd": cmd,
                    "exit_code": 1, "output_tail": "",
                    "note": "skipped — a verification check must be read-only",
                })
                await ws.send_text(json.dumps({
                    "type": "mission_step_done",
                    "index": index, "cmd": cmd, "description": desc,
                    "exit_code": 1, "output_tail": "",
                    "note": "Skipped — a verification check must be read-only.",
                    "server_id": str(target.id), "server_name": target.name,
                    "verifying": True,
                }))
                continue
            await ws.send_text(json.dumps({
                "type": "mission_step",
                "index": index, "budget": budget,
                "cmd": cmd, "description": desc, "risk_level": "low",
                "needs_approval": False,
                "server_id": str(target.id), "server_name": target.name,
                "verifying": True,
            }))
            exit_code, tail, note = await _mission_execute(target, cmd)
            gathered.append({
                "server": target.name, "description": desc, "cmd": cmd,
                "exit_code": exit_code, "output_tail": tail, "note": note,
            })
            await ws.send_text(json.dumps({
                "type": "mission_step_done",
                "index": index, "cmd": cmd, "description": desc,
                "exit_code": exit_code, "output_tail": tail, "note": note,
                "server_id": str(target.id), "server_name": target.name,
                "verifying": True,
            }))
            ran_any = True
        if not ran_any:
            break  # nothing runnable this round — stop with the current verdict
    return verdict, reason, gathered


async def _run_mission(
    ws: "mission_runner.MissionRunner",
    user: User,
    *,
    home_server: Server | None,
    goal: str,
    skill_slug: str | None,
    user_language: str,
    resume: dict | None = None,
    ally_mode_override: str | None = None,
) -> None:
    """The mission loop: plan ONE step → validate → (approve if risky) → execute →
    observe → repeat, until done/blocked/stopped/budget. Stage 2: steps carry their
    own target server (validated against the user's executable roster), and a
    "transfer" step copies a file between two servers through the backend.

    Phase 3: checkpointed to the DB after every step (durable + resumable).
    Phase 4: ``ws`` is a **MissionRunner**, not a socket — the loop runs DETACHED as a
    background task, fanning events out to whatever clients are attached (or none). It
    calls ``ws.send_text`` (fan-out), ``ws.wait_decision`` (approval), and
    ``ws.stop_requested``; a dropped client no longer ends the mission. See
    docs/ALLY-MISSIONS.md."""
    goal = (goal or "").strip()[:500]
    if not goal:
        await ws.send_text(json.dumps({"type": "error", "message": "Mission needs a goal."}))
        return None
    # Missions run shell steps — panel-API connections can't do that.
    if home_server is not None and home_server.connection_type == "hosting":
        await ws.send_text(json.dumps({
            "type": "error",
            "message": (
                "Missions need a shell (SSH) connection. This server is connected "
                "through its control panel API — add it over SSH to run missions."
            ),
        }))
        return None

    roster = await _mission_roster(user, home_server)
    if not roster:
        await ws.send_text(json.dumps({
            "type": "error",
            "message": "Missions need at least one SSH or Windows server you can run commands on.",
        }))
        return None
    roster_by_id = {str(s.id): s for s in roster}
    home_id = str(home_server.id) if home_server is not None else None
    # Track D: the user's autonomy mode shapes how much Ally assumes and the approval
    # floor (careful → confirm any mutating step). Never lowers the safety floor.
    #
    # ``ally_mode_override`` lets an UNATTENDED caller raise that floor. Autopilot passes
    # "careful" so that EVERY mutating step reaches its policy: without it, a step the
    # engine considers ordinary (`systemctl restart nginx`, even `rm -f /tmp/x` — both
    # safety-'ok') would run without ever consulting the policy, and a "look and tell me"
    # task could still change the server. The override can only ADD approvals.
    ally_mode = ai_service.normalize_mode(ally_mode_override or getattr(user, "ally_mode", None))

    # Quota gate — a mission costs 1 action (§4 of the missions doc); billed to the
    # home server owner's pool, or the acting user's own pool for fleet missions.
    billing_user_id = home_server.user_id if home_server is not None else user.id
    try:
        async with AsyncSessionLocal() as db:
            payer = await db.get(User, billing_user_id)
            g = await metering_service.gate(db, payer) if payer else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("quota gate failed (mission): %s", exc)
        g = None
    if g and not g.allowed:
        await ws.send_text(json.dumps({
            "type": "quota_exceeded",
            "used": g.used, "limit": g.limit, "resets_at": g.resets_at,
            "message": metering_service.quota_message(g),
        }))
        return None

    # A mission may be driven by one of the account's own runbooks, so its library has to be
    # in scope here too — otherwise a custom mission would start with no procedure at all.
    if skill_slug:
        async with AsyncSessionLocal() as _db:
            skill = skill_service.get(skill_slug, extra=await runbook_service.load_for(_db, user))
            if skill is not None:
                await runbook_service.record_use(_db, skill)
    else:
        skill = None
    budget = skill_service.resolve_mission_budget(skill)  # per-skill; default for ad-hoc
    steps: list[dict] = []
    verify_attempts = 0  # times the verifier sent the executor back to close a gap
    verify_step_count = 0  # read-only verification steps — excluded from the budget
    wait_step_count = 0    # `wait` (poll) steps — also excluded from the budget
    total_wait = 0         # seconds slept across the mission (bounded by _WAIT_TOTAL_MAX)
    logger.info(
        "mission started: %r (home=%s, roster=%d, skill=%s)",
        goal, home_id, len(roster), skill_slug,
    )
    # Phase 3 persistence: reuse the row + transcript on resume, else create a fresh
    # mission row. Phase 4: register the runner by id so clients can attach to it.
    if resume is not None:
        mission_id = resume.get("mission_id")
        steps = list(resume.get("steps") or [])
    else:
        mission_id = await mission_service.start(
            user_id=user.id, server=home_server, skill_slug=skill_slug, goal=goal, budget=budget,
        )
    if mission_id:
        mission_runner.register(ws, str(mission_id))

    await ws.send_text(json.dumps({
        "type": "mission_started",
        "mission_id": str(mission_id) if mission_id else None,
        "goal": goal,
        "skill": skill.slug if skill else None,
        "budget": budget,
        "resumed": resume is not None,
        # Home server → the card's identity tint (fleet missions carry none).
        "server_id": home_id,
        "server_name": home_server.name if home_server is not None else None,
    }))

    # On resume, replay the saved transcript into the UI so the timeline rebuilds.
    if resume is not None:
        for i, s in enumerate(steps, 1):
            await ws.send_text(json.dumps({
                "type": "mission_step_done",
                "index": i, "cmd": s.get("cmd", ""), "description": s.get("description", ""),
                "exit_code": s.get("exit_code", 0), "output_tail": s.get("output_tail", ""),
                "note": s.get("note", ""), "server_name": s.get("server"),
                "verifying": bool(s.get("verify")),
            }))
        # A resumed executor must not assume its last (possibly half-run) step finished.
        steps.append({
            "description": "Mission resumed after interruption",
            "cmd": "(resumed)", "exit_code": 0, "output_tail": "",
            "note": ("This mission was interrupted and resumed — re-check the current "
                     "state before assuming your last step completed, and don't repeat "
                     "a change that already happened."),
        })
        await ws.send_text(json.dumps({
            "type": "mission_step_done",
            "index": len(steps), "cmd": "(resumed)",
            "description": "Mission resumed — re-checking before continuing",
            "exit_code": 0, "output_tail": "", "note": "resumed", "verifying": True,
        }))

    tok = metering_service.start_collection()
    try:
        while True:
            # Checkpoint the transcript at the top of each iteration (Phase 3) — this is
            # the point a resumed mission picks back up from.
            await mission_service.checkpoint(mission_id, status="running", steps=steps)

            # Verification checks and waits don't count against the executor's budget —
            # verifying or polling must never be what pushes a mission over the limit.
            executor_steps = len(steps) - verify_step_count - wait_step_count
            if executor_steps >= budget:
                reason = (
                    f"I reached the {budget}-step limit for one mission. "
                    "The steps so far are above — tell me to continue as a new "
                    "mission, or take over from here."
                )
                await mission_service.finalize(mission_id, status="failed", steps=steps, summary=reason)
                await ws.send_text(json.dumps({
                    "type": "mission_failed", "reason": reason, "steps_used": len(steps),
                }))
                return None
            if ws.stop_requested:
                await mission_service.finalize(mission_id, status="stopped", steps=steps)
                await ws.send_text(json.dumps({"type": "mission_stopped", "steps_used": len(steps)}))
                return None

            # 1) Plan the next step from everything observed so far. One retry — a
            # single malformed reply must not kill a long mission. Model ladder: hand a
            # STRUGGLING mission (verifier bounced it back, or repeated failures) a
            # stronger brain for this step, then drop back once it's moving again.
            step_tier = ai_service.mission_step_tier(steps, verify_attempts)
            if step_tier == "high":
                logger.info("mission %s: escalating next step to a stronger model", mission_id)
            decision = None
            plan_error: Exception | None = None
            for attempt in (1, 2):
                try:
                    decision = await ai_service.plan_mission_step(
                        goal, roster, steps, budget - executor_steps, skill,
                        user_language, home_id=home_id, tier=step_tier,
                        ally_mode=ally_mode, model=ws.model,  # pinned model (Ally picker); None = Auto/ladder
                    )
                    break
                except Exception as exc:  # noqa: BLE001
                    plan_error = exc
                    logger.warning("mission step planning failed (attempt %d): %s", attempt, exc)
            if decision is None:
                await mission_service.finalize(
                    mission_id, status="failed", steps=steps, summary=f"AI error: {plan_error}")
                await ws.send_text(json.dumps({
                    "type": "mission_failed",
                    "reason": f"AI error: {plan_error}",
                    "steps_used": len(steps),
                }))
                return None

            status_ = decision.get("status")
            if status_ == "done":
                # VERIFICATION GATE — never accept a self-declared 'done' on trust.
                # An independent verifier gathers fresh READ-ONLY proof the goal is
                # truly met (docs/ALLY-MISSIONS.md §verification). This is the engine-
                # level fix for "claimed success without confirming reality".
                verdict, vreason, gathered = await _verify_mission_complete(
                    ws, home_server=home_server, roster=roster, roster_by_id=roster_by_id,
                    goal=goal, skill=skill, steps=steps, user_language=user_language,
                    home_id=home_id, budget=budget,
                )
                steps.extend(gathered)
                verify_step_count += len(gathered)  # these don't count against the budget
                summary = decision.get("summary", "Mission complete.")
                # Owner-facing structured outcome (headline + Found/Did/Left) — the
                # workspace renders this as a clear result card. None if unusable.
                result = ai_service.sanitize_mission_result(decision.get("result"))

                if verdict == "confirmed":
                    # Only a confirmed goal leaves a memory note (deploy facts) —
                    # server-scoped on the home server, user-scoped for fleet missions.
                    if decision.get("remember"):
                        async with AsyncSessionLocal() as db:
                            await memory_service.save_from_ai(
                                db, user_id=user.id,
                                remember=decision.get("remember"),
                                server_id=home_server.id if home_server is not None else None,
                            )
                    await mission_service.finalize(
                        mission_id, status="complete", steps=steps, verified=True,
                        summary=summary, result=result)
                    await ws.send_text(json.dumps({
                        "type": "mission_complete",
                        "summary": summary,
                        "verified": True,
                        "verification": vreason,
                        "result": result,
                        "steps_used": len(steps),
                    }))
                    return None

                # Not confirmed. Give the executor a bounded chance to close the gap
                # the verifier found (fed back as an observation), if budget remains —
                # this is how a genuinely-fixable "almost done" gets finished.
                verify_attempts += 1
                if verify_attempts < _VERIFY_MAX_ATTEMPTS and (len(steps) - verify_step_count - wait_step_count) < budget:
                    steps.append({
                        "description": "Independent verification",
                        "cmd": "(verification)", "exit_code": 1, "output_tail": "",
                        "note": f"NOT CONFIRMED — {vreason} Address this, then finish.",
                    })
                    verify_step_count += 1  # the fed-back verdict isn't an executor step
                    await ws.send_text(json.dumps({
                        "type": "mission_step_done",
                        "index": len(steps), "cmd": "(verification)",
                        "description": "Independent verification",
                        "exit_code": 1, "output_tail": "",
                        "note": f"Not confirmed yet — {vreason}",
                        "verifying": True,
                    }))
                    continue

                # Out of attempts/budget — finish HONESTLY, not as a success. Never a
                # false green; no memory note (the goal isn't confirmed).
                caveat = vreason or "I could not confirm the goal is fully done — please double-check."
                await mission_service.finalize(
                    mission_id, status="complete", steps=steps, verified=False,
                    summary=caveat, result=result)
                await ws.send_text(json.dumps({
                    "type": "mission_complete",
                    "summary": summary,
                    "verified": False,
                    "caveat": caveat,
                    "result": result,
                    "steps_used": len(steps),
                }))
                return None
            if status_ == "blocked":
                reason = decision.get("summary", "I can't continue from here.")
                # A blocked mission is still a finished-for-now outcome — render the same
                # owner-facing result card (Found/Did/Left), where "Left" holds what Ally
                # needs from the user.
                result = ai_service.sanitize_mission_result(decision.get("result"))
                await mission_service.finalize(
                    mission_id, status="blocked", steps=steps, summary=reason, result=result)
                await ws.send_text(json.dumps({
                    "type": "mission_blocked",
                    "reason": reason,
                    # Track C: enumerable answers ride along as tappable options.
                    "options": _clean_options(decision.get("options")),
                    "result": result,
                    "steps_used": len(steps),
                }))
                return None

            step = decision.get("step") or {}
            action = str(step.get("action") or "run").strip().lower()
            description = str(step.get("description", ""))[:300]
            risk = str(step.get("risk_level", "low"))
            index = len(steps) + 1

            # ── Transfer step: copy ONE file between two roster servers via the
            # backend (no inter-server credentials; never overwrites; size-capped).
            if action == "transfer":
                checked = _validate_transfer(step, roster_by_id)
                if isinstance(checked, str):
                    steps.append({
                        "description": description, "cmd": "(transfer)", "exit_code": 1,
                        "output_tail": "", "note": f"transfer rejected: {checked}",
                    })
                    await ws.send_text(json.dumps({
                        "type": "mission_step_done",
                        "index": index, "cmd": "(transfer)", "description": description,
                        "exit_code": 1, "output_tail": "",
                        "note": f"Transfer rejected — {checked}. Adapting…",
                    }))
                    continue
                src, src_path, dst, dst_path = checked
                display = f"transfer {src.name}:{src_path} → {dst.name}:{dst_path}"
                await ws.send_text(json.dumps({
                    "type": "mission_step",
                    "index": index, "budget": budget,
                    "cmd": display, "description": description, "risk_level": risk,
                    "needs_approval": False,
                    "server_id": str(dst.id), "server_name": f"{src.name} → {dst.name}",
                }))
                try:
                    copied = await file_service.transfer_between(src, src_path, dst, dst_path)
                    exit_code, tail, note = 0, f"copied {copied:,} bytes", ""
                except ValueError as exc:  # guard failures carry a plain message
                    exit_code, tail, note = 1, str(exc), "transfer refused"
                except Exception as exc:  # noqa: BLE001
                    exit_code, tail, note = 1, f"ERROR: {exc}", "transfer failed"
                steps.append({
                    "server": f"{src.name}→{dst.name}", "description": description,
                    "cmd": display, "exit_code": exit_code, "output_tail": tail, "note": note,
                })
                await ws.send_text(json.dumps({
                    "type": "mission_step_done",
                    "index": index, "cmd": display, "description": description,
                    "exit_code": exit_code, "output_tail": tail, "note": note,
                    "server_id": str(dst.id), "server_name": f"{src.name} → {dst.name}",
                }))
                continue

            # ── Wait step: poll a long-running background job (install finishing, a
            # service coming up) WITHOUT spending the step budget. Bounded so a mission
            # can never hang, and a Stop takes effect promptly.
            if action == "wait":
                allowed, seconds = _wait_plan(
                    step.get("seconds", step.get("wait_seconds", 0)), wait_step_count, total_wait
                )
                wait_step_count += 1
                if not allowed:
                    steps.append({
                        "description": description, "cmd": "(wait)", "exit_code": 1,
                        "output_tail": "", "note": "wait budget spent — wrap up or hand over",
                    })
                    await ws.send_text(json.dumps({
                        "type": "mission_step_done",
                        "index": index, "cmd": "(wait)", "description": description,
                        "exit_code": 1, "output_tail": "",
                        "note": "I've waited as long as I safely can — wrapping up.",
                        "waiting": True,
                    }))
                    continue
                display = f"wait {seconds}s"
                await ws.send_text(json.dumps({
                    "type": "mission_step",
                    "index": index, "budget": budget,
                    "cmd": display,
                    "description": description or f"Waiting {seconds}s for the last step to finish…",
                    "risk_level": "low", "needs_approval": False, "waiting": True,
                }))
                slept, stopped = 0, False
                while slept < seconds:
                    chunk = min(3, seconds - slept)
                    await asyncio.sleep(chunk)
                    slept += chunk
                    if ws.stop_requested:
                        stopped = True
                        break
                total_wait += slept
                steps.append({
                    "description": description, "cmd": display, "exit_code": 0,
                    "output_tail": f"waited {slept}s", "note": "",
                })
                await ws.send_text(json.dumps({
                    "type": "mission_step_done",
                    "index": index, "cmd": display, "description": description,
                    "exit_code": 0, "output_tail": f"waited {slept}s", "note": "", "waiting": True,
                }))
                if stopped:
                    await ws.send_text(json.dumps({"type": "mission_stopped", "steps_used": len(steps)}))
                    return None
                continue

            # ── Run step: a single command on ONE roster server.
            cmd = str(step.get("cmd", "")).strip()
            if not cmd:
                await mission_service.finalize(
                    mission_id, status="failed", steps=steps, summary="The AI returned an empty step.")
                await ws.send_text(json.dumps({
                    "type": "mission_failed",
                    "reason": "The AI returned an empty step.",
                    "steps_used": len(steps),
                }))
                return None
            target = _step_target(step, roster_by_id, home_server)
            if target is None:
                steps.append({
                    "description": description, "cmd": cmd, "exit_code": 1,
                    "output_tail": "", "note": "no valid server_id on this step",
                })
                await ws.send_text(json.dumps({
                    "type": "mission_step_done",
                    "index": index, "cmd": cmd, "description": description,
                    "exit_code": 1, "output_tail": "",
                    "note": "Step had no valid target server. Adapting…",
                }))
                continue
            target_family = "windows" if target.connection_type == "winrm" else "linux"

            # 2) Safety — same blocklist as everything else, per step, per TARGET OS.
            safety = safety_service.validate_command(cmd, target_family)
            if safety.status == "blocked":
                steps.append({
                    "server": target.name, "description": description, "cmd": cmd,
                    "exit_code": 1, "output_tail": "",
                    "note": f"BLOCKED by safety policy: {safety.reason}",
                })
                await ws.send_text(json.dumps({
                    "type": "mission_step_done",
                    "index": index, "cmd": cmd, "description": description,
                    "exit_code": 1, "output_tail": "",
                    "note": f"Blocked by safety policy — {safety.reason}. Adapting…",
                    "server_id": str(target.id), "server_name": target.name,
                }))
                continue  # the block is in the transcript; Ally adapts next iteration

            # 3) Risky steps pause for the user, even mid-mission. The base floor
            # (safety-confirm / explicitly-flagged / high-risk) holds in EVERY mode —
            # the autonomy mode (Track D) can only ADD approvals, never remove them.
            # Careful mode pauses for ANY step that changes the server (not read-only);
            # proactive/normal differ in how much the PROMPT lets Ally assume up front,
            # which shows up as fewer steps flagged risky, not a lower engine floor.
            needs_approval = safety.status == "confirm" or bool(step.get("requires_confirmation")) or risk == "high"
            if ally_mode == "careful" and not safety_service.is_read_only_command(cmd):
                needs_approval = True
            step_event = {
                "type": "mission_step",
                "index": index, "budget": budget,
                "cmd": cmd, "description": description, "risk_level": risk,
                "needs_approval": needs_approval,
                # WHY approval was asked for. `needs_approval` alone is ambiguous (and in
                # careful mode it is true for every change), so an unattended policy
                # caller cannot tell an AI-flagged step from an ordinary one without this.
                "ai_flagged": bool(step.get("requires_confirmation")),
                "server_id": str(target.id), "server_name": target.name,
                # Smart Model Ladder: this step was planned with a stronger brain — either
                # the loop escalated (mission struggling) or Ally asked for it up front.
                "strong": step_tier == "high" or bool(decision.get("escalated")),
            }
            await ws.send_text(json.dumps(step_event))
            if needs_approval:
                # Persist the pause so it's visible/resumable while we wait (Phase 3);
                # Phase 4: wait on the RUNNER for a decision — a detached mission just
                # pauses here (paused-awaiting-approval, persisted) until a client
                # attaches and approves, or the wait times out. Remember the prompt so a
                # client that ATTACHES mid-approval can be re-shown it.
                await mission_service.checkpoint(mission_id, status="awaiting_approval", steps=steps)
                ws.pending_approval = step_event
                try:
                    decision_msg = await ws.wait_decision()
                finally:
                    ws.pending_approval = None
                if decision_msg is None:  # nobody returned to approve within the window
                    await mission_service.finalize(
                        mission_id, status="blocked", steps=steps,
                        summary="I paused for your approval but didn't hear back — nothing was changed.")
                    await ws.send_text(json.dumps({
                        "type": "mission_blocked",
                        "reason": "I paused for your approval but didn't hear back, so I stopped here. Nothing was changed.",
                        "steps_used": len(steps),
                    }))
                    return None
                if decision_msg.get("type") != "approve":  # stop / reject
                    await mission_service.finalize(mission_id, status="stopped", steps=steps)
                    await ws.send_text(json.dumps({"type": "mission_stopped", "steps_used": len(steps)}))
                    return None

            # 4) Execute + observe.
            exit_code, tail, note = await _mission_execute(target, cmd)
            steps.append({
                "server": target.name, "description": description, "cmd": cmd,
                "exit_code": exit_code, "output_tail": tail, "note": note,
            })
            await ws.send_text(json.dumps({
                "type": "mission_step_done",
                "index": index, "cmd": cmd, "description": description,
                "exit_code": exit_code, "output_tail": tail, "note": note,
                "server_id": str(target.id), "server_name": target.name,
            }))
    except asyncio.CancelledError:
        # Backend shutting down — leave the mission resumable (recover_orphaned also
        # covers this on the next startup). Don't swallow the cancellation.
        await mission_service.mark_interrupted(mission_id)
        raise
    except Exception as exc:  # noqa: BLE001 — a mission (detached task) must never crash silently
        logger.exception("mission crashed (goal=%r)", goal)
        await mission_service.finalize(
            mission_id, status="failed", steps=steps,
            summary=f"The mission hit an unexpected error and stopped: {exc}")
        await ws.send_text(json.dumps({
            "type": "mission_failed",
            "reason": f"The mission hit an unexpected error and stopped: {exc}",
            "steps_used": len(steps),
        }))
    finally:
        calls = metering_service.finish_collection(tok)
        if calls:
            async with AsyncSessionLocal() as db:
                await metering_service.record(
                    db, user_id=billing_user_id, feature="mission",
                    calls=calls,
                    server_id=home_server.id if home_server is not None else None,
                    skill=skill.slug if skill else None,
                )


# ── Phase 4: detached execution + client bridge ───────────────────────────────

async def _run_mission_detached(runner: mission_runner.MissionRunner, user: User, **kwargs) -> None:
    """Run a mission to completion as a background task, decoupled from any client.
    Whatever happens, mark the runner finished so attached bridges unblock."""
    try:
        await _run_mission(runner, user, **kwargs)
    except asyncio.CancelledError:
        raise
    except Exception:  # noqa: BLE001 — a detached task must never die unnoticed
        logger.exception("detached mission task crashed")
    finally:
        runner.finish()


async def _replay_mission_to(ws: WebSocket, m) -> None:
    """Send a reconnecting client the mission's current state (a fresh mission_started
    + every step so far, from the DB) so it catches up before live events resume.
    Everything is tagged with the mission's id so it lands on the right card."""
    mid = str(m.id)
    await ws.send_text(json.dumps({
        "type": "mission_started", "mission_id": mid, "goal": m.goal,
        "skill": m.skill_slug, "budget": m.budget, "resumed": False, "attached": True,
        "server_id": str(m.server_id) if m.server_id else None,
        "server_name": m.server_name,
    }))
    for i, s in enumerate(mission_service.steps_of(m), 1):
        await ws.send_text(json.dumps({
            "type": "mission_step_done", "mission_id": mid,
            "index": i, "cmd": s.get("cmd", ""), "description": s.get("description", ""),
            "exit_code": s.get("exit_code", 0), "output_tail": s.get("output_tail", ""),
            "note": s.get("note", ""), "server_name": s.get("server"),
            "verifying": bool(s.get("verify")),
        }))


async def _load_runbooks(acting_user_id: str | None, server: Server) -> list:
    """The account's own runbooks, as Skills. Best-effort: if this fails, Ally falls back to
    its built-in procedures rather than the conversation breaking."""
    try:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, acting_user_id or server.user_id)
            if user is None:
                return []
            return await runbook_service.load_for(db, user)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load custom runbooks: %s", exc)
        return []


async def _handle_message(
    ws: WebSocket,
    server: Server,
    user_input: str,
    user_language: str,
    os_family: str,
    page_context: str | None = None,
    history: list[dict] | None = None,
    acting_user_id: str | None = None,
    mission_control: "_MissionHub | None" = None,
    model: str | None = None,
) -> dict | None:
    """Metered wrapper (docs/AI-METERING.md) — collects every model call made for this
    one user message (plan → execute → explain = 1 action) and writes the ledger,
    billed to the server owner's pool. Metering never blocks the message itself.
    Returns a leftover client frame for the loop to reprocess, or None.

    Also matches an Ally Skill (Phase A): a deterministic trigger match picks the
    expert procedure for this kind of task; the slug is tagged on the ledger rows."""
    # The account's own runbooks (Pro #7) are considered alongside the built-in skills, and
    # win a tie — that is what "teach Ally YOUR procedures" has to mean.
    runbooks = await _load_runbooks(acting_user_id, server)
    skill = skill_service.match(user_input, server.os_type, extra=runbooks,
                                panel=server.panel_type or "")
    if skill:
        logger.info("ally skill matched: %s%s (server=%s)", skill.slug,
                    " [custom]" if skill_service.is_custom(skill) else "", server.id)
    # The inner handler may upgrade the skill via the Phase B menu hop — it reports the
    # effective skill back through this holder so the ledger attributes correctly.
    meta = {"skill": skill.slug if skill else None}
    tok = metering_service.start_collection()
    try:
        return await _handle_message_inner(
            ws, server, user_input, user_language, os_family, page_context, history,
            acting_user_id=acting_user_id, skill=skill, meta=meta,
            mission_control=mission_control, model=model,
        )
    finally:
        calls = metering_service.finish_collection(tok)
        if calls:
            async with AsyncSessionLocal() as db:
                await metering_service.record(
                    db, user_id=server.user_id, feature="chat",
                    calls=calls, server_id=server.id,
                    skill=meta.get("skill"),
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
    meta: dict | None = None,
    mission_control: "_MissionHub | None" = None,
    model: str | None = None,
) -> dict | None:
    """Plan, validate, execute and explain one user message. Returns a leftover
    client frame (a new message that arrived instead of approve/cancel) or None.

    ``model`` (Ally's model picker): a pinned model id for the planning call, or None for
    Auto (the ladder). The mission it may offer carries the same pick via the start frame."""
    # ── 1. AI planning ────────────────────────────────────────────────────────
    await ws.send_text(json.dumps({"type": "thinking"}))

    # Ally Brain — assemble the full per-message context (server profile, memories,
    # autonomy mode, other reachable servers with health, read-only scout, live snapshot,
    # skill menu). Shared with the Dev Door dry-run via ai_context_service so both build
    # byte-identical prompts. Best-effort throughout — a failed piece degrades to None and
    # never blocks the chat (Phase 3/5, Track A/B, Context C1 all live inside it now).
    ctx = await ai_context_service.build_chat_context(
        server, user_input, acting_user_id=acting_user_id, skill=skill, runbooks=runbooks,
    )

    try:
        plan = await ai_service.plan_commands(
            user_input, server, user_language, page_context, history,
            server_profile=ctx.server_profile, memories=ctx.memories, skill=skill,
            skill_menu=ctx.skill_menu,
            live_snapshot=ctx.live_snapshot, other_servers=ctx.other_servers, scout=ctx.scout,
            ally_mode=ctx.ally_mode, model=model,
        )
    except Exception as exc:
        await ws.send_text(json.dumps({"type": "error", "message": f"AI error: {exc}"}))
        return

    # Phase B hop — the model requested a skill from the menu. Load it and plan again
    # (one hop max; the slug must exist and fit this OS, otherwise the reply stands).
    requested = plan.get("use_skill")
    if skill is None and isinstance(requested, str) and requested.strip():
        picked = skill_service.get_for_os(requested.strip(), server.os_type, extra=runbooks)
        if picked is not None:
            logger.info("ally skill requested via menu: %s (server=%s)", picked.slug, server.id)
            skill = picked
            if meta is not None:
                meta["skill"] = picked.slug
            try:
                plan = await ai_service.plan_commands(
                    user_input, server, user_language, page_context, history,
                    server_profile=ctx.server_profile, memories=ctx.memories, skill=picked,
                    live_snapshot=ctx.live_snapshot, other_servers=ctx.other_servers, scout=ctx.scout,
                    ally_mode=ctx.ally_mode, model=model,
                )
            except Exception as exc:  # noqa: BLE001
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

    # If AI needs clarification, return early. Track C: enumerable answers ride along
    # as tappable "options" so the user picks instead of typing (and Ally is nudged to
    # ask ONE bundled question, not a chain).
    if plan.get("clarification_needed"):
        await ws.send_text(json.dumps({
            "type": "clarification",
            "message": plan["clarification_needed"],
            "options": _clean_options(plan.get("clarification_options")),
            "server_id": str(server.id),
            "server_name": server.name,
        }))
        return

    # Ally Missions — the plan is a mission OFFER (multi-step job, no commands yet).
    # The user starts it with one click; the mission loop then works step by step.
    mission = plan.get("mission")
    if isinstance(mission, dict) and str(mission.get("goal", "")).strip():
        await ws.send_text(json.dumps({
            "type": "mission_offer",
            "goal": str(mission.get("goal"))[:500],
            # Any matched skill rides along as the mission's runbook — diagnostic
            # (knowledge) skills guide rescue missions just as deploy runbooks guide
            # deploys (the engine injects skill.body regardless of mode).
            "skill": skill.slug if skill else None,
            "server_id": str(server.id),
            "server_name": server.name,
            "message": plan.get("plan_summary", ""),
        }))
        return None

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
        "server_id": str(server.id),
        "server_name": server.name,
        # Smart Model Ladder: Ally judged this request hard and re-planned it on a
        # stronger model before showing you this plan.
        "strong": bool(plan.get("escalated")),
    }))

    # ── 4. Wait for approval if required ─────────────────────────────────────
    # The approval binds server-side to THIS plan on THIS server. A new message
    # arriving instead of approve/cancel cancels the plan and is handed back to
    # the loop so the user's words are never swallowed (unified socket). Control
    # frames for a RUNNING mission (they carry a mission_id) are routed to it and
    # never touch this plan — a mission card's Approve can't approve a plan.
    if requires_approval:
        while True:
            raw = await ws.receive_text()
            try:
                decision = json.loads(raw)
            except (TypeError, ValueError):
                decision = {}
            if mission_control is not None and _MissionHub.is_control(decision):
                mission_control.route(decision)
                continue
            break
        if decision.get("type") != "approve":
            log = await _save_log(server, user_input, user_language, plan, "", "cancelled")
            await ws.send_text(json.dumps({"type": "cancelled", "log_id": str(log.id)}))
            if decision.get("type") in ("message", "mission_start"):
                return decision
            return None

    # ── 5. Execute ────────────────────────────────────────────────────────────
    # Durable worker path (when a Celery worker is up): create the log up front (so
    # it has an id to stream and cancel against), enqueue the worker, and tail its
    # log — survives client disconnects (Update 15, slice 4). If the flag is on but
    # no worker responds, fall back to inline so the run never hangs (Risk 2).
    # NOTE (live-found 2026-07-14): the inline path runs the whole plan on THIS ws
    # handler, so a single long-running command (e.g. a `maldet` scan over a large
    # infected vhost — 10+ min) blocks the receive loop. Because Ally uses one socket,
    # the user can't send another message (or Stop) until it finishes. Long scans are
    # better run as a detached mission (which polls via the `wait` action and never
    # blocks the socket) or via the Celery worker path below. Worth a follow-up.
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

    # Track B Phase 2: Ally may append artifact block(s) (a table/chart) for the Workspace.
    # Split them out of the chat text so the conversation stays clean and the panels render
    # beside it. Robust: no/invalid blocks → empty list, text unchanged.
    explanation, artifacts = ai_service.split_artifacts(explanation)

    # ── 7. Save to DB ─────────────────────────────────────────────────────────
    log = await _save_log(
        server, user_input, user_language, plan, raw_output, overall_status,
        execution_ms=execution_ms,
    )

    # The code-level floor under the prompt's "remember your cleanups" rule (BUG-001):
    # a HIGH-RISK change that succeeded is recorded automatically, whether or not the
    # model thought to emit "remember". Narrow by design + best-effort (never breaks chat).
    async with AsyncSessionLocal() as db:
        await memory_service.record_action(
            db,
            user_id=acting_user_id or server.user_id,
            server_id=server.id,
            commands=plan.get("commands"),
            status=overall_status,
        )

    await ws.send_text(json.dumps({
        "type": "execution_complete",
        "log_id": str(log.id),
        "status": overall_status,
        "explanation": explanation,
        "artifacts": artifacts,
        "follow_up_suggestions": plan.get("follow_up_suggestions", []),
        "server_id": str(server.id),
        "server_name": server.name,
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
        # Attribute the completion to its server (the chat colors the message by it).
        srv = await db.get(Server, log.server_id) if log.server_id else None
    if log.status in _TERMINAL_RUN_STATUSES:
        return log.output, {
            "type": "execution_complete", "log_id": run_id, "status": log.status,
            "explanation": log.ai_explanation or "",
            "follow_up_suggestions": (log.ai_plan or {}).get("follow_up_suggestions", []),
            "server_id": str(log.server_id) if log.server_id else None,
            "server_name": srv.name if srv else None,
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

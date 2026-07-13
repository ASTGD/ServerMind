"""Guacamole RDP tunnel — the live in-browser desktop (Assets Phase E, guacd).

Bridges the browser (a WebSocket driven by guacamole-common-js) to guacd (TCP), which
speaks RDP to the Windows host and translates the pixels into the Guacamole wire protocol.

SECURITY: the RDP credentials are resolved SERVER-SIDE here from the short-lived session
token and handed to guacd during the handshake — they NEVER travel to the browser. The
browser only ever holds the opaque session token (access-checked, expiring). A viewer role
can't reach this: the token is only minted by ``rdp_service.issue_session`` behind
``resolve_server(need_execute=True)``.

The Guacamole protocol is a stream of instructions ``LEN.value,LEN.value,…;`` (LEN counts
Unicode characters). We perform the client handshake with guacd (select → args → connect),
then relay bytes both ways. See docs/HOSTING or the Apache Guacamole protocol reference.
"""
from __future__ import annotations

import asyncio
import codecs
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.server import Server
from app.services import auth_service, rdp_service
from app.services.crypto_service import decrypt

logger = logging.getLogger(__name__)
router = APIRouter()

_DEFAULT_W, _DEFAULT_H, _DEFAULT_DPI = 1280, 720, 96
_HANDSHAKE_TIMEOUT_S = 15.0


def _encode(*elements: str) -> bytes:
    """One Guacamole instruction: LEN.value,… ; (LEN = character count, per the spec)."""
    return (",".join(f"{len(e)}.{e}" for e in elements) + ";").encode("utf-8")


async def _read_instruction(reader: asyncio.StreamReader) -> list[str]:
    """Read exactly one Guacamole instruction from guacd (used only during the handshake;
    after that we relay raw). Handshake content is ASCII, so byte length == char length."""
    elements: list[str] = []
    while True:
        num = b""
        while True:
            ch = await reader.readexactly(1)
            if ch == b".":
                break
            num += ch
        length = int(num)
        value = (await reader.readexactly(length)).decode("utf-8", "replace")
        elements.append(value)
        sep = await reader.readexactly(1)  # ',' between elements, ';' ends the instruction
        if sep == b";":
            break
    return elements


def _guacd_addr() -> tuple[str, int]:
    raw = (settings.RDP_GUACD_URL or "127.0.0.1:4822").replace("tcp://", "")
    host, _, port = raw.partition(":")
    return host or "127.0.0.1", int(port or 4822)


async def _handshake(
    gr: asyncio.StreamReader, gw: asyncio.StreamWriter, *,
    hostname: str, port: int, username: str, password: str,
    width: int, height: int, dpi: int,
) -> str:
    """Perform the Guacamole client handshake with guacd for an RDP connection. Returns the
    guacd connection id on success; raises on failure (so the caller can close honestly)."""
    # 1. select the protocol
    gw.write(_encode("select", "rdp"))
    await gw.drain()

    # 2. guacd replies with the args it wants: ["args", "VERSION_x_y_z", "hostname", …]
    args = await _read_instruction(gr)
    if not args or args[0] != "args":
        raise RuntimeError(f"guacd did not send args (got {args[:2]})")
    arg_names = args[1:]

    # 3. tell guacd our display + supported media (empty audio/video = none)
    gw.write(_encode("size", str(width), str(height), str(dpi)))
    gw.write(_encode("audio"))
    gw.write(_encode("video"))
    gw.write(_encode("image", "image/png", "image/jpeg"))
    await gw.drain()

    # 4. connect: one value per arg guacd listed, in order. Fill what we know; echo the
    #    VERSION token; leave the rest empty (guacd applies its defaults).
    known = {
        "hostname": hostname, "port": str(port),
        "username": username, "password": password,
        "security": "any", "ignore-cert": "true",
        "resize-method": "display-update",
        "width": str(width), "height": str(height), "dpi": str(dpi),
        "enable-wallpaper": "true",
    }
    values: list[str] = []
    for name in arg_names:
        if name.upper().startswith("VERSION"):
            values.append(name)  # echo the version guacd offered
        else:
            values.append(known.get(name, ""))
    gw.write(_encode("connect", *values))
    await gw.drain()

    # 5. guacd → "ready,<id>;" on success (anything else is an error/refusal)
    ready = await _read_instruction(gr)
    if ready and ready[0] == "ready":
        return ready[1] if len(ready) > 1 else ""
    raise RuntimeError(f"guacd refused the connection (got {ready[:4]})")


def _int_param(ws: WebSocket, name: str, default: int) -> int:
    try:
        return max(200, min(4096, int(ws.query_params.get(name, default))))
    except (TypeError, ValueError):
        return default


@router.websocket("/ws/rdp")
async def rdp_tunnel(websocket: WebSocket) -> None:
    """Browser ⇄ guacd ⇄ RDP host. Auth by the ?token= session token; size via ?width/height/dpi."""
    # guacamole-common-js negotiates the "guacamole" subprotocol.
    await websocket.accept(subprotocol="guacamole")

    token = websocket.query_params.get("token", "")
    payload = auth_service.decode_token(token)
    if not payload or payload.get("type") != "rdp":
        await websocket.close(code=4401)  # unauthorized
        return
    server_id, user_id = payload.get("server_id"), payload.get("sub")

    # Load the asset + confirm the token's user owns it, then decrypt the RDP secret.
    try:
        async with AsyncSessionLocal() as db:
            server = await db.get(Server, uuid.UUID(str(server_id)))
            if server is None or str(server.user_id) != str(user_id):
                await websocket.close(code=4403)  # forbidden
                return
            rdp_service.ensure_available(server)  # Windows-only, enabled
            password = decrypt(server.encrypted_cred)
    except rdp_service.RdpError as exc:
        logger.info("RDP tunnel refused: %s", exc)
        await websocket.close(code=4403)
        return
    except Exception:  # noqa: BLE001
        logger.warning("RDP tunnel setup failed", exc_info=True)
        await websocket.close(code=1011)
        return

    width = _int_param(websocket, "width", _DEFAULT_W)
    height = _int_param(websocket, "height", _DEFAULT_H)
    dpi = _int_param(websocket, "dpi", _DEFAULT_DPI)

    # Open guacd + handshake.
    ghost, gport = _guacd_addr()
    try:
        gr, gw = await asyncio.wait_for(asyncio.open_connection(ghost, gport), timeout=8.0)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cannot reach guacd at %s:%s — %s", ghost, gport, exc)
        await websocket.close(code=1011)
        return

    try:
        await asyncio.wait_for(
            _handshake(
                gr, gw, hostname=server.host, port=rdp_service.rdp_port(server),
                username=server.username, password=password,
                width=width, height=height, dpi=dpi,
            ),
            timeout=_HANDSHAKE_TIMEOUT_S,
        )
    except Exception as exc:  # noqa: BLE001 — desktop unreachable / refused / timed out
        logger.info("RDP handshake failed for %s: %s", server.host, exc)
        try:
            await websocket.close(code=1011)
        finally:
            gw.close()
        return

    logger.info("RDP tunnel established: user %s → %s:%s", user_id, server.host, server.port)
    await _pump(websocket, gr, gw)


async def _pump(websocket: WebSocket, gr: asyncio.StreamReader, gw: asyncio.StreamWriter) -> None:
    """Relay the Guacamole stream both ways until either side closes."""
    decoder = codecs.getincrementaldecoder("utf-8")("replace")

    async def guacd_to_browser() -> None:
        try:
            while True:
                data = await gr.read(16384)
                if not data:
                    break
                text = decoder.decode(data)
                if text:
                    await websocket.send_text(text)
        except Exception:  # noqa: BLE001 — normal on close
            pass

    async def browser_to_guacd() -> None:
        try:
            while True:
                msg = await websocket.receive_text()
                gw.write(msg.encode("utf-8"))
                await gw.drain()
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001
            pass

    t1 = asyncio.create_task(guacd_to_browser())
    t2 = asyncio.create_task(browser_to_guacd())
    _, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    gw.close()
    try:
        await websocket.close()
    except Exception:  # noqa: BLE001
        pass

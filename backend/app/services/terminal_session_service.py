"""Server-side terminal session broker (Phase 2 — reconnect / restore).

Keeps the SSH PTY alive across WebSocket drops so a reconnecting client re-attaches
to the *same* shell: running commands survive, and output produced while detached is
buffered and replayed. A session is reaped after a grace period with no attached
client, or when the client explicitly closes it.

NOTE: sessions are held in-process, so this assumes a single web process (the current
prod topology). Under horizontal scaling a reconnect could land on a worker without the
session; a shared broker (Redis-backed) would be the follow-up.
"""
from __future__ import annotations

import asyncio
import logging
import socket as _socket
import time
from concurrent.futures import ThreadPoolExecutor

import paramiko

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix="term-reader")

GRACE_SECONDS = 180          # keep a detached session alive this long for reconnect
BUFFER_CAP = 256 * 1024      # replay scrollback cap, bytes
_READ_TIMEOUT = 0.3


def _read_channel(channel: paramiko.Channel) -> bytes | None:
    """None ⇒ channel closed; b'' ⇒ open but no data; bytes ⇒ output."""
    channel.settimeout(_READ_TIMEOUT)
    try:
        data = channel.recv(8192)
        return data if data else None
    except _socket.timeout:
        return b""
    except Exception:
        return None


class TermSession:
    def __init__(self, key: str, channel: paramiko.Channel):
        self.key = key
        self.channel = channel
        self.buffer: list[bytes] = []
        self.buffer_size = 0
        self.attached: asyncio.Queue | None = None
        self.detached_at: float | None = time.monotonic()
        self.closed = False
        self.reader: asyncio.Task | None = None

    def append(self, data: bytes) -> None:
        self.buffer.append(data)
        self.buffer_size += len(data)
        while self.buffer_size > BUFFER_CAP and len(self.buffer) > 1:
            self.buffer_size -= len(self.buffer.pop(0))
        if self.attached is not None:
            self.attached.put_nowait(data)

    def alive(self) -> bool:
        if self.closed:
            return False
        t = self.channel.get_transport()
        return bool(t and t.is_active())


_sessions: dict[str, TermSession] = {}
_reaper: asyncio.Task | None = None


def _ensure_reaper() -> None:
    global _reaper
    if _reaper is None or _reaper.done():
        _reaper = asyncio.ensure_future(_reaper_loop())


async def _reaper_loop() -> None:
    while True:
        await asyncio.sleep(30)
        now = time.monotonic()
        for sess in list(_sessions.values()):
            if not sess.alive() or (sess.detached_at is not None and now - sess.detached_at > GRACE_SECONDS):
                close(sess)


async def _reader_loop(sess: TermSession) -> None:
    loop = asyncio.get_event_loop()
    while not sess.closed:
        data = await loop.run_in_executor(_executor, _read_channel, sess.channel)
        if data is None:
            break
        if data:
            sess.append(data)
    close(sess)


async def get_or_create(key: str, opener) -> tuple[TermSession, bool]:
    """Return an existing live session for ``key`` (reattach) or create one.

    ``opener`` is an async callable returning a fresh paramiko channel.
    Returns (session, is_new).
    """
    _ensure_reaper()
    existing = _sessions.get(key)
    if existing is not None and existing.alive():
        return existing, False
    if existing is not None:
        close(existing)
    channel = await opener()
    sess = TermSession(key, channel)
    _sessions[key] = sess
    sess.reader = asyncio.ensure_future(_reader_loop(sess))
    return sess, True


def attach(sess: TermSession) -> tuple[bytes, asyncio.Queue]:
    """Attach the current WebSocket. Returns (scrollback snapshot, live queue).

    Synchronous + atomic: the snapshot captures everything up to now, and every
    subsequent chunk flows to the returned queue — no gap, no duplication.
    """
    q: asyncio.Queue = asyncio.Queue()
    snap = b"".join(sess.buffer)
    sess.attached = q
    sess.detached_at = None
    return snap, q


def detach(sess: TermSession, q: asyncio.Queue) -> None:
    """Detach a WebSocket without ending the session (kept alive for reconnect)."""
    if sess.attached is q:
        sess.attached = None
        sess.detached_at = time.monotonic()


async def write(sess: TermSession, data: str) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        _executor, lambda: sess.channel.sendall(data.encode("utf-8", errors="replace"))
    )


async def resize(sess: TermSession, cols: int, rows: int) -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_executor, lambda: sess.channel.resize_pty(width=cols, height=rows))


def close(sess: TermSession) -> None:
    """End a session for good — close the channel and drop it from the registry."""
    if sess.closed and sess.key not in _sessions:
        return
    sess.closed = True
    _sessions.pop(sess.key, None)
    try:
        sess.channel.close()
    except Exception:
        pass
    if sess.reader is not None:
        sess.reader.cancel()

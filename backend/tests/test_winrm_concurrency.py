"""One WinRM session, twenty threads — the race, and why it is not a lock on a dict.

`winrm.Session` is cached per server and handed to a 20-thread pool. That looks harmless
until you read what a Session actually is. `Session.__init__` builds ONE `Protocol`, which
builds ONE `requests.Session` and sets `session.auth = HttpNtlmAuth(...)` — a single
**stateful** NTLM context, carrying its own sequence numbers and message signing
(`transport.py:256`, `session_security` at :262). And a single `run_ps` is not one request:
`run_cmd` performs open_shell → run_command → get_command_output → cleanup_command →
close_shell, five HTTP calls, all over that one context.

So two threads running commands on one server interleave two five-call sequences through one
signing context. NTLM's answer to an out-of-order signed message is
`SpnegoError (6): invalid MIC` — which is what was seen live on engine.vev.astgd.com.

Worth stating plainly: no instance of that error is stored anywhere. It was seen in the
session and never persisted, so these tests do not rest on it — they demonstrate the race
directly. That is the stronger evidence anyway: the defect is in the code, whatever the logs
happened to keep.

SSH does not have this problem and that is not luck — a paramiko client multiplexes
independent channels by design, which is why `ssh_service` shares one safely. The rule here
is specific to a protocol whose authentication is a conversation.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from app.services import winrm_service as w


class _Result:
    def __init__(self):
        self.std_out, self.std_err, self.status_code = b"ok", b"", 0


class _StubSession:
    """A session that reports being used by two threads at once.

    It does not simulate NTLM — it detects the condition NTLM cannot survive. The sleep is
    what gives a second thread the chance to enter; without it the race is real but rarely
    observed, which is exactly why it reached production.
    """

    def __init__(self):
        self.inside = 0
        self.concurrent_entries = 0
        self.calls = 0
        self._guard = threading.Lock()

    def run_ps(self, script):
        with self._guard:
            self.inside += 1
            self.calls += 1
            if self.inside > 1:
                self.concurrent_entries += 1
        time.sleep(0.05)
        with self._guard:
            self.inside -= 1
        return _Result()


@pytest.fixture
def stub(monkeypatch):
    """Replace session-building and decryption; everything else is the real service."""
    made: list[_StubSession] = []

    def _make(host, port, username, credential):
        s = _StubSession()
        made.append(s)
        return s

    monkeypatch.setattr(w, "_make_session", _make)
    monkeypatch.setattr(w, "decrypt", lambda blob: "pw")
    w._sessions.clear()
    if hasattr(w, "_locks"):
        w._locks.clear()
    yield made
    w._sessions.clear()
    if hasattr(w, "_locks"):
        w._locks.clear()


def run_many(server_id: str, n: int):
    async def go():
        return await asyncio.gather(*[
            w.execute(server_id, "host", 5985, "Administrator", "password", "enc", f"cmd {i}")
            for i in range(n)
        ])

    return asyncio.run(go())


# ── the race ─────────────────────────────────────────────────────────────────

def test_one_servers_session_is_never_used_by_two_threads_at_once(stub):
    """The defect, demonstrated. Without the per-server lock this reports concurrent
    entries — one signing context, several conversations interleaved through it."""
    results = run_many("server-a", 8)
    assert len(stub) == 1, f"expected one session for one server, got {len(stub)}"
    session = stub[0]
    assert session.calls == 8, "not every command ran"
    assert session.concurrent_entries == 0, (
        f"the session was entered concurrently {session.concurrent_entries} times — "
        f"two NTLM conversations sharing one signing context is what produces "
        f"'invalid MIC'")
    for out, err, code in results:
        assert (out, code) == ("ok", 0), (out, err, code)


def test_one_session_is_built_per_server_even_under_a_burst(stub):
    """`_get_session` was a check-then-act: two threads could both find nothing, both build
    a session, and one would be handed out and then silently orphaned — replaced in the
    cache while a command was still running on it."""
    run_many("server-b", 8)
    assert len(stub) == 1, (
        f"{len(stub)} sessions were built for one server — the second overwrites the first "
        f"in the cache while the first is still in use")


# ── and the thing a global lock would break ──────────────────────────────────

def test_two_servers_still_run_at_the_same_time(stub):
    """The serialisation must be PER SERVER. One lock for the whole service would make a
    slow Windows box hold up every other one — turning a correctness fix into an outage.

    Timed rather than asserted structurally: eight commands at 50 ms each take ~400 ms
    serialised and ~200 ms when the two servers overlap.
    """
    async def go():
        await asyncio.gather(*[
            w.execute(sid, "host", 5985, "Administrator", "password", "enc", "cmd")
            for sid in ("server-c", "server-d") for _ in range(4)
        ])

    t0 = time.monotonic()
    asyncio.run(go())
    elapsed = time.monotonic() - t0

    assert len(stub) == 2, "each server needs its own session"
    assert elapsed < 0.35, (
        f"took {elapsed:.2f}s — two servers were serialised against each other; "
        f"4 commands x 50ms per server should overlap to ~0.2s, not ~0.4s")


def test_a_failure_drops_only_that_servers_session(stub, monkeypatch):
    """A broken session is evicted so the next command rebuilds it. Under the old code that
    `pop` could remove a session another thread had just built for the same server."""
    class _Angry(_StubSession):
        def run_ps(self, script):
            raise RuntimeError("connection reset")

    def _make(host, port, username, credential):
        s = _Angry()
        stub.append(s)
        return s

    monkeypatch.setattr(w, "_make_session", _make)
    out, err, code = asyncio.run(
        w.execute("server-e", "h", 5985, "u", "password", "enc", "cmd"))
    assert code == 1 and "connection reset" in err
    assert "server-e" not in w._sessions, "a broken session was left in the cache"


# ── why a threading lock and not an asyncio one ──────────────────────────────

def test_it_still_works_across_separate_event_loops(stub):
    """This is the Celery worker, exactly: `playbook_tasks` calls `asyncio.run()` PER TASK,
    so the second task runs on a brand-new event loop in the same process.

    A module-level `asyncio.Lock` is bound to the loop that first awaited it and raises
    `RuntimeError: ... is bound to a different event loop` on every task after the first —
    which would break the Windows playbook path this exists to protect. A threading lock
    does not care which loop is calling.
    """
    for _ in range(3):                      # three "tasks", three loops, one process
        out, err, code = asyncio.run(
            w.execute("server-f", "h", 5985, "u", "password", "enc", "cmd"))
        assert (out, code) == ("ok", 0), f"failed on a fresh event loop: {err}"
    assert len(stub) == 1, "the cached session should survive across loops"


def test_asyncio_run_matches_how_celery_actually_calls_this():
    """The claim above is only worth anything if `playbook_tasks` really does that. Read it,
    so this stops being an assumption the day someone changes it."""
    import inspect

    from app.workers import playbook_tasks

    src = inspect.getsource(playbook_tasks)
    assert "asyncio.run(" in src, (
        "playbook_tasks no longer creates its own event loop — the reason this module uses "
        "a threading lock instead of an asyncio one may no longer hold; re-check before "
        "changing it")


# ── no unguarded way in ──────────────────────────────────────────────────────

def test_nothing_reaches_a_session_without_holding_its_lock():
    """The guard belongs at the rule, not at each call site.

    Three callers of `ssh_service._get_client` quietly skipped host-key verification because
    it was an optional argument somebody could forget. The same shape applies here: a new
    function that reads `_sessions` directly would run outside the lock and nothing would
    say so. `_session_for` hands out the session and the lock together; this fails if any
    other function touches the cache.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(w))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        names = [n.id for n in ast.walk(node) if isinstance(n, ast.Name)]
        if "_sessions" in names and node.name not in {"_session_for", "close"}:
            offenders.append(node.name)

    assert offenders == [], (
        f"{offenders} reach the session cache directly, outside the per-server lock. "
        f"Go through `_session_for`, which hands out the session and its lock together.")

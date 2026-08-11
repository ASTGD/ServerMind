"""Both doors into the servers table must look at what they just added.

The cloud import wrote a row and never connected. That reads like a cosmetic gap — no OS, no
panel — and the serious part is invisible: it never pinned the host key, and `ssh_service`
compares only when there is something to compare against, so an imported server connected
**unverified on every connection, for ever**, and could never raise "Server identity
changed".

These tests hold the fix in place: one probe, called by both doors, and no second copy.
"""
import asyncio
import pathlib
import re

import pytest

from app.services import server_probe


class _Result:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _Db:
    def __init__(self, row=None):
        self.row = row
        self.commits = 0

    async def execute(self, _stmt):
        return _Result(self.row)

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        pass


class _Server:
    """Just the columns the probe writes."""

    def __init__(self, **over):
        self.id = over.pop("id", "srv-1")
        self.connection_type = over.pop("connection_type", "ssh")
        self.status = "unknown"
        self.fingerprint = None
        self.last_seen = None
        self.os_type = over.pop("os_type", None)
        self.os_version = None
        self.arch = None
        self.panel_type = None
        self.category = over.pop("category", "vps")
        self.__dict__.update(over)


class _TestResult:
    def __init__(self, ok=True, fingerprint=None, error=None, host_key_changed=False):
        self.ok, self.fingerprint = ok, fingerprint
        self.error, self.host_key_changed = error, host_key_changed
        self.latency_ms = 1


def _wire(monkeypatch, *, result, os_info=None, os_raises=None):
    async def fake_test(_server):
        return result

    async def fake_detect(_server):
        if os_raises:
            raise os_raises
        return os_info or {}

    monkeypatch.setattr(server_probe.connection_manager, "test_connection", fake_test)
    from app.services import metrics_service
    monkeypatch.setattr(metrics_service, "detect_os", fake_detect)


# ── the security property ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_probe_pins_the_host_key(monkeypatch):
    """Without this the pin stays NULL and every later connection skips verification."""
    _wire(monkeypatch, result=_TestResult(fingerprint="ssh-ed25519 SHA256:abc"),
          os_info={"os_type": "ubuntu"})
    server = _Server()
    await server_probe.probe(_Db(), server)

    assert server.fingerprint == "ssh-ed25519 SHA256:abc"
    assert server.status == "online"
    assert server.last_seen is not None


@pytest.mark.asyncio
async def test_a_server_we_could_not_reach_is_not_pinned(monkeypatch):
    """A pin must come from a connection that actually happened — never invented."""
    _wire(monkeypatch, result=_TestResult(ok=False, error="Connection refused"))
    server = _Server()
    await server_probe.probe(_Db(), server)

    assert server.fingerprint is None
    assert server.status == "offline"


@pytest.mark.asyncio
async def test_a_changed_host_key_is_reported_not_silently_repinned(monkeypatch):
    """Re-pinning here would erase the one signal that says the machine was replaced."""
    _wire(monkeypatch, result=_TestResult(ok=False, host_key_changed=True,
                                          fingerprint="ssh-rsa SHA256:new"))
    server = _Server()
    server.fingerprint = "ssh-rsa SHA256:old"
    await server_probe.probe(_Db(), server)

    assert server.status == "host_changed"
    assert server.fingerprint == "ssh-rsa SHA256:old"


# ── what the import used to get wrong ────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_panel_machine_is_recorded_as_one(monkeypatch):
    """A CyberPanel EC2 imported from AWS was filed as a plain VPS, while the identical
    machine added by hand was filed as a panel. The probe is what tells them apart."""
    _wire(monkeypatch, result=_TestResult(fingerprint="ssh-rsa SHA256:x"),
          os_info={"os_type": "ubuntu", "os_version": "22.04", "arch": "x86_64",
                   "panel": "cyberpanel"})
    server = _Server(category="vps")
    await server_probe.probe(_Db(), server)

    assert server.panel_type == "cyberpanel"
    assert server.category == "hosting"
    assert (server.os_type, server.os_version) == ("ubuntu", "22.04")


@pytest.mark.asyncio
async def test_a_windows_machine_never_gets_a_panel(monkeypatch):
    """`panel` is a Linux finding. Writing it on a WinRM box would offer a Control-panel
    section that cannot work there."""
    _wire(monkeypatch, result=_TestResult(fingerprint="x"),
          os_info={"os_type": "windows", "panel": "cyberpanel"})
    server = _Server(connection_type="winrm")
    await server_probe.probe(_Db(), server)

    assert server.panel_type is None
    assert server.category != "hosting"


@pytest.mark.asyncio
async def test_the_providers_guess_survives_when_we_cannot_look(monkeypatch):
    """The import records the cloud's coarse "linux". A probe that cannot reach the machine
    must leave that alone rather than replace a rough answer with none."""
    _wire(monkeypatch, result=_TestResult(ok=False, error="timed out"))
    server = _Server(os_type="linux")
    await server_probe.probe(_Db(), server)

    assert server.os_type == "linux"


@pytest.mark.asyncio
async def test_a_failing_probe_never_breaks_the_add(monkeypatch):
    """Adding a machine you cannot reach yet is normal — the firewall may not be open."""
    async def boom(_server):
        raise RuntimeError("network on fire")

    monkeypatch.setattr(server_probe.connection_manager, "test_connection", boom)
    server = _Server()
    await server_probe.probe(_Db(), server)          # must not raise

    assert server.status == "unknown"


@pytest.mark.asyncio
async def test_os_detect_failing_still_leaves_the_pin_and_the_status(monkeypatch):
    """Detection is the bonus; the connection already told us the two things that matter.

    And it must leave alone what it could not improve on: writing an empty result here would
    blank the cloud's "linux" and leave the row knowing LESS than before we looked.
    """
    _wire(monkeypatch, result=_TestResult(fingerprint="ssh-rsa SHA256:y"),
          os_raises=RuntimeError("no shell"))
    server = _Server(os_type="linux")
    await server_probe.probe(_Db(), server)

    assert server.status == "online"
    assert server.fingerprint == "ssh-rsa SHA256:y"
    assert server.os_type == "linux"


# ── importing many at once ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_probe_many_never_opens_more_than_the_cap(monkeypatch):
    """Fifty simultaneous SSH connections from one address is what a brute-force looks
    like, and fail2ban is on many of these machines — including by our own playbook."""
    live = 0
    peak = 0

    async def counting_probe(_db, _server):
        nonlocal live, peak
        live += 1
        peak = max(peak, live)
        await asyncio.sleep(0.01)
        live -= 1

    rows = {f"id-{i}": _Server(id=f"id-{i}") for i in range(20)}
    monkeypatch.setattr(server_probe, "probe", counting_probe)
    monkeypatch.setattr(server_probe, "AsyncSessionLocal", None, raising=False)

    class _Session:
        def __init__(self, sid):
            self.sid = sid

        async def __aenter__(self):
            return _Db(rows[self.sid])

        async def __aexit__(self, *_):
            return False

    # The session factory is looked up per task; hand each one the row it asks for.
    import app.database as database
    order = iter(rows)
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _Session(next(order)))

    await server_probe.probe_many(list(rows))

    assert peak <= server_probe.CONCURRENCY, f"opened {peak} at once"
    # A SECOND, fixed ceiling. Checking only against the constant is self-referential: raise
    # CONCURRENCY to 100 and the bound rises with it, so the test can never fail on the one
    # thing it exists to prevent. This number does not move.
    assert peak <= 10, f"opened {peak} connections at once — that reads as a brute-force"
    assert peak < len(rows), "the semaphore is not bounding anything"
    assert peak > 1, "the whole point is that they overlap"


@pytest.mark.asyncio
async def test_one_unreachable_machine_does_not_stop_the_others(monkeypatch):
    """An import of twenty must not be abandoned because the third one is off."""
    done = []

    async def flaky(_db, server):
        if server.id == "id-2":
            raise RuntimeError("that one is off")
        done.append(server.id)

    rows = {f"id-{i}": _Server(id=f"id-{i}") for i in range(5)}
    monkeypatch.setattr(server_probe, "probe", flaky)

    class _Session:
        def __init__(self, sid):
            self.sid = sid

        async def __aenter__(self):
            return _Db(rows[self.sid])

        async def __aexit__(self, *_):
            return False

    import app.database as database
    order = iter(rows)
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _Session(next(order)))

    await server_probe.probe_many(list(rows))       # must not raise

    assert len(done) == 4


# ── the structural rule: there is only ONE probe ─────────────────────────────

ROUTERS = pathlib.Path(__file__).resolve().parent.parent / "app" / "routers"


def _code(path: pathlib.Path) -> str:
    """The file with comments and docstrings stripped, so prose about a rule can never be
    mistaken for the rule itself — the mistake a `pgrep`-in-a-comment assertion already made
    once in this codebase."""
    text = path.read_text()
    text = re.sub(r'"""(?:.|\n)*?"""', "", text)
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("#"))


def test_no_router_pins_a_fingerprint_for_a_new_server():
    """`create_server` and the import must not each carry their own copy of this.

    A copy is exactly how the two doors drifted, and the thing that drifted away was host-key
    verification. The pin is written in `server_probe` and in the customer's explicit
    "trust the new key" action — nowhere else.
    """
    writers = []
    for path in ROUTERS.glob("*.py"):
        for line in _code(path).splitlines():
            # The right-hand side is tested in Python rather than with a lookahead: a
            # `\s*(?!None)` backtracks to zero spaces and then happily matches " None",
            # which is how the first version of this test passed while proving nothing.
            m = re.search(r"\.fingerprint\s*=(?!=)(.*)", line)
            if m and m.group(1).strip() not in ("None", ""):
                writers.append(f"{path.name}: {line.strip()}")

    # servers.py keeps two, and both are the SAME deliberate action: /test's trust-on-first-
    # use, and /trust-key clearing then re-pinning after the customer says it is a new box.
    assert all(w.startswith("servers.py") for w in writers), writers
    assert len(writers) <= 3, f"a third door started pinning its own way:\n" + "\n".join(writers)


def test_only_the_probe_decides_what_detect_os_means():
    """Three places used to copy "write these fields, and a panel changes what this IS".

    One of them forgetting the panel line is how a CyberPanel machine ends up with no
    Control-panel section, which is precisely what the import did.
    """
    offenders = []
    for path in ROUTERS.glob("*.py"):
        body = _code(path)
        if "detect_os" in body and "server_probe.record_os" not in body:
            offenders.append(path.name)
    assert offenders == [], f"these read detect_os without the shared recorder: {offenders}"


def test_the_cloud_import_actually_runs_the_probe():
    """The rule is worth nothing if the second door simply never calls it."""
    body = _code(ROUTERS / "cloud_accounts.py")
    assert "server_probe.probe_many" in body
    assert "background.add_task" in body, "probing inline would hold the request open"


def test_the_import_does_not_hardcode_a_category():
    """`category="windows" if ... else "vps"` was the visible half of the drift."""
    body = _code(ROUTERS / "cloud_accounts.py")
    assert "server_probe.infer_category" in body
    assert not re.search(r'category\s*=\s*"', body), "the label is inferred, never typed"

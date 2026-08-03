"""The host-key pin, and the one way it was being bypassed.

Found live, and the symptom was the giveaway: the owner rebuilt a test server and the app
did NOT offer "trust the new key" the way it had before. It went on reporting the server
online and collecting metrics from a machine whose host key no longer matched the pinned
one — the exact thing the pin exists to refuse.

The cause was not the check. `_get_client` refuses correctly on a fresh connect. It was
that **three callers never passed the pin at all** — the SFTP path, the interactive
terminal, and the shell opener — so for them verification was skipped, and worse, the
unverified connection went into the SHARED pool. Every later caller got it back and skipped
verification too, because reusing a pooled connection deliberately does not re-verify.

So which path happened to connect first decided whether the whole app noticed. That is why
it worked the previous time and not this time.
"""
import inspect

import pytest

from app.services import file_service, ssh_service


def test_the_pin_cannot_be_omitted_by_accident():
    """Keyword-only and no default: a caller that forgets it now fails loudly at the call
    instead of silently connecting to anything that answers.

    This is the fix that matters. The three offenders were all "forgot an optional
    argument", which is invisible in review and invisible at runtime.
    """
    sig = inspect.signature(ssh_service._get_client)
    param = sig.parameters["expected_fingerprint"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty, (
        "a default makes skipping verification the easy path again")


def test_every_caller_passes_it():
    """The compiler cannot see across modules here, so this walks the real call sites.

    Asserted on the SOURCE deliberately: the property is "no code path reaches the
    connection factory without a pin", and that is a fact about the callers, not about any
    single run.
    """
    import pathlib

    root = pathlib.Path(ssh_service.__file__).parent.parent
    offenders = []
    for path in root.rglob("*.py"):
        text = path.read_text()
        if "_get_client(" not in text:
            continue
        # Every call, with its arguments, however it is wrapped across lines.
        for chunk in text.split("_get_client(")[1:]:
            if chunk.lstrip().startswith(("\n", "server_id: str")):
                continue          # the definition itself
            # Balance the brackets: the call spans lines and contains str(server.id),
            # so stopping at the first ")" reads only half the arguments and calls a
            # correct caller an offender.
            depth, end = 1, len(chunk)
            for i, ch in enumerate(chunk):
                if ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        end = i
                        break
            call = chunk[:end]
            if "expected_fingerprint" not in call:
                offenders.append(f"{path.name}: _get_client({call.strip()[:60]}…")
    assert not offenders, "these connect without verifying identity:\n" + "\n".join(offenders)


def test_the_sftp_path_passes_the_servers_pin():
    """The specific offender. It shares the pool with everything else, so its unverified
    connection became everybody's unverified connection."""
    source = inspect.getsource(file_service._get_sftp)
    assert "expected_fingerprint=server.fingerprint" in source


def test_the_terminal_passes_it_too():
    """A terminal is the last place to skip this — it is where somebody types a password
    into what they believe is their own server."""
    sig = inspect.signature(ssh_service.open_shell)
    assert "expected_fingerprint" in sig.parameters


# ── The pool must not hand out a connection verified against a different pin ──

class _FakeTransport:
    def __init__(self, active=True):
        self._active = active

    def is_active(self):
        return self._active


class _FakeClient:
    def __init__(self, active=True):
        self._transport = _FakeTransport(active)
        self.closed = False

    def get_transport(self):
        return self._transport

    def close(self):
        self.closed = True


def _pooled(monkeypatch, pooled_pin, asked_pin):
    """Put a connection in the pool under one pin and ask for it under another."""
    made = {}

    def _fake_make(host, port, username, auth_type, credential, keytype=None):
        made["called"] = True
        return _FakeClient(), "SHA256:FRESH", "ssh-ed25519"

    monkeypatch.setattr(ssh_service, "_make_client", _fake_make)
    client = _FakeClient()
    ssh_service._pool["srv"] = (client, pooled_pin)
    try:
        try:
            ssh_service._get_client("srv", "h", 22, "root", "password", "x",
                                    expected_fingerprint=asked_pin)
        except ssh_service.HostKeyMismatch:
            pass
        return made.get("called", False), client
    finally:
        ssh_service._pool.pop("srv", None)


def test_a_connection_opened_without_a_pin_is_not_reused_for_a_pinned_caller(monkeypatch):
    """The actual hole. One caller connected with no pin, and every pinned caller after it
    was handed that unverified connection and skipped its own check."""
    reconnected, old = _pooled(monkeypatch, None, "SHA256:PINNED")
    assert reconnected, "an unverified pooled connection was reused for a pinned caller"
    assert old.closed, "the unverified connection was left open in the pool"


def test_a_connection_verified_against_the_same_pin_is_reused(monkeypatch):
    """Pooling still has to work, or every call pays for a handshake."""
    reconnected, _ = _pooled(monkeypatch, "SHA256:PINNED", "SHA256:PINNED")
    assert not reconnected


def test_a_dead_connection_is_replaced(monkeypatch):
    def _fake_make(*_a, **_k):
        return _FakeClient(), "SHA256:FRESH", "ssh-ed25519"

    monkeypatch.setattr(ssh_service, "_make_client", _fake_make)
    ssh_service._pool["srv"] = (_FakeClient(active=False), "SHA256:PINNED")
    try:
        with pytest.raises(ssh_service.HostKeyMismatch):
            ssh_service._get_client("srv", "h", 22, "root", "password", "x",
                                    expected_fingerprint="SHA256:PINNED")
    finally:
        ssh_service._pool.pop("srv", None)

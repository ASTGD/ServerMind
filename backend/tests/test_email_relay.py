"""Email delivery through our own mail server.

These drive a REAL SMTP conversation against a throwaway server in this process, because
every bug here was in the protocol handshake: an unconditional STARTTLS against a relay
that does not offer it, and an unconditional login with no credentials to log in with. A
mocked smtplib accepts both happily and proves nothing.

The server is raw sockets rather than stdlib `smtpd`, which was removed in Python 3.12 —
using it meant these tests silently SKIPPED on 3.13 and the local-relay path went unproven.
"""
from __future__ import annotations

import asyncio
import socket
import threading
from email import message_from_string

import pytest

from app.config import settings
from app.services import notification_service as ns


class FakeRelay:
    """A send-only mail server, like a Postfix bound to localhost.

    Deliberately advertises NO STARTTLS and offers NO AUTH — precisely the shape that used
    to make our own mail server unusable.
    """

    def __init__(self, *, offer_starttls: bool = False) -> None:
        self.offer_starttls = offer_starttls
        self.messages: list[str] = []
        self.commands: list[str] = []
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        try:
            conn, _ = self._sock.accept()
        except OSError:
            return
        with conn:
            f = conn.makefile("rwb")
            f.write(b"220 fake.local ESMTP\r\n")
            f.flush()
            while True:
                line = f.readline()
                if not line:
                    return
                text = line.decode("utf-8", "replace").strip()
                self.commands.append(text)
                upper = text.upper()

                if upper.startswith("EHLO") or upper.startswith("HELO"):
                    caps = [b"250-fake.local", b"250-SIZE 10240000"]
                    if self.offer_starttls:
                        caps.append(b"250-STARTTLS")
                    caps.append(b"250 HELP")
                    f.write(b"\r\n".join(caps) + b"\r\n")
                elif upper.startswith(("MAIL FROM", "RCPT TO")):
                    f.write(b"250 OK\r\n")
                elif upper == "DATA":
                    f.write(b"354 End data with <CR><LF>.<CR><LF>\r\n")
                    f.flush()
                    body: list[str] = []
                    while True:
                        chunk = f.readline()
                        if not chunk or chunk in (b".\r\n", b".\n"):
                            break
                        body.append(chunk.decode("utf-8", "replace"))
                    self.messages.append("".join(body))
                    f.write(b"250 Queued\r\n")
                elif upper == "QUIT":
                    f.write(b"221 Bye\r\n")
                    f.flush()
                    return
                else:
                    f.write(b"250 OK\r\n")
                f.flush()

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


@pytest.fixture
def relay(monkeypatch):
    """Point the sender at a throwaway local relay that has no credentials."""
    r = FakeRelay()
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "SMTP_PORT", r.port)
    monkeypatch.setattr(settings, "SMTP_USER", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    monkeypatch.setattr(settings, "EMAIL_FROM", "alerts@serverally.firevps.net")
    yield r
    r.close()


def test_our_own_server_needs_no_username_or_password(relay):
    """The bug that made our own mail server unusable: credentials were mandatory."""
    assert ns.email_relay() == "127.0.0.1", (
        "a loopback relay must count as configured even with no credentials"
    )
    asyncio.run(ns.send_email("owner@example.com", "Disk is filling up", "78% used"))

    assert len(relay.messages) == 1, (
        f"the message should have reached the relay; conversation was {relay.commands}"
    )
    msg = message_from_string(relay.messages[0])
    assert msg["Subject"] == "Disk is filling up"
    assert msg["To"] == "owner@example.com"
    assert msg["From"] == "alerts@serverally.firevps.net"


def test_no_auth_is_attempted_when_there_are_no_credentials(relay):
    """An unconditional login() is a hard failure against a relay with no AUTH."""
    asyncio.run(ns.send_email("o@example.com", "s", "b"))
    assert not any(c.upper().startswith("AUTH") for c in relay.commands), (
        f"should not try to authenticate: {relay.commands}"
    )


def test_starttls_is_not_attempted_when_the_relay_does_not_offer_it(relay):
    """The other half of the same bug — starttls() raises if unadvertised."""
    asyncio.run(ns.send_email("o@example.com", "s", "b"))
    assert not any(c.upper().startswith("STARTTLS") for c in relay.commands), (
        f"should not offer to upgrade a connection the server cannot upgrade: {relay.commands}"
    )


def test_starttls_is_used_when_the_relay_does_offer_it(monkeypatch):
    """Conditional, not disabled: a relay advertising STARTTLS should still get it.

    The handshake itself cannot complete without a real certificate, so the assertion is
    that we ASKED — which is what distinguishes "conditional" from "switched off".
    """
    r = FakeRelay(offer_starttls=True)
    monkeypatch.setattr(settings, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(settings, "SMTP_PORT", r.port)
    monkeypatch.setattr(settings, "SMTP_USER", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    try:
        with pytest.raises(Exception):  # noqa: B017, PT011 — TLS cannot complete here
            asyncio.run(ns.send_email("o@example.com", "s", "b"))
        assert any(c.upper().startswith("STARTTLS") for c in r.commands), (
            f"a relay advertising STARTTLS should be upgraded: {r.commands}"
        )
    finally:
        r.close()


def test_html_and_plain_both_survive_the_send(relay):
    asyncio.run(ns.send_email("o@example.com", "Report", "plain body",
                              html="<p>rich body</p>"))
    msg = message_from_string(relay.messages[0])
    assert msg.is_multipart()
    parts = {p.get_content_type(): p.get_payload() for p in msg.walk() if not p.is_multipart()}
    assert "plain body" in parts["text/plain"]
    assert "rich body" in parts["text/html"]


def test_a_remote_relay_without_credentials_is_not_usable(monkeypatch):
    """Unchanged for a real provider: no keys means no delivery."""
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setattr(settings, "SMTP_USER", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    assert ns.email_relay() is None


def test_a_remote_relay_with_credentials_is_usable(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.postmarkapp.com")
    monkeypatch.setattr(settings, "SMTP_USER", "token")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "token")
    assert ns.email_relay() == "smtp.postmarkapp.com"


def test_no_host_at_all_is_not_usable(monkeypatch):
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    assert ns.email_relay() is None


def test_undeliverable_email_is_loud_but_does_not_raise(monkeypatch, caplog):
    """Callers treat email as best-effort so this must not throw — but it must be LOUD.

    A warning is why nobody noticed production had no mail configured at all.
    """
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    with caplog.at_level("ERROR"):
        asyncio.run(ns.send_email("o@example.com", "Server compromised", "act now"))
    assert any(r.levelname == "ERROR" for r in caplog.records), (
        "an undeliverable alert must be logged at ERROR, not swallowed as routine"
    )


def test_every_message_carries_a_date_and_message_id(relay):
    """Mail without these is scored as suspicious, and ours had `message-id=<>`.

    Caught by reading the relay's own log during a real send, not by inspection.
    """
    asyncio.run(ns.send_email("o@example.com", "Malware detected", "body"))
    msg = message_from_string(relay.messages[0])
    assert msg["Date"], "a message with no Date header looks like spam"
    mid = msg["Message-ID"]
    assert mid and mid.strip("<>"), f"Message-ID must not be empty: {mid!r}"
    assert "serverally.firevps.net" in mid, (
        f"Message-ID domain should match the signing domain so DKIM alignment holds: {mid}"
    )

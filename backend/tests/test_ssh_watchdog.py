"""Watchdog (Update 16, Phase A): a streamed command that goes silent too long
raises CommandStalled; a command that finishes normally does not.

Uses a fake Paramiko channel so the test is deterministic and needs no server.
"""
import socket

import pytest

from app.config import settings
from app.services import ssh_service
from app.services.ssh_service import CommandStalled


class _Chan:
    """Fake channel. Emits one line, then either stays silent forever (stall) or
    reports the command finished (clean completion)."""

    def __init__(self, *, finish_after_line: bool) -> None:
        self._recv_calls = 0
        self._finish = finish_after_line

    def set_combine_stderr(self, _v): ...
    def exec_command(self, _cmd): ...
    def settimeout(self, _t): ...
    def recv_ready(self): return False
    def close(self): ...
    def recv_exit_status(self): return 0

    def exit_status_ready(self):
        # Only "finish" after the first line has been delivered.
        return self._finish and self._recv_calls >= 1

    def recv(self, _n):
        self._recv_calls += 1
        if self._recv_calls == 1:
            return b"START\n"
        raise socket.timeout()  # no more data


class _Transport:
    def __init__(self, chan): self._chan = chan
    def open_session(self): return self._chan


class _Client:
    def __init__(self, chan): self._chan = chan
    def get_transport(self): return _Transport(self._chan)


def _patch(monkeypatch, chan):
    monkeypatch.setattr(ssh_service, "decrypt", lambda _c: "cred")
    monkeypatch.setattr(ssh_service, "_get_client", lambda *a, **k: _Client(chan))


async def _drain(cmd_args):
    lines = []
    async for line in ssh_service.execute_stream(*cmd_args):
        lines.append(line)
    return lines


_ARGS = ("sid", "host", 22, "user", "password", "enc", "cmd")


async def test_stalls_on_silence(monkeypatch):
    monkeypatch.setattr(settings, "SSH_IDLE_TIMEOUT_SECONDS", 1)
    _patch(monkeypatch, _Chan(finish_after_line=False))

    lines = []
    with pytest.raises(CommandStalled) as ei:
        async for line in ssh_service.execute_stream(*_ARGS):
            lines.append(line)

    assert lines == ["START"]
    assert "START" in ei.value.last_output
    assert ei.value.reason == "idle"


async def test_no_false_stall_when_command_finishes(monkeypatch):
    monkeypatch.setattr(settings, "SSH_IDLE_TIMEOUT_SECONDS", 1)
    _patch(monkeypatch, _Chan(finish_after_line=True))

    lines = await _drain(_ARGS)  # must not raise
    assert lines == ["START"]

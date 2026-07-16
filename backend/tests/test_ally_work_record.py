"""Ally's work record — how Ally remembers the work IT did (Area D / BUG-001 follow-up).

BUG-001: Ally quarantined files on a site in chat, then the next day couldn't tell its
own quarantine folder from an unknown and nearly restored a 10-month-old backup over a
live government site. The prompt fix asked Ally to `remember` its cleanups — but a
prompt is a request, not a guarantee. These are the two code-level layers under it:

- ``ai_context_service._actions_done`` — the server profile now shows what Ally
  CHANGED (not just what the user asked), derived deterministically from command_logs.
- ``memory_service.record_action`` — a HIGH-RISK change that succeeded is written to
  long-term memory automatically, with no model cooperation.

Both are deliberately narrow: ally_memories is capped and injected into every prompt,
so routine work must NOT flood it (that would evict the curated facts).
Offline: no DB, no SSH, no API.
"""
from __future__ import annotations

import pytest

from app.models.command_log import CommandLog
from app.services import ai_context_service as ctx
from app.services import memory_service


def _log(commands) -> CommandLog:
    log = CommandLog()
    log.commands = commands
    return log


# ── Layer A: what Ally CHANGED (ai_context_service._actions_done) ─────────────

def test_read_only_command_is_not_recorded_as_work():
    """Ally LOOKING is not Ally DOING — a probe must not show up as a change."""
    assert ctx._actions_done(_log([
        {"cmd": "ls -la /var/www", "description": "List the web root"},
        {"cmd": "df -h", "description": "Check disk usage"},
    ])) == []


def test_mutating_command_is_recorded_with_its_description():
    """The exact BUG-001 shape: a quarantine must be recallable next conversation,
    and the plain-language description (with the path) is what Ally needs."""
    done = ctx._actions_done(_log([
        {"cmd": "ls /home/site", "description": "Look at the site"},          # ignored
        {"cmd": "mv /home/site/shell.php /root/quarantine_20260714/",
         "description": "Quarantine the webshell into /root/quarantine_20260714"},
    ]))
    assert done == ["Quarantine the webshell into /root/quarantine_20260714"]


def test_action_falls_back_to_the_raw_command_when_undescribed():
    done = ctx._actions_done(_log([{"cmd": "systemctl restart nginx"}]))
    assert done == ["systemctl restart nginx"]


def test_secret_looking_action_is_dropped():
    """A raw cmd can carry a credential; the profile is injected into the prompt, so
    anything that smells like a secret must never reach it."""
    assert ctx._actions_done(_log([
        {"cmd": "mysql -u root -p'hunter2Zx' -e 'drop database x'",
         "description": "password is hunter2Zx"},
    ])) == []


def test_actions_are_capped_per_log():
    cmds = [{"cmd": f"rm -f /tmp/f{i}", "description": f"Delete file {i}"} for i in range(10)]
    assert len(ctx._actions_done(_log(cmds))) == ctx._MAX_ACTIONS_PER_LOG


@pytest.mark.parametrize("commands", [None, [], ["not-a-dict"], [{}], [{"cmd": ""}]])
def test_malformed_commands_never_crash(commands):
    assert ctx._actions_done(_log(commands)) == []


# ── Layer B: critical changes auto-persist (memory_service.record_action) ─────

class _Rec:
    """Captures what record_action would persist, without touching the DB."""

    def __init__(self) -> None:
        self.saved: list[dict] = []

    async def __call__(self, _db, *, user_id, remember, server_id):  # noqa: D401
        self.saved.append(remember)


@pytest.fixture
def rec(monkeypatch) -> _Rec:
    r = _Rec()
    monkeypatch.setattr(memory_service, "save_from_ai", r)
    return r


_HIGH_QUARANTINE = {
    "cmd": "mv /home/site/shell.php /root/quarantine_20260714/",
    "description": "Quarantine the webshell into /root/quarantine_20260714",
    "risk_level": "high",
}


async def test_high_risk_change_is_recorded_without_the_model(rec):
    """The floor under the prompt: no `remember` field needed — the note is written
    from the plan itself."""
    await memory_service.record_action(
        None, user_id="u1", server_id="s1", commands=[_HIGH_QUARANTINE], status="success")
    assert len(rec.saved) == 1
    note = rec.saved[0]["note"]
    assert rec.saved[0]["kind"] == "fact"
    assert "ServerAlly did this on" in note
    assert "/root/quarantine_20260714" in note   # the PATH is the point (BUG-001)


async def test_only_one_note_per_action_not_one_per_command(rec):
    await memory_service.record_action(
        None, user_id="u1", server_id="s1",
        commands=[_HIGH_QUARANTINE, dict(_HIGH_QUARANTINE, description="Quarantine another shell")],
        status="success")
    assert len(rec.saved) == 1


@pytest.mark.parametrize("status", ["failed", "partial", "blocked", None])
async def test_only_successful_changes_are_recorded(rec, status):
    """Never claim to have done something that didn't actually land."""
    await memory_service.record_action(
        None, user_id="u1", server_id="s1", commands=[_HIGH_QUARANTINE], status=status)
    assert rec.saved == []


@pytest.mark.parametrize("risk", ["low", "medium", "", None])
async def test_routine_work_does_not_flood_long_term_memory(rec, risk):
    """ally_memories is capped and rides in every prompt — only genuinely critical,
    lasting changes may persist. Routine work is recalled from command_logs instead."""
    await memory_service.record_action(
        None, user_id="u1", server_id="s1",
        commands=[dict(_HIGH_QUARANTINE, risk_level=risk)], status="success")
    assert rec.saved == []


async def test_high_risk_but_read_only_is_not_a_change(rec):
    """A cautious model can mark a mere look 'high' — it still changed nothing."""
    await memory_service.record_action(
        None, user_id="u1", server_id="s1",
        commands=[{"cmd": "grep -r password /etc", "description": "Search configs",
                   "risk_level": "high"}],
        status="success")
    assert rec.saved == []


@pytest.mark.parametrize("commands", [None, "nope", [], [{"risk_level": "high"}]])
async def test_record_action_is_best_effort(rec, commands):
    """Malformed input must never raise — memory can never break the chat."""
    await memory_service.record_action(
        None, user_id="u1", server_id="s1", commands=commands, status="success")
    assert rec.saved == []

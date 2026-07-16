"""Mission verification gate — the adversarial check that a self-declared 'done'
mission is REALLY done before it can report success.

Two layers, both offline (no API, no SSH):
- verify_mission parsing/normalisation (a bad verdict must default to the SAFE
  outcome 'unverified', never a false 'confirmed').
- _verify_mission_complete engine behaviour with a fake socket + mocked model/exec:
  the SECURITY-CRITICAL property is that a verification check may only OBSERVE —
  a mutating check the verifier proposes is SKIPPED, never executed — and a goal
  that can't be proven resolves to 'unverified' (an honest, non-success finish).
"""
from __future__ import annotations

import json

import pytest

from app.models.server import Server
from app.services import ai_service
from app.websocket import terminal as ws


def _server(sid: str, name: str) -> Server:
    s = Server(
        name=name, host="h", port=22, username="root", auth_type="password",
        connection_type="ssh", panel_type=None, encrypted_cred="x",
        os_type="ubuntu", shell="bash",
    )
    s.id = sid
    return s


class _FakeWS:
    """Captures every frame the engine sends so we can assert on the timeline."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_text(self, raw: str) -> None:
        self.sent.append(json.loads(raw))


async def _run_gate(monkeypatch, verify_returns, executed_sink=None):
    """Drive _verify_mission_complete with a scripted sequence of verifier replies
    (verify_returns) and a recording _mission_execute. Returns (verdict, reason,
    gathered, sent_frames)."""
    srv = _server("srv-1", "TestServer")
    roster = [srv]
    roster_by_id = {"srv-1": srv}

    calls = {"i": 0}

    async def fake_verify(*_a, **_k):
        i = calls["i"]
        calls["i"] += 1
        # Repeat the last scripted reply if the engine asks more times than scripted.
        return verify_returns[min(i, len(verify_returns) - 1)]

    async def fake_exec(server, cmd):
        if executed_sink is not None:
            executed_sink.append(cmd)
        return 0, "ok-output", ""

    monkeypatch.setattr(ai_service, "verify_mission", fake_verify)
    monkeypatch.setattr(ws, "_mission_execute", fake_exec)

    fake_ws = _FakeWS()
    verdict, reason, gathered = await ws._verify_mission_complete(
        fake_ws, home_server=srv, roster=roster, roster_by_id=roster_by_id,
        goal="prove it", skill=None, steps=[], user_language="en", home_id="srv-1", budget=20,
    )
    return verdict, reason, gathered, fake_ws.sent


# ── verify_mission normalisation (parsing safety) ─────────────────────────────

@pytest.mark.parametrize("payload,expected_verdict", [
    ({"verdict": "confirmed", "checks": [], "reason": "ok"}, "confirmed"),
    ({"verdict": "unverified", "checks": [], "reason": "no"}, "unverified"),
    ({"verdict": "maybe", "checks": [], "reason": "?"}, "unverified"),   # bad → safe
    ({"reason": "missing verdict"}, "unverified"),                        # absent → safe
    ({"verdict": "confirmed", "checks": "nope"}, "confirmed"),            # checks coerced to []
])
async def test_verify_mission_normalises(monkeypatch, payload, expected_verdict):
    async def fake_complete(*_a, **_k):
        return json.dumps(payload)
    monkeypatch.setattr(ai_service.llm_service, "complete", fake_complete)
    out = await ai_service.verify_mission("goal", [_server("s", "S")], [], home_id="s")
    assert out["verdict"] == expected_verdict
    assert isinstance(out["checks"], list)


# ── Engine gate behaviour ─────────────────────────────────────────────────────

async def test_confirmed_immediately_no_checks(monkeypatch):
    executed: list[str] = []
    verdict, reason, gathered, sent = await _run_gate(
        monkeypatch,
        [{"verdict": "confirmed", "checks": [], "reason": "site returns 200"}],
        executed,
    )
    assert verdict == "confirmed"
    assert reason == "site returns 200"
    assert gathered == [] and executed == []  # nothing to run — the executor's evidence sufficed


async def test_runs_read_only_check_then_confirms(monkeypatch):
    executed: list[str] = []
    verdict, _reason, gathered, sent = await _run_gate(
        monkeypatch,
        [
            {"verdict": "unverified", "reason": "need proof",
             "checks": [{"server_id": "srv-1", "cmd": "curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/", "why": "site up?"}]},
            {"verdict": "confirmed", "checks": [], "reason": "confirmed 200"},
        ],
        executed,
    )
    assert verdict == "confirmed"
    assert executed == ["curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1/"]
    # The check is in the transcript and streamed as a verifying step.
    assert any(s.get("verifying") and s.get("type") == "mission_step" for s in sent)
    assert len(gathered) == 1 and gathered[0]["cmd"].startswith("curl")


async def test_mutating_verification_check_is_never_executed(monkeypatch):
    """SECURITY-CRITICAL: if the verifier proposes a state-changing 'check', the
    engine must SKIP it (never run it) — verification only observes."""
    executed: list[str] = []
    verdict, _reason, gathered, sent = await _run_gate(
        monkeypatch,
        [
            {"verdict": "unverified", "reason": "need to be sure",
             "checks": [{"server_id": "srv-1", "cmd": "rm -rf /var/www/html", "why": "clean it"}]},
            {"verdict": "unverified", "checks": [], "reason": "still not sure"},
        ],
        executed,
    )
    assert executed == []  # the mutating command was NEVER run
    assert verdict == "unverified"
    # It's recorded as skipped so the verifier can see it wasn't run.
    assert any("read-only" in (g.get("note") or "") for g in gathered)


async def test_unprovable_goal_resolves_unverified(monkeypatch):
    """If the verifier can never confirm (keeps asking, never satisfied), the gate
    finishes 'unverified' — an honest non-success, never a false 'confirmed'."""
    verdict, _reason, _gathered, _sent = await _run_gate(
        monkeypatch,
        [{"verdict": "unverified", "reason": "cron backdoor still present",
          "checks": [{"server_id": "srv-1", "cmd": "ls /etc/cron.d/", "why": "check cron"}]}],
    )
    assert verdict == "unverified"


async def test_verifier_error_is_unverified_not_crash(monkeypatch):
    """A verifier AI error must resolve to 'unverified' with a caveat — never crash
    the mission, never silently pass."""
    async def boom(*_a, **_k):
        raise RuntimeError("model down")
    monkeypatch.setattr(ai_service, "verify_mission", boom)
    monkeypatch.setattr(ws, "_mission_execute", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("should not run")))

    srv = _server("srv-1", "S")
    fake_ws = _FakeWS()
    verdict, reason, gathered = await ws._verify_mission_complete(
        fake_ws, home_server=srv, roster=[srv], roster_by_id={"srv-1": srv},
        goal="g", skill=None, steps=[], user_language="en", home_id="srv-1", budget=20,
    )
    assert verdict == "unverified" and reason and gathered == []


# ── Wait action bounding (poll long-running work without burning the budget) ──

@pytest.mark.parametrize("raw,expected", [
    (500, (True, 300)),    # clamped down to the 5-min per-wait cap
    (0, (True, 1)),        # clamped up to the 1-second floor
    ("x", (True, 1)),      # junk -> floor, still allowed
    (30, (True, 30)),      # normal
])
def test_wait_plan_clamps_seconds(raw, expected):
    assert ws._wait_plan(raw, 0, 0) == expected


def test_wait_plan_refuses_when_budget_spent():
    # 61st wait step is refused (per-mission wait-step cap).
    assert ws._wait_plan(10, ws._WAIT_MAX_STEPS, 0)[0] is False
    # A wait that would push total sleep past the 1-hour cap is refused.
    assert ws._wait_plan(300, 0, ws._WAIT_TOTAL_MAX - 1)[0] is False
    # Within both caps -> allowed.
    assert ws._wait_plan(30, 5, 100)[0] is True


# ── Content-aware verification (task #1 / Area C) ─────────────────────────────

def test_verify_prompt_checks_page_content_not_just_status():
    """Regression guard for the live gap (panel2.firevps.net): a "cleaned"/"fixed" site
    can return HTTP 200 while serving a blank body or a PHP/Laravel error page — exactly
    what happened when a restored index.php still 500-crashed (a quarantined asset was
    missing). The verify gate must confirm the page BODY is the real site, not trust the
    status code. Pin the rule into the verifier prompt so a future edit can't drop it."""
    p = " ".join(ai_service._VERIFY_SYSTEM.lower().split())
    # A status code alone is not proof.
    assert "a 200 status is not proof" in p
    # Must fetch and read a sample of the response body.
    assert "sample of the body" in p
    # An error/blank body overrides a good status code.
    assert "no matter what the status code says" in p
    # Names the concrete error-page shapes so the verifier recognises them.
    assert "error page" in p

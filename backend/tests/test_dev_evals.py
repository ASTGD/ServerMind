"""Dev Door Phase 3 — the eval runner + case capture (the flywheel).

Properties that matter:
  * run_evals runs the whole corpus offline and reports by category (all green today).
  * A captured case is run alongside the corpus and its result comes back (red or green).
  * capture_case validates the category and secret-scrubs the input before storing.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.evals.model import SKILL_ROUTING
from app.services import dev_service


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeSession:
    """Enough of an AsyncSession for the eval-runner service (no real DB)."""

    def __init__(self, rows=()):
        self._rows = list(rows)
        self.added: list = []

    async def execute(self, _stmt):
        return _FakeResult(self._rows)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        pass

    async def refresh(self, _obj):
        pass

    async def get(self, _model, key):
        return next((r for r in self._rows if str(getattr(r, "id", None)) == str(key)), None)

    async def delete(self, obj):
        self._rows = [r for r in self._rows if r is not obj]


def _captured(**kw):
    d = dict(
        id=uuid.uuid4(), category=SKILL_ROUTING, input="install nginx",
        expected="wordpress-rescue", os="ubuntu", note=None, created_at=None,
    )
    d.update(kw)
    return SimpleNamespace(**d)


# ── scrub ──────────────────────────────────────────────────────────────────────

def test_scrub_secret_masks_credentials():
    assert "***" in dev_service.scrub_secret("mysql -u root password=hunter2 -e 'x'")
    assert "hunter2" not in dev_service.scrub_secret("connect with password: hunter2")
    assert "***" in dev_service.scrub_secret("export TOKEN=ghp_abcdefgh12345678")
    # A benign message is untouched.
    assert dev_service.scrub_secret("why is my disk full?") == "why is my disk full?"


# ── run_evals ────────────────────────────────────────────────────────────────

async def test_run_evals_corpus_all_green_no_captured():
    out = await dev_service.run_evals(_FakeSession())
    assert out["summary"]["ok"] is True
    assert out["summary"]["passed"] == out["summary"]["total"] > 100
    cats = {c["category"] for c in out["by_category"]}
    assert SKILL_ROUTING in cats and "safety-block" in cats
    assert out["failures"] == []
    assert out["captured"] == []


async def test_run_evals_includes_a_captured_failure():
    # "install nginx" matches NO skill, so expecting "wordpress-rescue" must FAIL.
    bad = _captured()
    out = await dev_service.run_evals(_FakeSession([bad]))
    assert len(out["captured"]) == 1
    cap = out["captured"][0]
    assert cap["passed"] is False and cap["got"] == "None"
    assert any(f["source"] == "captured" for f in out["failures"])
    # The corpus itself is still green — only the captured case fails.
    assert out["summary"]["ok"] is False


async def test_run_evals_captured_green_case_passes():
    good = _captured(input="my wordpress site is down with a white screen", expected="wordpress-rescue")
    out = await dev_service.run_evals(_FakeSession([good]))
    assert out["captured"][0]["passed"] is True
    assert out["summary"]["ok"] is True


# ── capture_case ─────────────────────────────────────────────────────────────

async def test_capture_case_rejects_unknown_category():
    with pytest.raises(ValueError):
        await dev_service.capture_case(
            _FakeSession(), category="bogus", input="x", expected="y"
        )


async def test_capture_case_scrubs_and_stores():
    sess = _FakeSession()
    row = await dev_service.capture_case(
        sess, category=SKILL_ROUTING,
        input="deploy with token=ghp_secretsecret12345 please",
        expected="github-deploy", os="ubuntu",
    )
    assert row in sess.added
    assert "ghp_secretsecret12345" not in row.input and "***" in row.input
    assert row.expected == "github-deploy"


async def test_delete_captured_missing_returns_false():
    assert await dev_service.delete_captured(_FakeSession(), uuid.uuid4()) is False


async def test_delete_captured_removes_row():
    row = _captured()
    sess = _FakeSession([row])
    assert await dev_service.delete_captured(sess, row.id) is True
    assert row not in sess._rows

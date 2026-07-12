"""Assistant thread hardening — per-message content is size-bounded so a single
account can't bloat the shared DB via the inline JSONB message list."""
import pytest
from pydantic import ValidationError

from app.routers.assistant import (
    MessageAppend,
    _MAX_CONTENT_CHARS,
    _MAX_DATA_CHARS,
    _within_data_cap,
)


def test_message_content_at_cap_is_accepted():
    m = MessageAppend(role="user", content="x" * _MAX_CONTENT_CHARS)
    assert len(m.content) == _MAX_CONTENT_CHARS


def test_message_content_over_cap_is_rejected():
    with pytest.raises(ValidationError):
        MessageAppend(role="user", content="x" * (_MAX_CONTENT_CHARS + 1))


def test_workspace_message_allows_empty_content_with_data():
    # A saved Workspace message (mission/output/artifact) carries no chat text — the
    # rich snapshot rides in `data`, so content defaults to "".
    m = MessageAppend(role="assistant", data={"kind": "mission", "mission": {"goal": "x"}})
    assert m.content == ""
    assert m.data == {"kind": "mission", "mission": {"goal": "x"}}


def test_within_data_cap_accepts_normal_snapshot():
    # A realistic finished-mission snapshot fits the cap and is stored.
    snapshot = {"kind": "mission", "mission": {"status": "complete", "steps": [{"cmd": "ls"}] * 40}}
    assert _within_data_cap(snapshot) is True


def test_within_data_cap_drops_oversized_snapshot():
    # A pathological blob is dropped (the chat text still saves) so one heavy transcript
    # can't bloat the shared inline JSONB thread.
    huge = {"kind": "output", "content": "x" * (_MAX_DATA_CHARS + 100)}
    assert _within_data_cap(huge) is False

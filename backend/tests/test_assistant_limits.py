"""Assistant thread hardening — per-message content is size-bounded so a single
account can't bloat the shared DB via the inline JSONB message list."""
import pytest
from pydantic import ValidationError

from app.routers.assistant import MessageAppend, _MAX_CONTENT_CHARS


def test_message_content_at_cap_is_accepted():
    m = MessageAppend(role="user", content="x" * _MAX_CONTENT_CHARS)
    assert len(m.content) == _MAX_CONTENT_CHARS


def test_message_content_over_cap_is_rejected():
    with pytest.raises(ValidationError):
        MessageAppend(role="user", content="x" * (_MAX_CONTENT_CHARS + 1))

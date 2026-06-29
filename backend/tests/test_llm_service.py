"""Multi-provider AI routing (Update 20)."""
import pytest

from app.config import settings
from app.services import llm_service


def test_resolve_anthropic_falls_back_to_legacy(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "anthropic")
    monkeypatch.setattr(settings, "AI_API_KEY", "")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setattr(settings, "AI_MODEL", "")
    monkeypatch.setattr(settings, "AI_BASE_URL", "")
    provider, key, model, base = llm_service._resolve()
    assert provider == "anthropic"
    assert key == "sk-ant-test"  # falls back to ANTHROPIC_API_KEY
    assert model  # a default model is resolved
    assert base is None


def test_resolve_openai_defaults(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "AI_API_KEY", "sk-openai")
    monkeypatch.setattr(settings, "AI_MODEL", "")
    monkeypatch.setattr(settings, "AI_BASE_URL", "")
    assert llm_service._resolve() == ("openai", "sk-openai", "gpt-4o", None)


def test_resolve_gemini_uses_compatible_base(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "gemini")
    monkeypatch.setattr(settings, "AI_API_KEY", "g-key")
    monkeypatch.setattr(settings, "AI_MODEL", "")
    monkeypatch.setattr(settings, "AI_BASE_URL", "")
    provider, key, model, base = llm_service._resolve()
    assert provider == "gemini"
    assert "generativelanguage.googleapis.com" in (base or "")


def test_resolve_servermind_uses_gateway(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "servermind")
    monkeypatch.setattr(settings, "AI_API_KEY", "sm_live_token")
    monkeypatch.setattr(settings, "AI_MODEL", "")
    monkeypatch.setattr(settings, "AI_BASE_URL", "")
    monkeypatch.setattr(settings, "AI_GATEWAY_URL", "https://gw.example/v1")
    provider, key, _model, base = llm_service._resolve()
    assert (provider, key, base) == ("servermind", "sm_live_token", "https://gw.example/v1")


async def test_complete_routes_to_anthropic(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "anthropic")
    monkeypatch.setattr(settings, "AI_API_KEY", "k")
    monkeypatch.setattr(settings, "AI_MODEL", "")
    llm_service.reset_clients()

    class FakeMessages:
        async def create(self, **kw):
            return type("Msg", (), {"content": [type("C", (), {"text": "FROM_ANTHROPIC"})()]})()

    class FakeAnthropic:
        def __init__(self, **kw):
            self.messages = FakeMessages()

    import anthropic
    monkeypatch.setattr(anthropic, "AsyncAnthropic", FakeAnthropic)

    out = await llm_service.complete("sys", "hello", max_tokens=10)
    assert out == "FROM_ANTHROPIC"
    llm_service.reset_clients()


async def test_complete_routes_to_openai(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "AI_API_KEY", "k")
    monkeypatch.setattr(settings, "AI_MODEL", "gpt-4o")
    monkeypatch.setattr(settings, "AI_BASE_URL", "")
    llm_service.reset_clients()

    class FakeCompletions:
        async def create(self, **kw):
            msg = type("M", (), {"content": "FROM_OPENAI"})()
            return type("Resp", (), {"choices": [type("Ch", (), {"message": msg})()]})()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kw):
            self.chat = FakeChat()

    import openai
    monkeypatch.setattr(openai, "AsyncOpenAI", FakeOpenAI)

    out = await llm_service.complete("sys", "hello", max_tokens=10)
    assert out == "FROM_OPENAI"
    llm_service.reset_clients()


async def test_complete_without_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "AI_PROVIDER", "openai")
    monkeypatch.setattr(settings, "AI_API_KEY", "")
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", "")
    llm_service.reset_clients()
    with pytest.raises(RuntimeError):
        await llm_service.complete("sys", "hi")

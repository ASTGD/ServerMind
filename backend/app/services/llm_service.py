"""LLM provider abstraction (Update 20 — multi-provider AI).

Routes AI calls to whichever provider the instance is configured for, so a customer
can bring their own key from the provider they trust — Anthropic (Claude), OpenAI
(GPT), Google (Gemini), or any OpenAI-compatible endpoint (Mistral, Groq, DeepSeek,
a local model, …). All of ServerMind's AI features make one shape of call — a system
prompt + a single user message → text — which this module unifies.

Anthropic goes through the ``anthropic`` SDK; everything else goes through the
``openai`` SDK (pointed at the right base URL), which speaks the OpenAI-compatible
protocol the other providers expose. SDKs are imported lazily, so the default
(Anthropic) path needs no extra packages installed.
"""
from __future__ import annotations

import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Sensible default model per provider when AI_MODEL isn't set.
_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "gemini": "gemini-1.5-pro",
}

# OpenAI-compatible base URLs for non-OpenAI providers reached via the openai SDK.
_OPENAI_COMPATIBLE_BASE = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openai": None,  # the SDK default
}

_anthropic_client = None
_openai_client = None


def _resolve() -> tuple[str, str, str, str | None]:
    """Resolve (provider, api_key, model, base_url) from config, with fallbacks to
    the legacy ANTHROPIC_* settings so existing setups keep working."""
    provider = (settings.AI_PROVIDER or "anthropic").lower()
    key = settings.AI_API_KEY or (settings.ANTHROPIC_API_KEY if provider == "anthropic" else "")
    model = settings.AI_MODEL or _DEFAULT_MODELS.get(provider) or settings.ANTHROPIC_MODEL
    base_url = settings.AI_BASE_URL or _OPENAI_COMPATIBLE_BASE.get(provider)
    return provider, key, model, base_url


async def complete(system: str, user: str, *, max_tokens: int = 2048) -> str:
    """Single-turn completion: a system prompt + one user message → text response.
    Routes to the configured provider."""
    provider, key, model, base_url = _resolve()
    if not key:
        raise RuntimeError(
            "No AI API key configured — set AI_API_KEY (or ANTHROPIC_API_KEY) and AI_PROVIDER."
        )
    if provider == "anthropic":
        return await _anthropic_complete(key, model, system, user, max_tokens)
    # openai / gemini / openai_compatible / others → the OpenAI-protocol client.
    return await _openai_complete(key, model, base_url, system, user, max_tokens)


async def _anthropic_complete(key: str, model: str, system: str, user: str, max_tokens: int) -> str:
    global _anthropic_client
    from anthropic import AsyncAnthropic

    if _anthropic_client is None:
        _anthropic_client = AsyncAnthropic(api_key=key)
    msg = await _anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return msg.content[0].text


async def _openai_complete(
    key: str, model: str, base_url: str | None, system: str, user: str, max_tokens: int
) -> str:
    global _openai_client
    from openai import AsyncOpenAI

    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=key, base_url=base_url or None)
    resp = await _openai_client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.choices[0].message.content or ""


def reset_clients() -> None:
    """Drop cached provider clients — call after the AI config changes at runtime."""
    global _anthropic_client, _openai_client
    _anthropic_client = None
    _openai_client = None

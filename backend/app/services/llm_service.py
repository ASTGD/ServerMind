"""LLM provider abstraction (Update 20 — multi-provider AI).

Routes AI calls to whichever provider the instance is configured for, so a customer
can bring their own key from the provider they trust — Anthropic (Claude), OpenAI
(GPT), Google (Gemini), or any OpenAI-compatible endpoint (Mistral, Groq, DeepSeek,
a local model, …). All of ServerAlly's AI features make one shape of call — a system
prompt + a single user message → text — which this module unifies.

Anthropic goes through the ``anthropic`` SDK; everything else goes through the
``openai`` SDK (pointed at the right base URL), which speaks the OpenAI-compatible
protocol the other providers expose. SDKs are imported lazily, so the default
(Anthropic) path needs no extra packages installed.
"""
from __future__ import annotations

import logging

from app.config import settings
from app.services import metering_service

logger = logging.getLogger(__name__)

# Sensible default model per provider when no model is configured.
_DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-5",
    "openai": "gpt-4o",
    "gemini": "gemini-1.5-pro",
    "servermind": "servermind",  # the hosted gateway picks the real upstream model
}

# The model ladder (docs/AI-MODEL-LADDER.md): Ally uses the right-sized brain per task.
# 'default' is the resolved provider model; 'low'/'high' swap to a cheaper / stronger
# model for trivial / high-stakes work. Applied for the ANTHROPIC provider only — a
# bring-your-own-key user on another provider keeps their one configured model, and the
# whole thing is gated by settings.ENABLE_MODEL_LADDER.
TIERS = ("low", "default", "high")
_TIER_DEFAULTS = {"low": "claude-haiku-4-5-20251001", "high": "claude-opus-4-8"}


def _tier_model(provider: str, tier: str) -> str | None:
    """The model to use for a non-default tier, or None to keep the resolved model
    (ladder off, unsupported provider, or unknown tier)."""
    if not settings.ENABLE_MODEL_LADDER or provider != "anthropic" or tier not in ("low", "high"):
        return None
    override = settings.AI_MODEL_HIGH if tier == "high" else settings.AI_MODEL_LOW
    return override or _TIER_DEFAULTS[tier]


def model_for_tier(tier: str = "default") -> str:
    """The concrete model id a call at this tier would use (for logging / tests)."""
    provider, _key, model, _base = _resolve()
    return _tier_model(provider, tier) or model


def has_stronger_tier() -> bool:
    """True when 'high' resolves to a genuinely stronger (different) model than 'default'
    — i.e. escalating a hard request to it is worth a re-plan. False when the ladder is
    off or the provider has no stronger tier (BYO / non-anthropic), so callers skip the
    extra call instead of paying for an identical re-plan."""
    return model_for_tier("high") != model_for_tier("default")

# OpenAI-compatible base URLs for non-OpenAI providers reached via the openai SDK.
_OPENAI_COMPATIBLE_BASE = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "openai": None,  # the SDK default
}

_anthropic_client = None
_openai_client = None

# Runtime override chosen in Settings (DB-backed), loaded at startup. When it has a
# key, it takes precedence over the .env config (Update 20.1).
_runtime_config: dict | None = None


def set_runtime_config(provider: str, api_key: str, model: str, base_url: str) -> None:
    """Apply an AI config chosen in Settings (overrides .env). Resets cached clients."""
    global _runtime_config
    _runtime_config = {
        "provider": (provider or "anthropic").lower(),
        "api_key": api_key or "",
        "model": model or "",
        "base_url": base_url or "",
    }
    reset_clients()


def clear_runtime_config() -> None:
    """Drop the runtime override; fall back to the .env config. Resets cached clients."""
    global _runtime_config
    _runtime_config = None
    reset_clients()


def _base_for(provider: str) -> str | None:
    """Base URL for a provider reached via the OpenAI client. The hosted 'servermind'
    gateway is config-driven; the rest are fixed OpenAI-compatible endpoints."""
    if provider == "servermind":
        return settings.AI_GATEWAY_URL or None
    return _OPENAI_COMPATIBLE_BASE.get(provider)


def _resolve() -> tuple[str, str, str, str | None]:
    """Resolve (provider, api_key, model, base_url). The Settings override wins when it
    has a key; otherwise fall back to .env / the legacy ANTHROPIC_* settings."""
    cfg = _runtime_config
    if cfg and cfg.get("api_key"):
        provider = cfg["provider"]
        key = cfg["api_key"]
        model = cfg.get("model") or _DEFAULT_MODELS.get(provider) or settings.ANTHROPIC_MODEL
        base_url = cfg.get("base_url") or _base_for(provider)
        return provider, key, model, base_url
    provider = (settings.AI_PROVIDER or "anthropic").lower()
    key = settings.AI_API_KEY or (settings.ANTHROPIC_API_KEY if provider == "anthropic" else "")
    # Explicit config wins over the built-in default: AI_MODEL first, then the legacy
    # ANTHROPIC_MODEL (only for the anthropic provider — never leak it to openai/gemini),
    # then the per-provider default.
    legacy_model = settings.ANTHROPIC_MODEL if provider == "anthropic" else ""
    model = settings.AI_MODEL or legacy_model or _DEFAULT_MODELS.get(provider)
    base_url = settings.AI_BASE_URL or _base_for(provider)
    return provider, key, model, base_url


async def complete(
    system: str, user: str, *, max_tokens: int = 2048, system_volatile: str = "",
    tier: str = "default",
) -> str:
    """Single-turn completion: a system prompt + one user message → text response.
    Routes to the configured provider.

    ``tier`` picks the model size (docs/AI-MODEL-LADDER.md): 'default' uses the
    configured model; 'high' swaps to a stronger model for high-stakes judgment and
    'low' to a cheaper/faster one for trivial parses — Anthropic provider only, gated by
    ENABLE_MODEL_LADDER (a no-op elsewhere, so callers can always pass a tier safely).

    Prompt caching (Ally Context C3): ``system`` is the STABLE prefix (identical across
    consecutive calls in a conversation — persona, rules, server identity, skill) and
    ``system_volatile`` is the per-message tail (live profile, memories, page context,
    history). On Anthropic the stable part carries a cache_control marker (~90% cheaper
    on repeat); on OpenAI-protocol providers the stable-first ordering makes their
    automatic prefix caching work.
    """
    provider, key, model, base_url = _resolve()
    if not key:
        raise RuntimeError(
            "No AI API key configured — set AI_API_KEY (or ANTHROPIC_API_KEY) and AI_PROVIDER."
        )
    model = _tier_model(provider, tier) or model
    if provider == "anthropic":
        return await _anthropic_complete(key, model, system, system_volatile, user, max_tokens)
    # openai / gemini / openai_compatible / others → the OpenAI-protocol client.
    return await _openai_complete(key, model, base_url, system, system_volatile, user, max_tokens)


async def _anthropic_complete(
    key: str, model: str, system: str, system_volatile: str, user: str, max_tokens: int
) -> str:
    global _anthropic_client
    from anthropic import AsyncAnthropic

    if _anthropic_client is None:
        _anthropic_client = AsyncAnthropic(api_key=key)
    # The stable block is marked cacheable; below the provider's minimum prefix size
    # the marker is simply ignored (no error). The volatile tail is never cached.
    system_blocks: list[dict] = [
        {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
    ]
    if system_volatile:
        system_blocks.append({"type": "text", "text": system_volatile})
    msg = await _anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_blocks,
        messages=[{"role": "user", "content": user}],
        # All our calls are structured-JSON tasks: extended thinking (default-on for
        # Sonnet 5+) would eat the max_tokens budget (truncating long JSON) and bill
        # hidden output tokens. Explicitly off.
        thinking={"type": "disabled"},
    )
    # AI metering (docs/AI-METERING.md): exact token counts into the active collection,
    # including prompt-cache reads/writes (input_tokens excludes cached tokens).
    usage = getattr(msg, "usage", None)
    metering_service.note_usage(
        model,
        getattr(usage, "input_tokens", 0) or 0,
        getattr(usage, "output_tokens", 0) or 0,
        cache_read=getattr(usage, "cache_read_input_tokens", 0) or 0,
        cache_write=getattr(usage, "cache_creation_input_tokens", 0) or 0,
    )
    return _anthropic_text(msg)


def _anthropic_text(msg) -> str:
    """Join the TEXT blocks of a response. Newer models (Sonnet 5+) may emit thinking
    blocks first — content[0] is no longer guaranteed to be text."""
    parts = [
        block.text
        for block in (msg.content or [])
        if getattr(block, "type", "") == "text" and getattr(block, "text", None)
    ]
    return "\n".join(parts)


async def _openai_complete(
    key: str,
    model: str,
    base_url: str | None,
    system: str,
    system_volatile: str,
    user: str,
    max_tokens: int,
) -> str:
    global _openai_client
    from openai import AsyncOpenAI

    if _openai_client is None:
        _openai_client = AsyncOpenAI(api_key=key, base_url=base_url or None)
    full_system = system + ("\n" + system_volatile if system_volatile else "")
    resp = await _openai_client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": full_system},
            {"role": "user", "content": user},
        ],
    )
    # AI metering (docs/AI-METERING.md): exact token counts into the active collection.
    # OpenAI reports cached prompt tokens inside prompt_tokens — split them out.
    usage = getattr(resp, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    details = getattr(usage, "prompt_tokens_details", None)
    cached = getattr(details, "cached_tokens", 0) or 0
    metering_service.note_usage(
        model,
        max(0, prompt_tokens - cached),
        getattr(usage, "completion_tokens", 0) or 0,
        cache_read=cached,
    )
    return resp.choices[0].message.content or ""


def reset_clients() -> None:
    """Drop cached provider clients — call after the AI config changes at runtime."""
    global _anthropic_client, _openai_client
    _anthropic_client = None
    _openai_client = None

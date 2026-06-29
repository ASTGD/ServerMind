"""Instance settings — AI provider config (Update 20.1).

Instance-wide (the self-hosted owner's AI setup), not per-user. Changing it requires
an authenticated user; tighten to an owner/admin role for multi-user instances.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.services import llm_service, settings_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings", tags=["settings"])

_PROVIDERS = {"anthropic", "openai", "gemini", "openai_compatible"}


class AiSettingsBody(BaseModel):
    provider: str = "anthropic"
    api_key: str | None = None  # blank keeps the existing key
    model: str = ""
    base_url: str = ""


def _public(cfg: dict | None) -> dict:
    """Shape the AI config for the UI — never returns the key itself."""
    if cfg:
        return {
            "provider": cfg["provider"],
            "model": cfg["model"],
            "base_url": cfg["base_url"],
            "has_key": bool(cfg["api_key"]),
            "source": "settings",
        }
    return {
        "provider": settings.AI_PROVIDER,
        "model": settings.AI_MODEL,
        "base_url": settings.AI_BASE_URL,
        "has_key": bool(settings.AI_API_KEY or settings.ANTHROPIC_API_KEY),
        "source": "env",
    }


@router.get("/ai")
async def get_ai_settings(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """Current AI provider config (never returns the key itself)."""
    return _public(await settings_service.get_ai_config(db))


@router.put("/ai")
async def put_ai_settings(
    body: AiSettingsBody,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """Save the AI provider config and apply it live. A blank api_key keeps the
    existing key (so the model/provider can change without re-typing the secret)."""
    provider = body.provider if body.provider in _PROVIDERS else "anthropic"
    cfg = await settings_service.set_ai_config(db, provider, body.api_key, body.model, body.base_url)
    llm_service.set_runtime_config(
        cfg.get("provider", "anthropic"),
        cfg.get("api_key", ""),
        cfg.get("model", ""),
        cfg.get("base_url", ""),
    )
    return _public(cfg)


@router.post("/ai/test")
async def test_ai_settings(_: User = Depends(get_current_user)) -> dict:
    """Send a tiny prompt to the configured AI to confirm the key + model work."""
    try:
        reply = await llm_service.complete(
            "You are a connectivity check. Reply with the single word OK.",
            "ping",
            max_tokens=5,
        )
        return {"ok": True, "reply": (reply or "").strip()[:40]}
    except Exception as exc:  # noqa: BLE001 — report any provider/key error cleanly
        return {"ok": False, "error": str(exc)[:200]}

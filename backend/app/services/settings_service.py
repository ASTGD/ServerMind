"""Instance-wide settings (Update 20.1) — AI provider config persisted in the DB with
the API key encrypted (AES-256-GCM). The live override that llm_service reads is set
from here; this module is the persistence layer."""
from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.app_setting import AppSetting
from app.services.crypto_service import decrypt, encrypt

logger = logging.getLogger(__name__)

_AI_KEY = "ai_config"


async def get_ai_config(db: AsyncSession) -> dict | None:
    """Return the stored AI config with the key decrypted, or None if unset."""
    row = (
        await db.execute(select(AppSetting).where(AppSetting.key == _AI_KEY))
    ).scalar_one_or_none()
    if not row or not row.value:
        return None
    data = json.loads(row.value)
    enc = data.get("api_key_encrypted")
    return {
        "provider": data.get("provider") or "anthropic",
        "api_key": decrypt(enc) if enc else "",
        "model": data.get("model") or "",
        "base_url": data.get("base_url") or "",
    }


async def set_ai_config(
    db: AsyncSession, provider: str, api_key: str | None, model: str, base_url: str
) -> dict:
    """Persist the AI config. A blank api_key keeps the existing key (so the model or
    provider can change without re-typing the secret). Returns the saved config."""
    data: dict = {
        "provider": (provider or "anthropic").lower(),
        "model": model or "",
        "base_url": base_url or "",
    }
    if api_key:
        data["api_key_encrypted"] = encrypt(api_key)
    else:
        existing = await get_ai_config(db)
        if existing and existing.get("api_key"):
            data["api_key_encrypted"] = encrypt(existing["api_key"])

    row = (
        await db.execute(select(AppSetting).where(AppSetting.key == _AI_KEY))
    ).scalar_one_or_none()
    if row:
        row.value = json.dumps(data)
    else:
        db.add(AppSetting(key=_AI_KEY, value=json.dumps(data)))
    await db.commit()
    return await get_ai_config(db) or {}

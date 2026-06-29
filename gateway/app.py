"""ServerAlly AI Gateway (Update 20.3).

A small, standalone service WE run — NOT part of a customer's ServerAlly install. It
lets customers without their own AI key use "ServerAlly AI" via a subscription: their
ServerAlly instance points at this gateway (AI_PROVIDER=servermind, AI_API_KEY=<token>),
and the gateway forwards to a real provider with OUR upstream key, validating the
subscription and metering usage.

It speaks the OpenAI protocol, so ServerAlly reaches it with the openai SDK — the one
inference endpoint is ``POST /v1/chat/completions``. Subscriptions are issued via
``POST /admin/subscriptions`` (protected by GATEWAY_ADMIN_KEY); wire that to your billing
platform's webhook later. Tokens are stored hashed; only the hash is kept.

Run:  uvicorn gateway.app:app --port 8100      (see gateway/README.md)
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import uuid
from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import Boolean, Date, DateTime, Integer, String, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gateway")

# ── Config (env) ──────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("GATEWAY_DATABASE_URL", "sqlite+aiosqlite:///./gateway.db")
ADMIN_KEY = os.getenv("GATEWAY_ADMIN_KEY", "")
UPSTREAM_PROVIDER = os.getenv("GATEWAY_UPSTREAM_PROVIDER", "anthropic").lower()
UPSTREAM_KEY = os.getenv("GATEWAY_UPSTREAM_KEY", "")
UPSTREAM_MODEL = os.getenv("GATEWAY_UPSTREAM_MODEL", "claude-sonnet-4-20250514")
UPSTREAM_BASE_URL = os.getenv("GATEWAY_UPSTREAM_BASE_URL", "")
DEFAULT_MONTHLY_LIMIT = int(os.getenv("GATEWAY_DEFAULT_MONTHLY_LIMIT", "1000"))


# ── DB ────────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(255), default="")
    plan: Mapped[str] = mapped_column(String(40), default="standard")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    monthly_limit: Mapped[int] = mapped_column(Integer, default=DEFAULT_MONTHLY_LIMIT)
    used_this_period: Mapped[int] = mapped_column(Integer, default=0)
    period_start: Mapped[date] = mapped_column(Date, default=lambda: date.today().replace(day=1))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


engine = create_async_engine(DATABASE_URL)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with Session() as db:
        yield db


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="ServerAlly AI Gateway")


@app.on_event("startup")
async def _startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Gateway up — upstream=%s, db=%s", UPSTREAM_PROVIDER, DATABASE_URL.split("://")[0])


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


# ── Admin: issue / list subscriptions ─────────────────────────────────────────
def _require_admin(x_admin_key: str = Header(default="")) -> None:
    if not ADMIN_KEY or x_admin_key != ADMIN_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad admin key")


class NewSubscription(BaseModel):
    label: str = ""
    plan: str = "standard"
    monthly_limit: int | None = None


@app.post("/admin/subscriptions", dependencies=[Depends(_require_admin)])
async def create_subscription(body: NewSubscription, db: AsyncSession = Depends(get_db)) -> dict:
    """Issue a subscription token. Returned ONCE — only its hash is stored."""
    token = "sm_live_" + secrets.token_urlsafe(32)
    sub = Subscription(
        token_hash=_hash(token),
        label=body.label,
        plan=body.plan,
        monthly_limit=body.monthly_limit or DEFAULT_MONTHLY_LIMIT,
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return {"id": sub.id, "token": token, "plan": sub.plan, "monthly_limit": sub.monthly_limit}


@app.get("/admin/subscriptions", dependencies=[Depends(_require_admin)])
async def list_subscriptions(db: AsyncSession = Depends(get_db)) -> list[dict]:
    rows = (
        await db.execute(select(Subscription).order_by(Subscription.created_at.desc()))
    ).scalars().all()
    return [
        {
            "id": s.id, "label": s.label, "plan": s.plan, "active": s.active,
            "monthly_limit": s.monthly_limit, "used_this_period": s.used_this_period,
            "period_start": s.period_start.isoformat(),
        }
        for s in rows
    ]


# ── OpenAI-compatible inference ───────────────────────────────────────────────
async def _authed_subscription(db: AsyncSession, authorization: str) -> Subscription:
    token = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not token:
        raise HTTPException(status_code=401, detail="Missing subscription token")
    sub = (
        await db.execute(select(Subscription).where(Subscription.token_hash == _hash(token)))
    ).scalar_one_or_none()
    if not sub or not sub.active:
        raise HTTPException(status_code=401, detail="Invalid or inactive subscription")
    return sub


def _within_limit(sub: Subscription) -> bool:
    """True if the subscription has requests left this month; resets the period if the
    month rolled over (caller commits)."""
    this_period = date.today().replace(day=1)
    if sub.period_start != this_period:
        sub.period_start = this_period
        sub.used_this_period = 0
    return sub.used_this_period < sub.monthly_limit


async def _upstream(messages: list[dict]) -> str:
    """Forward the chat to the real provider with OUR key. ServerAlly only ever sends a
    system + user message, so we collapse them per provider."""
    if not UPSTREAM_KEY:
        raise HTTPException(status_code=503, detail="Gateway upstream key not configured")
    system = "\n\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
    user = "\n\n".join(m.get("content", "") for m in messages if m.get("role") == "user")
    if UPSTREAM_PROVIDER == "anthropic":
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=UPSTREAM_KEY)
        msg = await client.messages.create(
            model=UPSTREAM_MODEL, max_tokens=2048, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=UPSTREAM_KEY, base_url=UPSTREAM_BASE_URL or None)
    resp = await client.chat.completions.create(model=UPSTREAM_MODEL, max_tokens=2048, messages=messages)
    return resp.choices[0].message.content or ""


@app.post("/v1/chat/completions")
async def chat_completions(
    request: Request,
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(default=""),
) -> dict:
    sub = await _authed_subscription(db, authorization)
    if not _within_limit(sub):
        await db.commit()  # persist a possible period reset
        raise HTTPException(status_code=429, detail="Monthly request limit reached")

    body = await request.json()
    reply = await _upstream(body.get("messages") or [])

    sub.used_this_period += 1
    await db.commit()

    return {
        "id": "smai-" + uuid.uuid4().hex[:24],
        "object": "chat.completion",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "model": "servermind",
        "choices": [
            {"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }

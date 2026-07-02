"""ServerAlly AI Gateway — auth, metering, and OpenAI-compatible forwarding."""
import os

os.environ.setdefault("GATEWAY_DATABASE_URL", "sqlite+aiosqlite:////tmp/sm_test_gateway.db")
os.environ.setdefault("GATEWAY_ADMIN_KEY", "test-admin")

from httpx import ASGITransport, AsyncClient  # noqa: E402

from gateway import app as gw  # noqa: E402


async def _client() -> AsyncClient:
    async with gw.engine.begin() as conn:
        await conn.run_sync(gw.Base.metadata.drop_all)
        await conn.run_sync(gw.Base.metadata.create_all)
    return AsyncClient(transport=ASGITransport(app=gw.app), base_url="http://test")


async def test_full_flow(monkeypatch):
    async def fake_upstream(messages):
        # (text, input_tokens, output_tokens) — the metering passthrough shape
        return "HELLO_FROM_GATEWAY", 100, 20

    monkeypatch.setattr(gw, "_upstream", fake_upstream)

    async with await _client() as client:
        assert (await client.get("/health")).json() == {"ok": True}

        # admin needs the key
        assert (await client.post("/admin/subscriptions", json={"label": "x"})).status_code == 401

        # issue a token (limit 2)
        r = await client.post(
            "/admin/subscriptions",
            headers={"X-Admin-Key": "test-admin"},
            json={"label": "acme", "monthly_limit": 2},
        )
        token = r.json()["token"]
        assert token.startswith("sm_live_")

        hdr = {"Authorization": f"Bearer {token}"}
        body = {"messages": [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}]}

        # two requests within the limit — OpenAI-shaped + forwarded, real usage passed through
        for _ in range(2):
            r = await client.post("/v1/chat/completions", headers=hdr, json=body)
            assert r.status_code == 200
            data = r.json()
            assert data["choices"][0]["message"]["content"] == "HELLO_FROM_GATEWAY"
            assert data["usage"] == {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}

        # the per-request token ledger recorded both calls (docs/AI-METERING.md Brick 1)
        async with gw.Session() as db:
            from sqlalchemy import select

            records = (await db.execute(select(gw.UsageRecord))).scalars().all()
            assert len(records) == 2
            assert all(r.input_tokens == 100 and r.output_tokens == 20 for r in records)

        # third exceeds the monthly limit
        assert (await client.post("/v1/chat/completions", headers=hdr, json=body)).status_code == 429

        # a bad token is rejected
        bad = await client.post(
            "/v1/chat/completions", headers={"Authorization": "Bearer nope"}, json=body
        )
        assert bad.status_code == 401

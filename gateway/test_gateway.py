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
        return "HELLO_FROM_GATEWAY"

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

        # two requests within the limit — OpenAI-shaped + forwarded
        for _ in range(2):
            r = await client.post("/v1/chat/completions", headers=hdr, json=body)
            assert r.status_code == 200
            assert r.json()["choices"][0]["message"]["content"] == "HELLO_FROM_GATEWAY"

        # third exceeds the monthly limit
        assert (await client.post("/v1/chat/completions", headers=hdr, json=body)).status_code == 429

        # a bad token is rejected
        bad = await client.post(
            "/v1/chat/completions", headers={"Authorization": "Bearer nope"}, json=body
        )
        assert bad.status_code == 401

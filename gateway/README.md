# ServerAlly AI Gateway

The hosted **"ServerAlly AI" subscription** backend (Update 20.3). **We** run this;
customers never do. It lets a self-hosted ServerAlly use our AI without their own key:
their instance points here with a subscription token, and we forward to a real provider
with our upstream key — validating the subscription and metering usage.

It speaks the **OpenAI protocol**, so ServerAlly talks to it with the openai SDK.

## Run

```bash
pip install -r gateway/requirements.txt
cp gateway/.env.example gateway/.env     # set GATEWAY_ADMIN_KEY + GATEWAY_UPSTREAM_KEY
uvicorn gateway.app:app --port 8100
```

Defaults to a local SQLite file; set `GATEWAY_DATABASE_URL` to Postgres in production.

## Issue a subscription token

```bash
curl -X POST http://localhost:8100/admin/subscriptions \
  -H "X-Admin-Key: $GATEWAY_ADMIN_KEY" -H "Content-Type: application/json" \
  -d '{"label":"acme co","monthly_limit":1000}'
# → {"id":"…","token":"sm_live_…","plan":"standard","monthly_limit":1000}
```

The token is shown **once** (only its hash is stored). Later, wire
`POST /admin/subscriptions` to your billing platform's webhook (Lemon Squeezy / Gumroad
/ Paddle) so a purchase issues a token automatically.

## Point a ServerAlly instance at it

In that ServerAlly's **Settings → AI provider**, choose **ServerAlly AI (subscription)**
and paste the token. (Equivalently: `AI_PROVIDER=servermind`, `AI_API_KEY=<token>`,
`AI_GATEWAY_URL=<this gateway>/v1`.)

## Endpoints

- `POST /v1/chat/completions` — OpenAI-compatible; needs `Authorization: Bearer <token>`.
  Validates the subscription, enforces the monthly limit, forwards to the upstream
  provider, and meters the request.
- `POST /admin/subscriptions` / `GET /admin/subscriptions` — issue / list (`X-Admin-Key`).
- `GET /health`.

## Tests

```bash
pip install httpx
python -m pytest gateway/test_gateway.py
```

## Follow-ups (not built yet)

- Billing-platform webhook → auto-issue / revoke subscriptions.
- Token-accurate metering (currently per-request) + usage reporting to the customer.
- Per-token rate limiting + abuse alerts.
- Tighten the gateway admin auth (rotate keys, scope per action).

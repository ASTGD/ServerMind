# AI Metering & Subscription Token Model

> **Status: Bricks 1 + 2 SHIPPED (2026-07-03). Brick 3 (billing webhook) HALTED** until
> a payment provider is chosen — `users.plan` is set manually meanwhile, and the quota
> wall only blocks when `ENFORCE_AI_QUOTA=true` (default off; cloud will turn it on).
> This document is the contract for how ServerAlly turns one Anthropic API key
> (wholesale, pay-per-token) into per-customer monthly allowances (retail, flat
> subscription). Companion to [PRICING-FREE-VS-PRO.md](PRICING-FREE-VS-PRO.md)
> (§9 allowances, §10 implementation notes, §11 open questions) and the hosted
> gateway (`gateway/`).
>
> Shipped code map: `ai_usage` table (migration 019) · `metering_service.py`
> (collector/gate/record/prices) · `entitlements.py` (plan map) · usage hooks in
> `llm_service.py` · gates+ledger in chat/fleet/batch (`websocket/terminal.py`),
> script generation (402 wall) and schedule parse (0-action) · `GET /api/usage/me` ·
> gateway token capture + `usage_records` + real usage passthrough · Settings
> "Ally usage" card + chat quota bubble.

---

## 1. The economic model in one picture

```
Anthropic ──(tokens, billed to OUR one key, per-token price)──▶ ServerAlly
ServerAlly ──(flat monthly plan with an "action" allowance)──▶ Customer
```

- Anthropic has **no per-customer allocation**. You cannot hand customer X a slice of
  the API key. Every provider bill lands on us, undivided.
- Therefore **all metering is ours**: our database decides who may call, our ledger
  records what each call cost, our caps stop the bleeding.
- This is the standard AI-SaaS pattern (Notion AI, Intercom Fin, Jasper). Nothing exotic.

The margin logic: most subscribers use 5–10% of their cap. The cap exists to stop the
heavy tail, not to be reached. Free's small allowance is bounded marketing spend
(~$1/user/month worst case); Pro's generous allowance costs $1–3/month for a typical
user against a $15–25 price.

---

## 2. The unit customers see: **actions** (locked in PRICING §9)

Customers never see tokens or dollars. One **action** = one user-initiated request to
Ally. We absorb token variance between requests; the token ledger (below) is our
internal cost view.

| Event | Actions charged |
|---|---|
| Per-server chat message (plan → execute → explain cycle) | **1** — the explain step is part of the same action, not a second one |
| Fleet chat message | **1** |
| Script generation (Ally chat or the Script Generator page) | **1** |
| Batch action across N servers | **N** (one plan per target server — honest: it really costs N model calls; the batch modal shows the count before running) |
| Ally Mission (multi-step job, docs/ALLY-MISSIONS.md) | **1** at start — its up-to-20 model calls are ledgered with `feature="mission"` + the skill tag; revisit pricing from real ledger data if missions prove heavy |
| Natural-language → cron parse (scheduler) | **0** — tiny utility call, metered in the ledger but free to the user |
| Request blocked by the safety layer *after* planning | **1** — the model already ran; honesty over generosity |
| Our failure (provider error, gateway down, AI misconfigured) | **0** — never charge for our own errors; retries after a provider error are not double-counted |
| User on their **own key** (BYO) | **0** — their fuel, unmetered against the plan (ledgered with `fuel='byok'`, cost 0, for product analytics only) |

---

## 3. Data model

Two records with two different jobs, plus a static entitlement map.

### 3.1 `ai_usage` — the token ledger (source of truth)

One row per model call. Append-only. **Never stores prompt or response content** — only
counts and labels (no secrets by construction, same principle as the Ally Brain context).

```sql
id              UUID PK
user_id         UUID → users            -- who to bill it to (see §8 team pooling)
server_id       UUID → servers NULL     -- per-server calls; NULL for fleet/scripts
feature         VARCHAR(30)             -- 'chat' | 'fleet_chat' | 'script_gen' | 'explain'
                                        --   | 'schedule_parse' | 'batch'
model           VARCHAR(60)             -- exact model id used
fuel            VARCHAR(10)             -- 'included' | 'byok'
input_tokens    INTEGER                 -- from the provider's usage block
output_tokens   INTEGER
cost_usd        DECIMAL(10,6)           -- computed at write time from a price table
actions         SMALLINT                -- 0 or 1 (batch = N rows of 1, one per server)
status          VARCHAR(15)             -- 'ok' | 'provider_error' | 'blocked'
created_at      TIMESTAMP
```

Answers: real margin per customer, which feature burns money, which model mix to route,
who the heavy tail is.

### 3.2 Monthly action counter — the fast gate

A per-user counter for the current billing period (Redis `INCR` with the ledger as the
rebuildable source of truth: `SUM(actions) WHERE user_id AND period`). Checked **before**
every metered call; incremented **after** a successful one. If Redis is cold, rebuild
from the ledger.

### 3.3 Entitlements — one static map (PRICING §10)

Per plan: `max_servers`, `actions_per_month`, feature flags (fleet, batch, scheduler,
team…). Exposed as `can_use(feature)` + `within_limit(kind)` and enforced
**server-side** — the UI reads the same map for greying-out, but the API is the wall.

---

## 4. Enforcement flow (every metered call)

```
user request
  → resolve fuel: own key set? → BYO path (no gate; ledger fuel='byok')
  → gate: counter < plan allowance?
      NO  → friendly wall (no model call):
            "You've used all N actions this month." + 3 exits:
            Upgrade · Add your own key · Resets on <date>
      YES → call provider (our key)
  → on response: read exact usage {input_tokens, output_tokens}
  → write ledger row (cost from price table) + INCR counter
  → serve the answer
```

Failure policy:

- **Provider call fails** → status `provider_error`, **0 actions**, friendly error.
- **Ledger/counter write fails** → **still serve the answer**, log loudly, reconcile
  from the ledger later. A metering bug must never punish a paying customer.
- **Streaming responses** → usage arrives in the final stream event; the ledger row is
  written at stream end (crash mid-stream = worst case one under-counted call — always
  err in the customer's favor).

---

## 5. Where the meter sits: two doors, one design

Both deployment modes already funnel every AI call through a single choke point, so the
meter is one component used twice:

| Mode | Choke point | Status today |
|---|---|---|
| **Cloud SaaS** | `backend/app/services/llm_service.py` — every Ally feature calls it | No metering yet (`.env` key, no per-user limits) |
| **Self-hosted + hosted "ServerAlly AI" subscription** | `gateway/` — customer instance sends `Authorization: Bearer sm_live_…` | **Partially built**: token issue/validate (hash-stored), `monthly_limit` vs `used_this_period` request counting, OpenAI-compatible forward. **Gap**: counts requests not tokens; upstream `usage` is not captured/passed through yet |

Build once as a small `metering_service` (gate, record, price table) and call it from
both doors. The gateway additionally maps *subscription token → allowance* instead of
*user → allowance*; same ledger schema.

---

## 6. Safety rails (defense in depth)

1. **Plan cap** — the action gate above (per user / per subscription token).
2. **Rate limit** — 30 requests/min/user/server (already live in `rate_limit_service`).
3. **Global circuit breaker** — a monthly spend cap on our Anthropic workspace
   (provider-side). If all our code fails, Anthropic stops the bleeding.
4. **Model routing** — cheap model (Haiku-class) for `explain` and `schedule_parse`,
   strong model only for planning/scripts. 3–5× cost cut, no UX change.
5. **Prompt caching** — ✅ IMPLEMENTED (Ally Context C3, 2026-07-03). Prompts are laid
   out stable-prefix-first (persona/rules/identity/skill) with per-message blocks in a
   volatile tail; `llm_service` marks the stable block `cache_control: ephemeral` on
   Anthropic (~90% off on repeat) and the ordering makes OpenAI's automatic prefix
   caching work too. The ledger records `cache_read_tokens`/`cache_write_tokens`
   (migration 022) and `cost_usd` prices them (reads 0.1×, writes 1.25×; OpenAI reads
   0.5×). Mission steps benefit most — the transcript only appends, so the prefix
   stays identical step after step.
6. **Anomaly alert** — a daily job flags users >5× their trailing average (bug or abuse).

---

## 7. Cost & margin math (fill with real data before launch — PRICING §11)

Assume one action ≈ 5k input + 1k output tokens (Ally Brain context included):

| Model class | ~Cost per action | 30 actions (Free) | 1,000 actions (Pro cap) |
|---|---|---|---|
| Haiku-class | ~$0.01 | ~$0.30 | ~$10 |
| Sonnet-class | ~$0.03 | ~$1 | ~$30 |

With routing (cheap model for the small calls) a blended action lands near
**$0.015–0.02**. Typical Pro usage (50–100 actions/mo) → **$1–2/mo COGS** against a
$15–25 plan. The pre-launch task from PRICING §9 stands: measure real per-action tokens
from the ledger, then set the final caps.

---

## 8. Billing loop & team pooling

- **Provider:** Stripe / Paddle / Lemon Squeezy (TBD — PRICING §10). They own card data;
  we never touch it.
- **Webhooks drive entitlements:** `subscription.created/updated` → set plan +
  allowance; `renewed` → reset the counter (billing-anchor date, not calendar month);
  `canceled/past_due` → drop to Free limits at period end. Webhook handler is idempotent.
- **Top-up packs** (later, optional): one-time purchase adds N actions to the current
  period — the "overage" answer from PRICING §11 without surprise bills.
- **Team accounts:** members draw from the **owner's** pool (the owner pays; matches the
  existing team model). Per-member sub-limits are a later Pro nicety, not v1.
- **Self-hosted offline:** the gateway is the meter, so a customer instance that can't
  reach it gets a short grace window (mirrors the license model in
  SELF-HOSTED-LICENSING.md) rather than instant lockout.

---

## 9. Build order (three bricks, each shippable alone)

1. ✅ **Brick 1 — Ledger + counter (no billing needed).** SHIPPED 2026-07-03: `ai_usage`
   table + `metering_service` (gate/record/price-table) wired into `llm_service`;
   Free-plan default allowance for everyone. Collecting the real per-action cost data
   §7 needs. Gateway captures real `usage` (per-request `usage_records`) and passes it
   through.
2. ✅ **Brick 2 — Entitlement map + the wall.** SHIPPED 2026-07-03: `entitlements.py`
   server-side, quota wall in chat/fleet/batch (`quota_exceeded` bubble) and script
   generation (HTTP 402), usage bar in Settings ("X of N actions"). The wall is armed
   by `ENFORCE_AI_QUOTA` (default off — dev/self-hosted only collect data).
3. ⏸ **Brick 3 — Billing webhook. HALTED** (PM decision 2026-07-03): payment provider
   not chosen yet — no Stripe/Paddle/Lemon Squeezy code. When chosen: Upgrade modal →
   real checkout, webhook → entitlements, anchor-date resets.

---

## 10. Open questions (PM to settle — tracked in PRICING §11)

- Final Free/Pro action numbers (after Brick 1 gives real cost data).
- Pro price point; monthly/annual.
- Overage style at the wall: top-up packs vs hard stop vs BYO-key prompt only.
- Billing provider (Stripe vs Paddle vs Lemon Squeezy — merchant-of-record question).

# ServerAlly — Pricing v2: "Open features, two meters"

> **v2 (2026-07-03) — DECIDED & ENFORCEMENT BUILT.** This revises v1's feature-gating
> matrix. The new model: **every feature is available on every plan; plans differ in
> exactly two numbers — servers and Ally actions.** The two gates are implemented and
> sit dormant behind `ENFORCE_PLAN_LIMITS` (default off; cloud flips it on). **Update
> (2026-07-03): the billing-provider question below was resolved by going through
> FireVPS's existing WHMCS instead of Stripe/Paddle/Lemon Squeezy** — see
> [WHMCS-INTEGRATION.md](WHMCS-INTEGRATION.md). `users.plan` now moves via the WHMCS
> entitlement API; the exact price/allowance numbers in this doc are still open (§11).

---

## 1. Summary

- **Free:** 2 servers · 30 Ally actions/month · every feature included.
- **Pro (~$15–19/mo):** 15 servers · 1,000 Ally actions/month · every feature included
  · own-AI-key escape valve (unmetered) · priority support.
- **Later — Agency tier:** more servers, white-label, team-of-teams. Added ABOVE,
  never by removing something below.
- The pitch is one sentence: *"ServerAlly is free for 2 servers. Pay when you need
  more servers or more Ally."*

A separate **self-hosted** edition exists (licensed) — see
[SELF-HOSTED-LICENSING.md](SELF-HOSTED-LICENSING.md); §10 notes how it maps onto this model.

---

## 2. The AI is named "Ally"

Unchanged from v1: the assistant persona is **Ally** everywhere ("Ask Ally", "Hand to
Ally", "Ally remembers", missions). The brand is the companion.

---

## 3. AI packaging — one subscription, two fuel options

Unchanged from v1: **software and AI-fuel are ONE purchase, never a second bill.**

- **Included ServerAlly AI (default):** works out of the box; the plan's action
  allowance is the meter (ledger + walls shipped — see [AI-METERING.md](AI-METERING.md)).
- **Bring-your-own-key (escape valve):** plug your own Claude/OpenAI/Gemini key →
  actions unmetered (your fuel). A toggle, not a purchase. Hidden on cloud Free
  (`SHOW_AI_PROVIDER_SETTINGS`); always available self-hosted.
- **Overage:** top-up action packs (one-time, no surprise bills) — arrives with billing.

---

## 4. The two meters (the whole model)

Each meter maps to a REAL cost for us and a REAL value signal from the customer:

| Meter | Aligned with | Enforced at |
|---|---|---|
| **Ally actions / month** | Our AI bill (measured ≤ $0.05/action — §9) | The AI choke points (`metering_service.gate`) — chat, fleet, batch, missions, script gen |
| **Servers** | Our per-server infra (metrics polling every 5 min, scans, probes) + the market's standard value metric | One check at server creation (`metering_service.servers_gate`) — HTTP 402, friendly message |

Both always *measure*; they only *block* when `ENFORCE_PLAN_LIMITS=true`.
The server cap only stops **adding more** — existing servers are never touched.

---

## 5. What's included: everything, everywhere

Missions, long-term memory, skills, Live Look, fleet chat, batch actions, scheduler,
backups, security scans, alerts, file manager, terminal workspace, team, hosting-panel
mode — **all of it, on Free and Pro alike.** The Settings "Ally usage" card shows both
meters plus the promise: "All features included on every plan."

---

## 6. Why no feature gates (the reasoning that replaced v1)

1. **The AI already gates the product for our audience.** The target user is
   non-technical — every feature is *operated through Ally*. Out of actions ≈ out of
   product. Locking doors is redundant when the AI is the key to every door.
2. **Never gate safety.** Paywalled backups/security = a user loses data one day and
   the brand dies. Safety features are open, forever, on principle.
3. **Don't fragment the magic.** The conversion moment is a full-quality Ally
   experience (a mission fixing a broken site) inside the free allowance. The quota
   limits how MUCH — never how GOOD. One quota, full quality.
4. **The server cap is cost-honest, not greedy.** Metrics/scans/backup schedules run
   per server — unlimited free servers is real infra exposure; and "price per server"
   is the metric this market (RunCloud, Ploi, cPanel) already trained buyers on.
5. **Feature-gating costs weeks** of enforcement surface + support pain ("you locked
   my backups?!"); the two-meter model needed two choke points and ~2 days.
6. **Accepted trade-off:** a technical user can run 2 servers free forever, manually,
   never paying. Fine — they weren't the buyer, they cost pennies, and they evangelize.

---

## 7. Upgrade triggers (the two walls that convert)

1. *"You've used all 30 Ally actions this month"* — hit mid-love, right after Ally
   fixed something real. (Amber chat bubble + HTTP 402 on script gen; shipped.)
2. *"Your plan includes 2 servers and you already have 2"* — hit exactly when their
   business grows. (HTTP 402 at Add Server; the modal surfaces the message; shipped.)

Both walls offer the same exits: **Upgrade · own key (actions only) · wait for reset.**

---

## 8. Pricing shape

- **Free** — $0 forever.
- **Pro** — target **$15–19/mo** (annual ≈ 2 months free). One plan, no matrix to read.
- **Agency** — later, built from real demand (servers, white-label, priority).
- **Top-up packs** for actions — with billing.

---

## 9a. ⚠️ Cost/action is running at ~$0.096 — nearly 2× the assumption (2026-07-17)

The new admin Overview (SAAS-LAUNCH-PLAN §5.1) computes cost/action live from the
ledger. Its first real reading: **$0.096/action** over 341 actions / 1,161 calls /
$32.68 — against the **≤$0.05** this whole section's margin case rests on.

**Read it with the caveat it deserves:** that is *our dev/test* usage, not a customer's.
It is unusually mission- and verify-heavy (Opus verification runs ~$0.042 each), and the
sample is small. It is a **signal, not a verdict** — real customer usage skews lighter.

But it must not be waved away either, because the Pro case below is priced on $0.05:
- At $0.096, a Pro user who **maxes 1,000 actions** costs **$96/mo** against a $15–19
  price. §9's "worst case $50" becomes ~$96. Typical usage (5–10% of cap) is still fine
  (~$3–10/mo) — the exposure is the tail, not the average.
- Before arming `ENFORCE_PLAN_LIMITS`, re-read this number against **customer-shaped**
  usage, and settle the Pro allowance against it (§11). The allowance — not the price —
  is the lever that bounds our tail risk.

The admin Overview now shows this tile in **red above $0.05**, so the assumption can
never quietly drift again.

## 9. AI allowance — REAL numbers (First Flight, 2026-07-03)

Measured live on Sonnet 5 with prompt caching + thinking disabled:

- Typical action: **$0.03–0.05** (missions cache ~80% of their input tokens).
- Free worst case: 30 × $0.05 = **≤ $1.50/user/month**; realistic ~$0.30.
- Pro worst case: 1,000 × $0.05 = $50, but typical usage is 5–10% of cap →
  **$1.50–5/mo COGS** against $15–19 → 70–90% gross margin.
- Keep tuning from the `ai_usage` ledger (exact tokens + cache + cost per call).

---

## 10. Implementation status

- ✅ Actions meter: ledger, gate, walls, Settings card (AI-METERING.md Bricks 1+2).
- ✅ Server meter: `servers_gate` + 402 at create + both meters in `GET /api/usage/me`
  and the Settings card.
- ✅ One switch arms both: `ENFORCE_PLAN_LIMITS` (default false — dev/self-hosted
  just measure; cloud enforces).
- ✅ Plan map: `entitlements.py` — two numbers per plan, **no feature flags by design**.
- ⏸ Billing (checkout, webhooks, plan sync, top-ups): waits on the provider decision
  (Stripe vs Paddle vs Lemon Squeezy).
- **Self-hosted licensing:** a license key only needs to encode `plan + max_servers`
  (+ a gateway subscription token or BYO key for actions) — the two-meter model keeps
  the license format trivial.

---

## 11. Open questions before launch

- Pro price point ($15 vs $19; annual discount).
- Exact Pro action allowance (1,000 placeholder — validate against ledger data).
- Overage UX: top-up pack sizes/prices.
- Billing provider (merchant-of-record question).

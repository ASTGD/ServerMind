# ServerAlly SaaS — admin design, WHMCS split, and the renewal lifecycle

> **Status: DESIGN (2026-07-16).** Management decided ServerAlly ships as a hosted SaaS
> product of FireVPS.net, sold and renewed through the existing WHMCS.
> `serverally.firevps.net` = marketing site, the app lives beside it.
>
> This doc answers three questions: **what can we control in the ServerAlly admin area**,
> **what WHMCS gives us**, and **exactly how renewal works**. It is the reference for the
> whole billing/admin surface — read it before touching entitlements, plans, or metering.
>
> Related: [WHMCS-INTEGRATION.md](WHMCS-INTEGRATION.md) (what shipped),
> [PRICING-FREE-VS-PRO.md](PRICING-FREE-VS-PRO.md) (the two-meter model),
> [AI-METERING.md](AI-METERING.md) (the ledger).

---

## 1. The split in one table

The rule: **one system of record per fact.** If both systems own "what plan is this
customer on", they will disagree one day, and support cannot tell which is true.

| Fact | Owner | ServerAlly's role |
|---|---|---|
| Billing identity (name, address, company, tax, currency) | **WHMCS** | never stores it |
| Orders, invoices, payments, refunds, coupons, affiliates | **WHMCS** | never sees them |
| Renewal dates, dunning, auto-suspend, auto-terminate | **WHMCS** | reacts to the event |
| Revenue, MRR, churn reporting | **WHMCS** | never computes it |
| Support tickets | **WHMCS** | links out |
| Login + password | **ServerAlly** | owns it (WHMCS sends a claim link) |
| Servers, missions, memory, files, credentials | **ServerAlly** | owns it |
| AI usage + our real AI cost | **ServerAlly** | owns it (WHMCS cannot know it) |
| `users.plan` (free / pro) | WHMCS **decides** | **mirrors** it, read-only |

**Revenue lives in WHMCS. Cost lives in ServerAlly.** Neither system can compute margin
alone — see §5.1 for how the admin overview handles that.

---

## 2. What WHMCS gives us

Everything on the money side, with no work from us:

- **The customer record** — name, email, company, address, phone, currency, tax.
- **The order + invoice + payment** — through any gateway FireVPS already runs
  (Payssion included). The ServerAlly module never touches payments.
- **The service record** — which plan, status (Active / Suspended / Terminated /
  Cancelled), next due date, billing cycle, amount.
- **Automatic dunning** — renewal invoice, reminder emails, late fees, auto-suspend,
  auto-terminate. All configured in WHMCS, no code from us.
- **The client area** — our module renders the customer's ServerAlly plan, both meters,
  and their claim link directly on the service page (`serverally_ClientArea`).
- **Business reporting** — revenue, MRR, churn, tax reports.

What WHMCS **cannot** give us: anything about servers, missions, Ally, AI cost, or
errors. That gap is exactly what the ServerAlly admin area exists to fill.

---

## 3. How renewal actually works

### 3.1 The mechanism

The module (`whmcs/serverally/serverally.php`) implements exactly five hooks. This is the
complete list — verified in the code:

| WHMCS event | Fires when | ServerAlly plan becomes |
|---|---|---|
| `CreateAccount` | first order is paid | `pro` (+ provisions account, returns claim link) |
| `SuspendAccount` | invoice overdue past the grace period | `free` |
| `UnsuspendAccount` | overdue invoice gets paid | `pro` |
| `TerminateAccount` | cancelled / terminated | `free` |
| `ChangePackage` | upgrade / downgrade | the new product's plan |

All of them call the same endpoint — `POST /api/admin/entitlements/set` — which is
**idempotent** and only ever moves `users.plan` between two values. It never deletes
anything and never touches the customer's servers or data.

### 3.2 The renewal timeline, month by month

**A customer who pays (the normal case):**

1. **Day −7** — WHMCS generates the renewal invoice and emails it.
2. **Day 0** — customer pays. Invoice Paid, next due date moves +1 month, service stays
   Active.
3. **→ ServerAlly is never called. Nothing happens. They were Pro, they stay Pro.**

**A customer who does not pay:**

1. **Day 0** — invoice overdue. WHMCS sends its reminders (configured in WHMCS).
2. **Day +N** (WHMCS Auto-Suspend setting) — WHMCS suspends the service →
   `SuspendAccount` → **plan = free**. They drop to 2 servers / 30 actions.
   **They keep every server, every mission, every file. Nothing is deleted.**
3. **Day +M** (Auto-Terminate) — `TerminateAccount` → plan = free (already free —
   idempotent, harmless).
4. **They pay late** → WHMCS unsuspends → `UnsuspendAccount` → **plan = pro**, instantly,
   with all their data intact.

### 3.3 ⚠️ The important part: renewal is silence

**There is no `Renew` hook, because WHMCS does not call the module on renewal.** A
successful payment changes nothing in ServerAlly — the customer was Pro and stays Pro.

This is elegant, and it has a consequence nobody has written down:

> **The system fails OPEN.** If a suspend event never reaches us — module error, our API
> down during the WHMCS cron, a WHMCS cron that stopped running, a network blip — the
> non-paying customer **stays Pro forever, and we never find out.** Silence means both
> "everything is fine" and "the integration is broken." We cannot tell them apart.

Failing open is the right *default* (never lock out a paying customer over a network
blip), but it must not be the only behaviour. The fix is cheap:

**Nightly reconciliation, pushed from WHMCS.** A WHMCS cron loops every Active ServerAlly
service and re-asserts its plan by calling `/set` — which is already idempotent, so this
needs **zero new ServerAlly code** for the upgrade direction. Any drift self-heals within
24 hours.

**✅ BUILT (2026-07-16) — Phase 2 is done.** WHMCS sends the full truth once a night;
ServerAlly makes reality match. Idempotent, nothing deleted, drift self-heals in 24h.

```
POST /api/admin/entitlements/reconcile
{ "active_pro_emails": [...], "dry_run": false, "force": false }
→ { upgraded[], downgraded[], unknown[], unchanged }
```

- **Both directions in one call** — a missed suspend downgrades, a missed CreateAccount
  upgrades. WHMCS makes ONE call a night, not N.
- **`whmcs/serverally/hooks.php`** — rides WHMCS's own `DailyCronJob`, so installing the
  module installs the job. No crontab entry.
- **Guarded, because it can mass-downgrade every customer.** An empty list is refused
  (a broken billing query is not "we lost everyone"); more than
  `max(3, 20% of Pro)` downgrades in one night returns **409** rather than obeying a
  truncated list. `force: true` is the deliberate human override; `dry_run: true`
  reports without changing.
- **Admins are never downgraded** — staff are Pro by hand and don't exist in WHMCS.
- **Unknown emails are reported, never created** — provisioning stays with
  CreateAccount, the only event that can email a claim link.
- **Refusals are loud** (409 + WHMCS activity log). A silent 200 would recreate the very
  failure this exists to catch.

It also heals the revenue-leak half of BUG-W1 (§5.1) for free: an orphaned Pro account
isn't in WHMCS's active list, so it is corrected within a day.

### 3.4 Design decision: quota resets on the 1st, not the billing date

The action counter resets on the **first of the calendar month, UTC**
(`metering_service.period_start`), while WHMCS bills on the customer's **signup
anniversary**. These do not line up.

Consequence: a customer who buys Pro on the 28th gets a fresh 1,000 actions three days
later. A small, one-time leak in the customer's favour.

**Decision: keep the calendar month.** It is already built, it is trivially explainable
("your actions reset on the 1st"), and a billing-anchored window means every customer has
a different reset date — which is confusing to support and to the customer. The leak
happens once per customer, costs a few dollars of AI at most, and only ever makes a new
customer happy. Revisit only if the ledger shows people gaming it.

---

## 4. What the ServerAlly admin area is for

**Not billing.** It is an **operator console** that answers the four questions WHMCS
structurally cannot:

1. *"A customer says Ally is broken."* → see their servers, missions and errors — without
   asking for their password.
2. *"Are we making money on this customer?"* → their AI cost vs. their plan.
3. *"Is the platform healthy?"* → signups, active users, AI spend, error rate.
4. *"Why is this paying customer still on Free?"* → did the entitlement call land?

Everything about money is a **link out to WHMCS**.

It is not a new system: `users.is_admin` and the admin-only Dev Door (`/dev`) already
exist. The admin area is **new tabs on the Dev Door**, reusing that auth and the
`ai_usage` ledger.

---

## 5. The admin area — screen by screen

> **✅ Phase 5a SHIPPED (2026-07-17)** — read-only. Four tabs on the Dev Door
> (`/dev` → Overview · Users · Billing events), `admin_service.py` +
> `GET /api/dev/admin/*`. Reuses `is_admin`; no new auth, no new tables, no migration.
> **Read-only is enforced by a test**, not by intent: a route on this surface accepting
> anything but GET fails the suite. Controls are 5b.

### 5.1 Overview — the business at a glance

| Block | Shows | Source |
|---|---|---|
| Users | total · new this month · Pro vs Free | `users` |
| Activity | active in last 7 days · servers under management | `command_logs`, `servers` |
| **AI cost this month** | our real COGS, and cost per action vs. the $0.05 target | `ai_usage` ledger ✅ |
| Health strip | entitlement failures · users at quota · provider errors · **plan drift** | audit + ledger |

**On margin:** revenue lives in WHMCS, cost lives here — neither side can compute margin
alone. Do **not** sync invoices to fix that. Put the Pro price in config
(`PRO_PRICE_USD`) and show *estimated* margin = (Pro users × price) − AI cost, clearly
labelled as an estimate, with WHMCS as the authority for real revenue. One number, no
second source of truth.

### 5.2 Users — the list

Columns: email · plan badge · joined · last active · servers (n/limit) · actions
(n/limit) · AI cost this month · status.
Filters: plan · over quota · inactive · admin · **plan drift**.
Search by email. Each row → user detail, plus "open in WHMCS".

### 5.3 User detail — the support screen

This is where support actually lives.

- **Identity** — email, name, joined, verified, 2FA on/off, language, last login.
- **Plan** — the plan as a **read-only mirror**, its WHMCS reference, and the full
  entitlement history (already audit-logged). Plus a "manage in WHMCS" link.
- **Meters** — actions used/limit this month, servers used/limit.
- **Servers** — name, host, type, status, last seen. **Read-only. Never credentials.**
- **Ally activity** — recent missions and their outcomes, recent AI calls
  (feature/model/cost), recent errors.

### 5.4 Entitlement log — "did billing land?"

Every `entitlement.set` call: when · email · plan · WHMCS reference · created? · IP.
Plus failures and drift. This screen answers question 4 in one look, and it is the only
place the WHMCS↔ServerAlly seam is visible.

### 5.5 AI & cost

Extends the Dev Door's existing Activity tab: cost by day / feature / model, top users by
cost, cost-per-action trend, provider errors.

---

## 6. The controls — what an operator can actually do

Every write action is audit-logged with who did it and why.

| Control | Why it exists | Notes |
|---|---|---|
| **Resend claim link** | The single most likely support ticket: *"I paid but never got the email."* | Regenerates a one-time link. Today only `CreateAccount` returns one — **needs a small endpoint.** |
| **Set plan (override)** | The escape hatch. WHMCS module fails at 2 a.m. and a paying customer is locked out. | Audit-logged, **displayed as an override** so nobody mistakes it for the WHMCS truth. Next reconciliation may correct it — that is intended. |
| **Grant bonus actions** | Goodwill after *our* bug burned their quota. Without it, the only apology is a plan upgrade. | Needs an `action_grants` table (amount, month, reason, granted_by) — small, auditable, keeps the ledger append-only. |
| **Deactivate / reactivate** | Abuse response (§8). | `is_active` already exists. |
| **Force logout** | Credential-compromise response. | Bump `token_version` — already implemented for logout. |
| **Toggle `is_admin`** | Staff management. | Never via signup or billing. |
| **Run reconciliation now** | Fix drift without waiting for the nightly cron. | Depends on §3.3. |

### What an operator can NEVER do — by construction

- **See customer credentials.** They are AES-256-GCM encrypted; the admin area never
  decrypts. There is no screen, no endpoint, no export.
- **Run commands on a customer's server.** No admin path into `connection_manager`.
- **Read chat or Ally content.** The ledger stores counts and labels only — no content
  exists to leak.
- **Delete customer data.** Suspend and terminate only shrink meters. Nothing is deleted,
  ever.
- **Change an invoice, price or refund.** That is WHMCS.

These are not policies to remember — they are properties of the design. Keep them that
way: the moment an admin endpoint can decrypt a credential, our breach radius becomes
every customer's production server.

---

## 7. What we deliberately do NOT build

Listed so a future session does not "helpfully" add them:

- A customer list we can edit → **two truths.** WHMCS owns the customer.
- Orders, invoices, refunds, coupons, dunning → WHMCS does all of it, better.
- Revenue/MRR/churn reporting → WHMCS.
- A payment integration → WHMCS owns the gateway.
- Feature flags per plan → pricing v2 is *open features, two meters*, by design.
- "Log in as customer" impersonation → the fastest route to a credential breach. Support
  gets read-only visibility instead (§5.3).

### 7.1 Removed: the Dashboard "Coming with billing" placeholder

The customer Dashboard carried a dimmed `BillingPreview` tile row — Revenue · Customers ·
Orders, all `—`, labelled *"Coming with billing"* (built 2026-07-08, when ServerAlly might
have grown its own billing). **Deleted 2026-07-16.** It was wrong twice over:

1. **It promised what will now never arrive.** Revenue, Customers and Orders live in WHMCS
   permanently. Leaving the tiles up promises a feature the architecture has decided
   against — and a stale promise on the dashboard is worse than no promise.
2. **It was on the wrong screen entirely.** Those are *FireVPS's* business metrics, not the
   customer's. A customer managing three servers has no use for a "Revenue" tile. Even in
   the world where we did own billing, those numbers belong in the **admin area** (§5.1),
   which only staff can see.

**The rule this leaves behind:** the customer Dashboard is about *their servers*. Business
metrics — ours — belong in the admin area, never on a customer screen. If a future session
wants to surface revenue, it goes in §5.1, behind `is_admin`.

---

## 8. Risks to settle before taking money

**We are about to hold root SSH credentials for other people's production servers, in a
multi-tenant database, for money.** That is a different risk class than any feature:

- **`ENCRYPTION_KEY` is the entire product's security.** If it leaks, every customer's
  server is compromised. It cannot live only in a `.env` on one VPS. Decide storage,
  rotation and recovery **before** the first paying customer.
- **A backup stored next to its key is not a backup** — it is a second copy of the
  breach.
- **Abuse.** Nothing stops someone paying $15 and pointing Ally at a server they do not
  own. The Terms must make ownership the customer's warranty, and §6's deactivate control
  must be fast.
- **`ENFORCE_PLAN_LIMITS` is `false` today.** Every user currently has unlimited servers
  and unlimited AI. It is one switch — but it must be flipped deliberately, after the
  walls are tested with real plan data.

---

## 9. Build phases

### Phase 1 — Prove the money path *(no new features)*
On staging WHMCS: install the module, create the Pro product, run the full lifecycle —
order → pay → provision → claim → suspend → unsuspend → terminate. The module is fully
built and **has never run once**. Everything else depends on it behaving as assumed.

### Phase 2 — Close the renewal gap *(§3.3 — the real architecture work)*
The nightly WHMCS reconciliation cron, plus `POST /api/admin/entitlements/reconcile` for
the downgrade direction. Without this the integration has no failure detection.

### Phase 3 — Arm the meters
Settle the price and allowance ([PRICING-FREE-VS-PRO.md](PRICING-FREE-VS-PRO.md) §11).
Flip `ENFORCE_PLAN_LIMITS`. Verify both walls live, each offering Upgrade → the WHMCS
order page.

### Phase 4 — Front door
Marketing pages on `serverally.firevps.net`, the app on `app.serverally.firevps.net`
(separate hosts: a marketing edit can never break the app, and auth cookies never touch
the marketing page). Legal pages. Working email — claim links are useless without SMTP.

### Phase 5 — Admin area
Dev Door tabs: Overview → Users → User detail → Entitlement log. Then the controls in §6,
starting with **resend claim link** (the most likely ticket) and **plan override** (the
escape hatch).

### Phase 6 — Polish
SSO from the WHMCS client area. Top-up action packs as WHMCS addons. Agency tier if
demand appears.

---

## 10. Recommendation

**Start with Phase 1 — prove the money path on staging.**

Not the admin area. The admin console is real work, but it is only useful once customers
exist, and the first few can be handled with WHMCS plus a database query. The WHMCS module
is the one piece that is fully built and completely unproven, and pricing, walls, marketing
copy and the order button all rest on it. If the first real run surprises us, far better to
find out now than after the marketing page is live.

Phase 1 needs a staging WHMCS and cannot be done from this repo (no PHP here). Phase 2 —
the reconciliation gap — is the first thing that is genuinely ours to build.

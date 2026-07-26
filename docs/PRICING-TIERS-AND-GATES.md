# Three tiers, and how they are enforced

> **Created 2026-07-26.** Asked for by the owner: *"what about the free, pro and pro+ …
> how should be the plans based on server quantity, AllyChat and pro features? Please plan
> this first, then we need to create gate for them."*
>
> This **implements** [PRICING-V3.md](PRICING-V3.md) rather than replacing it: v3's Layer 1
> becomes three tiers, and this doc adds the feature dimension v3 deliberately left out.
> Read v3 first — its hard rule and its cost arithmetic constrain everything below.

---

## 1. The conflict this doc resolves

Two decisions in the repo point in opposite directions:

| Decision | Says |
|---|---|
| [PRICING-V3](PRICING-V3.md) §5 (2026-07-17) | *"every feature on every plan, no feature flags"* — **KEPT** |
| [PRO-FEATURES-PLAN](PRO-FEATURES-PLAN.md) (2026-07-25) | Owner: *"add some more features so we can separate plans based on features"* |

The later instruction wins, but v3's **reasons** were sound and must survive. It rejected
feature gating because gating would:

1. take away safety features,
2. break the free experience that converts people, and
3. add enforcement surface everywhere.

**All three survive if we gate the right axis.** The resolution:

> ### Gate by SCALE and by AUDIENCE — never by capability, and never by safety.

A Free user gets the *same Ally*: same model, same expert procedures, same missions, same
verification gate. What changes is **how many servers**, **how much AI**, and **whether the
features that only exist for agencies are switched on**.

---

## 2. Who each tier is for

This is the whole basis of the split. Getting the buyer right matters more than the numbers.

| Tier | The person | What they are buying |
|---|---|---|
| **Free** | One VPS. A blogger, a founder, someone learning. Genuinely non-technical. | *"I couldn't do this at all on my own."* |
| **Pro** | A developer or a small studio. A handful of servers they care about. Semi-technical. | *"Don't make me spend 3 hours, and don't let me break production at 2am."* |
| **Pro+** | An agency or MSP with **clients**. Servers belong to other people. | *"I need to look professional to my clients, and my team needs access."* |

The jump from Pro to Pro+ is not "more power". It is **other people**: clients who receive
reports, and staff who need logins. That is why the Pro+ features are the client-facing and
multi-user ones, and it is why an agency will pay 4× without arguing.

---

## 3. The tiers

### 3.1 Servers — be generous, this is nearly free for us

A server costs us a metrics poll every five minutes. The market is far more generous than
our old plan: **RunCloud gives 50 servers at ~$19, Laravel Forge gives unlimited.** Our
previous cap of 15 on Pro was uncompetitive ([v3 §7](PRICING-V3.md)).

| | Free | Pro | Pro+ |
|---|---|---|---|
| **Servers** | 2 | 10 | 50, then $1/month each |

Free stays at **2**, not 1 — the current documented figure, and two servers is what lets
someone see the fleet view work at all. Never reduce it.

### 3.2 Ally AI — the honest arithmetic

**This is the part that does not work at the placeholder prices, and the plan has to say so.**

Measured cost is **$0.096 per Ally request** (admin console, 2026-07-17). At the PM's
placeholder of **Pro $4.99**:

> **51 requests consume the entire monthly price.** Before hosting, before support, before
> anything else.

So a meaningful AI allowance **cannot** be bundled into $4.99. This is exactly why v3 split
AI into its own layer. Two consequences, and both must be stated on the pricing page:

**(a) Every tier includes a small allowance** — enough to feel the product, not enough to
be someone's daily driver.

**(b) Beyond it, the customer chooses** — and one option is free for them *and* free for us:

| Option | Cost to customer | Cost to us |
|---|---|---|
| **Bring your own AI** — connect their Claude/ChatGPT account (MCP), or their own API key | $0 | **$0** |
| **Ally subscription** — our hosted AI, added to any tier | +$19/month per 150 requests | we pay inference |

| | Free | Pro | Pro+ |
|---|---|---|---|
| **Ally requests included** | 20/month | 50/month | 150/month |
| **Bring your own AI** | ✅ unlimited | ✅ unlimited | ✅ unlimited |

These allowances are **sized backwards from our real cost**, not picked for the marketing
page. At $0.096/request they leave a positive margin on both paid tiers, which the first
draft of this plan did not — see §4.

### 3.2a DECIDED: AI stays inside the tier at launch, sold separately only if the data demands it

The owner asked directly: *"should we also add Ally action or we keep this as separate?"*

**Decision: one price per tier, with the AI allowance included as fair use. No separate AI
product at launch. Bring-your-own stays available on every tier from day one.**

Three reasons, in order of weight.

**1. A second product doubles a money path that has never run once.** The whole billing
integration is built on a single field — `users.plan` — moved between two values, and each
WHMCS event maps to one plan string. Adding a third tier costs nothing: it is one more value
in the same field. Adding a *separate AI subscription* means a second field, a second WHMCS
product with its own create/suspend/unsuspend/terminate lifecycle, a second thing for the
nightly reconciliation to check, and a state space that goes from 2 to 8 (Pro-but-AI-lapsed,
Free-but-AI-active, and so on) — every combination needing a test. The billing path has not
yet executed a single time in production. **Do not double it before proving it once.**

**2. A published request number becomes a comparison axis we lose on.** If the plan table
says *"Pro — 50 AI requests"*, buyers will compare that against Panelica's undisclosed limit
and against Ploi handing AI over for free. We look worse on a number that is not our real
value. Keep the comparison on **servers and features**, where RunCloud-at-50-servers is the
bar and our feature list is genuinely stronger. So the allowance exists, is visible **inside
the app** on the usage card, and is described on the pricing page as fair use — not as a
headline figure to be shopped against.

**3. Bring-your-own already carries the financial risk.** It is built (the MCP connector
shipped 2026-07-23), it costs us nothing, and it is self-selecting: the heaviest users are
the most technical, so the most likely to already own a Claude subscription. *The customers
we cannot afford are exactly the ones who do not need our AI.* That is the pressure valve,
and it works without a second invoice.

**What this changes about [PRICING-V3](PRICING-V3.md):** v3's two-layer *reasoning* is kept
in full — AI cost stays isolated and re-priceable. What changes is the *packaging*: Layer 2(b)
is not a separate line item at launch, it is a fair-use allowance inside Layer 1. The split
becomes a lever we can pull later rather than a launch requirement.

**When to revisit — write the trigger down now, so it is a measurement and not an argument:**

| Trigger | Then |
|---|---|
| Real cost/request from beta customers stays **above ~$0.06** | Split AI out as a paid add-on |
| A meaningful share of paying users exceed their allowance every month | Sell a top-up pack (+150 requests) |
| Cost/request comes in **under ~$0.04** | Do nothing — raise the included allowances instead and keep one price |

The third row is the most likely outcome, and it is the reason not to build the add-on
yet.

**Shown as requests, never as tokens or credits.** This is v3's one hard rule and it is not
negotiable: the Cursor and Replit blow-ups happened because the metered unit was driven by
*vendor* decisions, not user intent. We choose which model runs the verification gate; the
customer must never be billed for that choice. (Exception, deliberate: **BYO users see full
token and cost detail** — their key, their bill, transparency helps them.)

### 3.3 Features

**Never gated, on any plan.** This list is a competitive weapon and we should say it out
loud on the pricing page — Ploi hides backups on its €8 plan and it is their loudest
complaint.

- Backups, including sending them off the server
- Security scans and malware/intrusion detection
- Incident response, and Ally's refusal to claim success it cannot prove
- Uptime monitoring, and the HTTPS-certificate expiry warning
- **The full Ally experience** — same model, same expert procedures, same missions

> Rationale: a customer whose site is hacked or whose backup was missing does not blame
> their plan, they blame us. And a degraded free Ally would break the moment that makes
> people pay.

**Gated features:**

| Feature | Free | Pro | Pro+ | Why here |
|---|---|---|---|---|
| Ally works on a schedule (autopilot + auto-fix policy) | — | ✅ | ✅ | The single biggest reason to pay. Needs an always-on service. |
| On-call alerts (text/Telegram, keeps calling until answered) | email only | ✅ | ✅ | Costs us real money per text. |
| API keys + webhooks | — | ✅ | ✅ | The market gates this (RunCloud puts it behind $49). |
| Custom runbooks (teach Ally your procedures) | — | 5 | unlimited | Sticky, and ours to build. |
| History kept | 7–30 days | 1 year | 1 year | Storage genuinely costs us. |
| Public status page | 1, our branding | 3 | unlimited, **your branding** | Branding is the agency ask. |
| **Client reports** | — | — | ✅ | The agency resells this. |
| **White-label (remove our name)** | — | — | ✅ | The definition of Pro+. |
| **Team logins** | — | 2 | 10 | Other people = the Pro+ jump. |

### 3.4 The whole picture

| | **Free** | **Pro** | **Pro+** |
|---|---|---|---|
| Price *(recommended — see §4)* | $0 | $9 | $29 |
| Servers | 2 | 10 | 50 + $1 each |
| Ally requests/month | 20 | 50 | 150 |
| Bring your own AI | ✅ | ✅ | ✅ |
| Safety features | ✅ all | ✅ all | ✅ all |
| Ally on a schedule | — | ✅ | ✅ |
| On-call text/Telegram | — | ✅ | ✅ |
| API + webhooks | — | ✅ | ✅ |
| Custom runbooks | — | 5 | ∞ |
| History | 7–30 days | 1 year | 1 year |
| Status pages | 1 | 3 | ∞ + branded |
| Client reports | — | — | ✅ |
| White-label | — | — | ✅ |
| Team logins | — | 2 | 10 |

---

## 4. ⚠️ The price points need the PM's decision

**I got this wrong on the first pass and the correction is the useful part of this section.**
My initial draft bundled 150 requests into Pro and 500 into Pro+. Checking the arithmetic
afterwards showed **every tier losing money**, including at the higher prices I had
recommended:

| Draft | Price | Requests | AI cost | Result |
|---|---|---|---|---|
| Pro (placeholder) | $4.99 | 150 | $14.40 | **−$9.41** |
| Pro (my first recommendation) | $9.00 | 150 | $14.40 | **−$5.40** |
| Pro+ (my first recommendation) | $29.00 | 500 | $48.00 | **−$19.00** |

**At $4.99, 51 requests consume the entire monthly price.** This is precisely the arithmetic
[v3](PRICING-V3.md) identified, and it means a meaningful AI allowance simply cannot be
bundled into a $5 platform price.

### The corrected structure

| Tier | Price | Included requests | AI cost | Left for platform + margin |
|---|---|---|---|---|
| Free | $0 | 20 | $1.92 | −$1.92 — **acquisition cost, accepted** |
| **Pro** | **$9** | 50 | $4.80 | **$4.20 (47%)** |
| **Pro+** | **$29** | 150 | $14.40 | **$14.60 (50%)** |
| *(deferred)* top-up | +$19/mo | +150, stackable | $14.40 | $4.60 (24%) — **not at launch, see §3.2a** |

Both paid tiers now have real margin, and we are still cheaper than the market: RunCloud is
$19 for 50 servers, Ploi €13, Forge $19.

### Two things that could move all of this

- **$0.096 is almost certainly too pessimistic.** It comes from ~13 accounts that are
  essentially us, doing mission-heavy work with the expensive verification model. A customer
  asking *"why is my site slow"* costs a fraction of a 20-step mission. At $0.05 the Pro
  allowance costs $2.50 instead of $4.80; at $0.03, $1.50. **Re-measure on beta customers
  before locking anything** — the number may let us double the allowances at the same price.
- **Free costs us ~$1.92 per active user per month.** That is the price of the moment that
  converts people, and it drops to **$0** for anyone who connects their own AI. Watch it; if
  free-tier abuse appears, reduce the allowance rather than degrading Ally's quality.

### Recommendation

**Launch at Free $0 / Pro $9 / Pro+ $29 with the allowances above, labelled "early access",
and grandfather the beta cohort.** Revisit the allowances — not the prices — once we have a
real cost number from real customers.

## 5. How the gates get built

### 5.1 One place decides, everywhere asks

Everything goes in `entitlements.py`, which already exists and already holds the two
numbers. It gains a feature map and three helpers:

- `limits_for(user)` — the numbers (servers, requests, runbooks, status pages, team seats)
- `allows(user, feature)` — a yes/no for a gated feature
- `require(user, feature)` — raises a clean "this is a Pro feature" error

Nothing else hard-codes a plan name. A feature checks once, at its own entry point.

### 5.2 Three kinds of gate, at few choke points

| Kind | Where it is checked | Already exists? |
|---|---|---|
| **Count** (servers, runbooks, status pages, team) | when creating the thing | servers only |
| **Feature** (autopilot, API keys, client reports, white-label, SMS) | the feature's own create/enable endpoint | no |
| **Fair use** (Ally requests) | the existing AI choke point | ✅ yes |

Deliberately **not** per-request middleware — an existing autopilot task must keep working
if someone downgrades; we block *creating* new ones, we do not break what is running.

### 5.3 🐞 A real bug to fix in the same change

`limits_for` currently falls back to **Free** for any plan name it does not recognise:

```python
return PLANS.get((user.plan or "free").lower(), PLANS["free"])
```

The moment we add `pro_plus`, any code path not updated **silently downgrades a paying
customer to Free limits.** They would hit a wall they paid not to hit, and nothing would
log it.

**Fix: an unrecognised plan gets the most generous limits, and logs loudly.** A paying
customer being throttled by our own bug is far worse than a free user briefly getting extra —
and `users.plan` is not customer-controllable (only the billing integration or a manual
database change sets it), so there is nothing to exploit. This is the same fail-generous
rule the retention sweep already uses.

### 5.4 The UI must explain, never just fail

Every gated control shows a small lock with *"Included in Pro"* and an upgrade link —
**before** the user fills in a form. `GET /api/usage/me` already returns the plan and both
meters; it gains the feature map so the frontend can render locks from one source instead of
duplicating the rules.

### 5.5 Order of work

1. Feature map + `allows`/`require`, and the fail-generous fix (§5.3).
2. Expose it on `/api/usage/me`; add locks in the UI.
3. Count gates: runbooks, status pages, team seats (servers already done).
4. Feature gates at each entry point.
5. Tests: for every gated feature, a Free user is refused and a Pro user is allowed; and a
   **downgrade never breaks something already running**.
6. Leave `ENFORCE_PLAN_LIMITS=false` until the money path is proven and the beta sets the
   numbers.

---

## 6. What is decided vs open

| | |
|---|---|
| ✅ Three tiers, split by scale and audience | Decided here |
| ✅ Safety features never gated | Decided — carried from v3 and the Pro plan |
| ✅ Client reports + white-label + team = Pro+ | Decided here |
| ✅ AI shown as requests, never tokens/credits | v3 hard rule |
| ✅ BYO AI available on every tier | v3 |
| ⚠️ Actual prices | **PM decision.** Recommended $0/$9/$29 — see §4 |
| ⚠️ Included request counts | Sized to today's measured cost; re-check on beta data |
| ✅ AI included as fair use, no separate product at launch | Decided — §3.2a |
| ⚠️ Whether MCP is Free-tier or Pro-and-up | Open (Ploi gates it at Pro) |

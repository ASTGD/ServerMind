# Pricing v3 — "Two layers: platform + your choice of AI"

> **DECIDED 2026-07-17 by the PM.** Supersedes [PRICING-FREE-VS-PRO.md](PRICING-FREE-VS-PRO.md)
> (v2 "open features, two meters"). Evidence behind every claim here:
> [PRICING-METRIC-RESEARCH.md](PRICING-METRIC-RESEARCH.md).
>
> **This doc is the durable record of decisions taken in conversation. Read it before
> touching pricing, entitlements, metering, or the MCP server.**

---

## 1. The decision in one line

**Layer 1 = the platform, priced per server (like the whole market).
Layer 2 = the AI, and the customer chooses: bring their own via MCP, or subscribe to Ally.**

```
┌─ Layer 1 — Platform ────────────────────────────┐
│  Priced per SERVER. Familiar, predictable,      │
│  matches every competitor. We know this cost.   │
└─────────────────────────────────────────────────┘
┌─ Layer 2 — AI (customer chooses ONE) ───────────┐
│  (a) Bring your own  → MCP or own API key       │
│      $0 · unlimited · their fuel · our COGS = 0 │
│  (b) Ally subscription → our hosted AI          │
│      +$X/mo · flat · fair-use limit · no surprise│
└─────────────────────────────────────────────────┘
```

## 2. Why two layers (the argument that decided it)

**It isolates the cost we don't understand from the one we do.**

We know a server costs us ~nothing (a metrics poll every 5 min). We have **no idea** what
a customer's AI costs — the measured $0.096/action comes from ~13 users who are
essentially ourselves, and the *average* is meaningless anyway; the **distribution** is
what matters and we have zero data on it.

Welded into one price, the AI uncertainty contaminates the entire pricing page. Split:

- **Layer 1 can be priced today, with confidence.**
- **Layer 2 can be re-priced as data arrives, without ever touching Layer 1.**

> **We can therefore ship pricing before we understand our AI cost.** That is the whole
> point of the split, and the reason it beats v2.

**Second benefit — the cost risk becomes self-limiting.** The heaviest users are the most
technical, so the most likely to already own a Claude subscription, so the most able to
choose Layer 2(a). *The customers we cannot afford are exactly the ones who don't need
our AI.*

**Third — it beats Ploi on price for the technical buyer:**

| | Monthly |
|---|---|
| Ploi €13 + own Claude $20 | **~$34** |
| ServerAlly ~$15 + own AI (MCP) | **~$15** |
| ServerAlly ~$15 + Ally subscription | **~$25** |

## 3. 🚫 FORBIDDEN: credits, tokens, or per-request billing

**This is the one hard rule. Do not cross it, in any future change.**

Verified evidence (3-0 adversarial verification, see the research doc):

- **Cursor**: *"500 fast responses"* → *"$20 in API credits"* → refunds; founder conceded
  the rollout was mishandled.
- **Replit**: *"$0.25 per checkpoint"* → *"effort-based"* pricing → *"I spent $1k this
  week alone"* vs $180–200/month before.
- **The verified root cause** — the decisive claim:
  > *"The cost overruns were caused by agent behaviour the customer did not request or
  > control — the agent spawned subagents and refactored working code on minor edits —
  > meaning **the metered unit was driven by vendor-side decisions, not user intent**."*

**Tokens are the purest form of that mistake.** *We* choose Opus for the verification
gate. *We* decide a mission runs 20 steps. *We* control prompt size and caching. Billing
tokens = billing the customer for **our** engineering decisions, and punishing them every
time we make Ally smarter.

Strategic cost too: the moment we sell tokens we are **reselling Anthropic**, and the
margin story dies. Ploi gives AI away precisely by never touching inference.

### The distinction that IS allowed

| Showing usage | Charging on it |
|---|---|
| *"120 of 1,000 requests used"* — ✅ fine, this is Ploi's rate-limit line | *"2.4M tokens = $18.30"* — 🚫 the trap |

**One exception, deliberately:** for **BYO/MCP users, show tokens and cost in full.** It
is *their* key and *their* bill — transparency helps them. Same data, opposite meaning.
**Show tokens to BYO users; never to Ally-subscription users.**

## 4. ✅ CORRECTED: our buyer is semi-technical, not non-technical

**Old (wrong) positioning**, still in CLAUDE.md §Product Identity and PRICING v2 §6.1:

> *"Target users: … who own servers but **don't know system administration**."*
> *"The AI already gates the product for our audience. The target user is non-technical —
> **out of actions ≈ out of product**."*

**The contradiction:** Pro allows **15 servers**. *Nobody who "doesn't know system
administration" runs 15 servers.* That person is an agency, an MSP, or a developer. We
priced our paying tier for someone our positioning says does not exist.

**The corrected read — we have two different buyers:**

| Tier | Who | What they buy |
|---|---|---|
| **Free (1–2 servers)** | Genuinely non-technical — the blogger with one VPS | *"I couldn't do this at all"* |
| **Paid (5–100 servers)** | Agency / dev / MSP — **semi-technical** | *"I don't want to spend 3 hours, or break prod at 2am"* |

**The payer is not buying access. They are buying speed and safety.**

**Consequences that follow (do not lose these):**

1. **v2's "no feature gates" rationale is void.** It rested on *out of actions ≈ out of
   product*. A semi-technical user just SSHes in — so the quota is not a conversion lever,
   it is an irritant. Feature-gating stays rejected, but for the *other* v2 reasons
   (never gate safety; don't fragment the magic; enforcement cost).
2. **MCP is promoted** from "adjacent market" to a first-class Layer 2 option — our real
   buyer plausibly wants it.
3. **`SHOW_AI_PROVIDER_SETTINGS=false` (BYO-key hidden on cloud) is now WRONG and must be
   flipped.** That flag was set under the non-technical premise. Under the corrected read,
   hiding BYO suppresses our own pressure valve against our single worst financial risk.
   A BYO customer is ~100% margin — Ploi runs an entire business on exactly that.

## 5. What supersedes what

| Decision | Status |
|---|---|
| v2 "Free 2 servers/30 actions · Pro 15 servers/1,000 actions" | **Superseded** — server counts uncompetitive (§7), actions demoted to fair use |
| 2026-07-02 "one subscription, AI included — **never a second bill**" | **Revisited & overridden.** It was reasoned from the non-technical premise (§4). A semi-technical buyer already pays for AI and understands a separate line. Layer 2 *is* a second line item, deliberately. |
| v2 "every feature on every plan, no feature flags" | **KEPT.** Still right, for the surviving reasons. |
| The two meters existing in code | **KEPT.** They measure always; the action meter simply stops being a headline. |
| `ENFORCE_PLAN_LIMITS=false` | **KEPT for now** — do not arm until Phase 1 (money path) passes AND the beta sets the numbers. |

## 6. Open numbers — deliberately NOT decided

**Do not invent these. They come from the beta, not from theory.**

**PM placeholders set 2026-07-17** (for the marketing site; still placeholders):
**Free $0 · Pro $4.99 · Agency $19.99** — these are **Layer 1 (platform) prices**, and
Layer 2(b) Ally is **additive**. If Ally is ever bundled into $4.99, note that at ~$0.096/
request **52 requests consume the whole plan** — the same arithmetic that does not close for
Panelica (§7). Server counts per tier are **not** set; size them against §7 (RunCloud gives
**50 servers at ~$19**, Forge unlimited) — servers cost us ~nothing, so be generous.

- Layer 1 tier prices and server counts.
- Layer 2(b) Ally subscription price (`$X`) and its fair-use limit (`N`).
- Whether MCP is included from Starter up (Ploi gates it at "Pro and up").

**How they get decided:** run a **beta cohort** — real customers, generous limits, 4–8
weeks. The admin console (`/dev` → Overview, shipped 2026-07-17) already reports real
cost/action per user. Set the numbers from that distribution, then **grandfather the beta
users**. Launch on a stated *early-access* price and say honestly that it is early.

## 7. Competitive anchors (verified — see research doc)

| Vendor | Price | Metric | Their AI cost |
|---|---|---|---|
| **Ploi** | €8/13/30 | Servers (1/5/10/∞) | **$0** — MCP, customer's own AI |
| **RunCloud** | $9/19/49 | Servers (1/**50**/100) | $0 |
| **Laravel Forge** | $12/19/39 | **Flat, unlimited servers** — *"Is Forge usage-based pricing? **No.**"* | n/a |
| **SpinupWP** | $12/19 + $1/extra server | Servers | n/a |
| **ServerPilot** | $5–20/server + $0.50–2/app | Server + app | n/a |
| **Plesk** | €6.60/9.90/16.50 | Per-server licence, tiered by domains | ~0 |
| **Panelica** ⚠️ | **$4.99/9.99/24.99** | Per server, tiered by domains | *"Claude-powered OpsAI"*, **no disclosed limit** |

**⚠️ Our v2 server caps were uncompetitive:** at ~$19, RunCloud gives **50 servers** and
Forge gives **unlimited**, against our planned **15 + a visible action meter**. We looked
worse on both axes at once — and we capped the wrong resource: servers are nearly free for
us; AI is the cost. **Layer 1 must be generous on servers.**

**Panelica is the head-to-head competitor** (same pitch: natural language that *executes*).
Treat its numbers sceptically — at $0.096/action, 52 requests would consume its entire
$4.99 plan, so the arithmetic doesn't close. Worth a hands-on trial.

## 8. Guardrails: rate limit ≠ cost control

Already built and verified working (30/min per user **per server**, Redis fixed-window,
fails open). **It is an abuse guard, not a budget:** at $0.096/action, 30/min = **$172/hour
on one server**; a Pro user could burn a month of revenue in ~7 minutes without ever
tripping it. **Only the fair-use limit protects the bill.**

Two known gaps (neither blocking): it is **per-server so it multiplies** (15 servers =
450/min — should also be per-user across all servers), and it **fails open** if Redis is
down (correct for a safety guard, but Redis is load-bearing for abuse protection in prod).

## 9. Implementation status

- ✅ Both meters, the ledger, the 402 walls, `GET /api/usage/me` — built (v2 work, all reusable).
- ✅ Admin console reports real per-user cost/action — shipped 2026-07-17.
- ⬜ **MCP server** — Layer 2(a). See [MCP-SERVER-PLAN.md](MCP-SERVER-PLAN.md).
- ⬜ Flip `SHOW_AI_PROVIDER_SETTINGS` to true on cloud (§4.3).
- ⬜ Re-tier Layer 1 server counts (§7).
- ⬜ Rename "actions" → **"Ally requests"** in all user-facing copy.
- ⬜ Pricing page promise, verbatim: **"We will never send you a bill you didn't choose."**

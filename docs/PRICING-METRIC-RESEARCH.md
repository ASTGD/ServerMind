# Is "actions" the right pricing metric? — evidence review

> **Status: RESEARCH (2026-07-17).** Triggered by the PM's doubt: *"is an actions
> metric right? What do competitors do?"* Fair question — "actions" is a unit **we
> invented**, and customers must learn it before they can predict their bill.
>
> **Method:** multi-source search, then each claim adversarially verified by 3
> independent checkers (2 of 3 refutes kills it). 105 claims extracted → **13 survived**,
> 6 refuted, 6 unverified.
>
> ⚠️ **This research is INCOMPLETE.** The run hit a session limit: the synthesis step and
> ~20 verifiers failed. The **competitor-panel pricing leg largely did not survive** —
> only Cloudways is confirmed. See §5 before treating any of this as final.

---

## 1. The headline: my first instinct was wrong

Before the research I said the answer was *probably* "price per server, hide the AI cost
behind a fair-use policy." **The evidence does not support that**, and one confirmed
claim argues directly against it:

> **The core economic argument for abandoning flat-rate AI pricing is that agentic usage
> has no natural ceiling, unlike human-paced seat usage — meaning heavy users
> structurally drain a flat plan.**
> — [developer-tech.com](https://www.developer-tech.com/news/ai-coding-tools-usage-based-billing/) (verified 3-0)

And the market is moving **toward** metering, not away:

> **GitHub moved all Copilot plans to usage-based billing on June 1, 2026**, replacing
> premium request units with "GitHub AI Credits" (1 credit = $0.01), justified by agentic
> workflows consuming far more compute than the prior product. — *same source* (3-0)

An invisible fair-use cap would expose us to exactly the tail risk that pushed GitHub the
other way. **So: do not remove the meter.**

## 2. But the backlash is real — and it is not about metering

Both famous blow-ups happened when a vendor moved **from a countable unit to an opaque
one**:

| Vendor | Moved FROM | Moved TO | Result |
|---|---|---|---|
| **Cursor** (Jun 2025) | 500 fast responses + unlimited slow — *a comprehensible quota* | "$20 in API credits", billed at API rates | Refunds; founder conceded the rollout was mishandled (3-0) |
| **Replit** (Jun–Jul 2025) | $0.25 per checkpoint — *a countable unit* | "effort-based" pricing on compute consumed | Replit itself conceded it "can end up being more expensive over the lifetime of a project" (3-0) |

The damage in both cases:

- **Unpredictable bills.** Cursor users "ran out of credits quickly… faced unexpected
  charges after exceeding the $20 limit without setting spending caps, unaware they'd be
  billed for overages." ([TechCrunch](https://techcrunch.com/2025/07/07/cursor-apologizes-for-unclear_pricing-changes-that-upset-users/), 3-0)
- **Order-of-magnitude spikes.** A Replit customer: *"I spent $1k this week alone"* vs
  $180–200/month before. ([The Register](https://www.theregister.com/2025/09/18/replit_agent3_pricing/), 3-0)
- **The lesson stated plainly:** *visibility and predictability of billing matters more
  to customers than the absolute cost level.*
  ([wearefounders](https://www.wearefounders.uk/cursors-pricing-disaster-the-full-timeline-of-how-an-ai-coding-darling-burned-its-most-loyal-users/), 3-0)

## 3. The claim that decides it for us

> **The cost overruns were caused by agent behaviour the customer did not request or
> control — the agent spawned subagents and refactored working code on minor edits —
> meaning the metered unit was driven by vendor-side decisions, not user intent.**
> — [InfoWorld](https://www.infoworld.com/article/4059876/replit-update-sparks-developers-dissatisfaction-over-pricing.html) (verified 2-0)

This is the real dividing line. Not *metered vs unmetered* — **user-controlled vs
vendor-driven**.

- **Bad unit:** consumption our agent decides (tokens, compute, "effort"). The customer
  cannot predict it, cannot control it, and gets punished when *we* make the agent
  smarter. Cursor and Replit both crossed this line.
- **Good unit:** something the customer *does*. Countable before they do it.

**ServerAlly's action is already the good kind** — and this is the important finding.
We charge **1 action per user request**. A mission that makes 20 model calls, escalates
to Opus, and runs a verification pass is still **1 action** (`AI-METERING.md`: follow-up
calls carry 0). Our own errors are free. The customer is billed for *asking*, not for
what Ally decides to do about it.

That is the exact property Replit violated — and we already have it, by design.

## 4. Recommendation

**Keep both meters. Change the packaging, not the model.**

1. **Servers stay the headline price metric.** It is what this market already trains
   buyers on — Cloudways' primary metric is the server, and multiple apps run on one
   server at no extra fee ([pricing page](https://www.cloudways.com/en/pricing.php),
   3-0). It is also honest: servers are our real per-server infra cost.
2. **Keep the action meter — it is our only defence against the no-ceiling problem (§1).**
   Removing it is the one option the evidence rules out.
3. **Rename "actions" to something a non-technical person already understands** — e.g.
   *"Ally requests"* or *"tasks"*. The unit is fine; the invented word is the risk.
4. **Never auto-bill an overage. This is the whole Cursor mistake.** Our design already
   hard-stops at the wall with an upgrade offer and no surprise charge — that is a
   *feature*, and it should be said out loud on the pricing page: **"we will never send
   you a bill you didn't choose."**
5. **Never charge for Ally's internal decisions.** Already true. Protect it: if a future
   change ever bills per model call or per mission step, we become Replit.
6. **Set the allowance generously** and re-read it against customer-shaped usage. §9a's
   $0.096/action tail risk is bounded by the allowance, not the price.

## 4b. The competitor leg — completed 2026-07-17 (vendors' OWN pricing pages)

The gap in §5 is now filled by reading each vendor's own page (primary sources, not blogs).

| Vendor | Price | **Price metric** | Usage meter? |
|---|---|---|---|
| **Ploi** | €8 / €13 / €30 | **Servers** (1 / 5 / 10 / unlimited) | No. API **rate limit** 60/120/240 req/min |
| **RunCloud** | $9 / $19 / $49 / $399 | **Servers** (1 / 50 / 100 / 500) | No. API **rate limit** 120 req/min, 10k/month (Business) |
| **Laravel Forge** | $12 / $19 / $39 | **Flat** — *unlimited* servers & sites | **No** — *"Is Forge usage-based pricing? **No.** Forge uses flat-rate monthly pricing."* |
| **SpinupWP** | $12 / $19 base | **Servers** (+$1–10/extra server, +$2/user, +$1/site monitor) | No |
| **ServerPilot** | $5 / $10 / $20 per server | **Server + app** ($0.50–$2 per app), billed hourly | No |
| **GridPane** | Free (≤25 sites); from $19 | **Per managed server** | No |
| **Plesk** | €6.60 / €9.90 / €16.50 | **Per-server licence**, tiered by **domain count** (10 / 30 / ∞) | No |
| **Cloudways** | hourly by server spec | **Server** | Meters GB (disk/bandwidth) |

### Three findings that matter

**1. Servers is the market's metric. Near-unanimous.** Every vendor prices on servers,
sites/domains, or a flat fee. **Not one meters usage of the product itself.** An
"actions" headline would make us the only vendor in the category asking buyers to learn a
new unit.

**2. "Requests/minute" in this market means a RATE LIMIT, not a price.** This is what the
PM saw in Ploi. Ploi tiers API access at 60/120/240 req/min; RunCloud at 120 req/min and
10k/month. It sits in the plan table as a **guardrail**, stated plainly, and nobody
riots over it — because it is not a currency, is never billed, and never produces a
surprise invoice. **That is the precedent for how our AI limit should be presented.**

**3. ⚠️ Our server cap is uncompetitive, and we capped the wrong thing.**

At roughly the same price point:

| | Price | Servers |
|---|---|---|
| RunCloud Professional | $19 | **50** |
| Laravel Forge Growth | $19 | **unlimited** |
| Ploi Pro | €13 (~$14) | 10 |
| **ServerAlly Pro (planned)** | **$15–19** | **15** |

A shopper comparing at $19 sees *"unlimited servers"* vs our *"15 servers + 1,000
actions"*. We look worse on both axes at once.

And the cap is on the wrong resource. **Servers are nearly free for us** — a metrics poll
every 5 minutes and some probes; going 15 → 50 costs cents. **Our real cost is AI**
(§9a: ~$0.096/action). We are being stingy with the cheap, *visible, comparable* thing
and generous with the expensive one. That is exactly backwards.

## 4bb. How do our competitors source their LLM? (2026-07-17)

PM asked: *"can you guess what LLM they use? I suppose they host their own."*
**Answer: nobody in our category hosts their own model — and the most interesting one
runs no LLM at all.**

| Competitor | AI feature | LLM source | **Their AI cost** |
|---|---|---|---|
| **Ploi** | **MCP server** — connect your own AI client | **None. Ploi hosts no LLM.** | **$0** |
| **Panelica** | **OpsAI** — executes ops from natural language | *"Claude-powered OpsAI (15 expert profiles)"* (their own claim) | Unknown; bundled |
| **RunCloud** | community/3rd-party MCP into Claude Desktop | Customer's own client | $0 |
| **cPanel / Plesk** | Plesk "Smart Updates" = automated WP plugin updates | n/a — not a real assistant | ~$0 |

### 1. Ploi's answer to AI is to not buy any: MCP

> *"Works with Claude · Claude Code · ChatGPT · Cursor · VS Code · Windsurf + any MCP
> client"* — included in **Pro and up, no extra charge, no usage limits**.
> ([ploi.io/features/mcp](https://ploi.io/features/mcp))

Ploi exposes an MCP server and **the customer's own AI subscription pays for every
token.** Ploi's AI COGS is **zero**, which is exactly why they can offer it "unlimited"
inside a €13 flat plan with no meter. This is the cleanest solution to the AI-cost
problem in the entire market, and it costs them nothing to maintain.

**Why it doesn't kill us:** MCP requires the customer to already own and configure an AI
client. That is a *developer*. Our buyer is the person who doesn't know what MCP is — for
them the hosted AI *is* the product. Ploi's model serves the customer we deliberately
don't target.

**But it is our BYO-key option, validated.** We already have that escape valve. Shipping
an MCP server later would serve technical users at **$0 marginal cost** — a cheap
adjacent market, not a threat.

### 2. Panelica is the real head-to-head competitor

Same pitch as ours — natural language that *executes*, not a chatbot that suggests:
*"Create a domain with SSL and WordPress"* handled end-to-end, plus log/CPU/MySQL
diagnostics. **Claude-powered**, by their own account.

Their pricing ([panelica.com/pricing](https://panelica.com/pricing)) — flat licence per
server, tiered by **domains**:

| Plan | Price | Domains |
|---|---|---|
| Starter | Free | 3 |
| Professional | **$4.99** | 15 |
| Business | **$9.99** | 50 |
| Enterprise | **$24.99** | Unlimited |

**And they disclose no AI limit whatsoever** — no credits, no quota, no fair-use line, no
BYO-key requirement.

**Treat that with real scepticism.** At our measured ~$0.096/action, **52 AI requests
would consume the entire $4.99 plan.** Claude-powered agentic server ops with no
disclosed cap at $4.99/mo is not arithmetic that closes. The plausible explanations:
their AI is thin/rarely used; there is an undisclosed internal cap; they are subsidising
for growth; or OpsAI is more marketing than product. **Unverified either way** — worth a
hands-on trial before we treat it as a benchmark.

**What it does tell us:** a competitor is publicly anchoring "AI included, no visible
meter" at **$4.99–24.99**. If that holds, our $15–19 *with* a visible action meter is a
weak offer by comparison. This strengthens §4c: the meter should be fair-use, not a
headline.

### 3. Why nobody self-hosts (and neither should we, yet)

Self-hosting is real only at Cursor's scale — and even Cursor built **Composer** on an
**open Kimi K2.5 base** rather than training from scratch, while still defaulting to
Claude Sonnet for hard work. At our scale the maths is brutal: our AI spend is **~$33/mo**
against **~$700–1,500/mo** for one always-on GPU. Break-even is somewhere past
**$1,500/mo** of API spend — hundreds of active customers.

And our failure mode is not Cursor's. Bad code can be reviewed; a wrong root command
deletes a database. The safety-critical path (verification gate, blocklist judgement,
incident response) is exactly where a smaller open model degrades most. **Revisit only
past ~$1,500/mo, and even then only for the cheap high-volume path** (explanations,
classification) — never the safety-critical one. Our Smart Model Ladder already captures
most of that saving (Haiku for explains, Sonnet default, Opus only to verify) plus
50–70% off input via prompt caching.

## 4c. Revised recommendation (supersedes §4)

**Be generous where we're cheap; strict where we're expensive; and never invent a currency.**

1. **Headline metric: servers — and raise the cap sharply.** It is the market's unit, the
   one buyers can count before paying, and it costs us almost nothing. Something like
   50 (Pro) makes us comparable to RunCloud instead of visibly worse.
2. **Keep the AI limit — but present it as fair use, exactly like every competitor's API
   rate limit.** One honest line in the plan table (*"fair use: ~N Ally requests/month"*),
   not a headline, not a currency, never billed. §1's no-ceiling problem is real, so the
   limit must exist; §4b.2 shows the market already accepts this shape.
3. **Never auto-bill an overage.** The whole Cursor mistake. We hard-stop and offer an
   upgrade — say so on the pricing page as a promise: *"we'll never send you a bill you
   didn't choose."*
4. **Never charge for Ally's internal decisions.** Already true (1 action per user
   request, regardless of how many model calls it triggers). Protect it — billing per
   model call or mission step is the day we become Replit (§3).
5. **Rename "actions"** → *"Ally requests"*. The unit is fine; the invented word is the risk.

**The net effect:** we compete on the axis buyers already understand (servers), we stop
looking worse than RunCloud at the same price, and our real cost driver stays controlled
by a guardrail the market has already normalised.

## 5. What this research did NOT establish

Being honest about the gaps:

- ~~Competitor panel pricing is mostly unverified.~~ **Resolved in §4b** by reading each
  vendor's own pricing page. Remaining caveat: **RunCloud's figures came from a search
  summary, not its page directly** (the page renders pricing via JS) — confirm RunCloud's
  numbers before quoting them externally. All others are from the vendors' own pages.
  Prices move; re-check before any public comparison.
- **xCloud and cPanel were not checked.** cPanel's model is known to be per-account
  tiers, but it is unverified here.
- **Two relevant claims went unverified** (neither confirmed nor refuted): that
  credit-based systems grew 126% YoY, and that Notion/Slack/Loom moved *away* from
  separately-metered AI add-ons. The second would strengthen the fair-use case if true —
  it is currently unproven either way.
- **No value-metric theory** (Price Intelligently, Poyar et al.) survived verification, so
  §3's reasoning rests on the observed Cursor/Replit cases, not on pricing literature.

**Worth completing** when the session budget allows: a direct pass over each competitor's
own pricing page. That is the leg that would tell us whether per-server is priced per
server, per site, or per seat in our actual market.

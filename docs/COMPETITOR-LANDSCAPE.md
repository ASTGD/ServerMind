# Competitor landscape — who is actually competing with us

> **Created 2026-07-17.** Corrects a framing error: the Ploi teardown
> ([COMPETITOR-PLOI-TEARDOWN.md](COMPETITOR-PLOI-TEARDOWN.md)) called Ploi *"our closest
> per-server competitor."* **That is wrong** and led to over-weighted conclusions. This
> doc is the corrected map. Read it before doing any more competitor research.

---

## 1. The distinction that matters: two different jobs

| | **BUILD & DEPLOY** | **OPERATE & REPAIR** |
|---|---|---|
| Job | Blank VPS → working web server → deploy code | A server that exists, usually when something is wrong |
| Trigger | *"I want my app live"* | *"Something is broken"* |
| Who | Ploi · RunCloud · Forge · SpinupWP · GridPane · ServerPilot · Cloudways | **ServerAlly** · Panelica OpsAI · servermind.dev |

**We are in the right-hand column.** Ploi's 27-task provisioning recipe *is* their product;
we don't provision at all. Nothing in Ploi diagnoses, explains or repairs — there is no
*"my site is down"* flow, no malware handling, no incident response, and their entire AI
story is MCP (i.e. someone else's AI).

### What this corrects

- ❌ **"At ~$19 RunCloud gives 50 servers and we look worse."** Apples-to-oranges. A buyer
  is not choosing between us and RunCloud — different jobs. **Server-count parity matters
  much less than [PRICING-METRIC-RESEARCH.md](PRICING-METRIC-RESEARCH.md) §4b implied.**
- ⚠️ **The Ploi feature-borrow list is half-suspect.** UX patterns transfer (they are
  job-agnostic): sudo mode, *"safe to leave this screen"*, named task checklists,
  connected-applications tab. But *"should we build Projects / a Marketplace"* must be
  re-tested against **our** buyer, not adopted because Ploi has them.

### What still holds

- ✅ **Servers, not usage, is the pricing metric.** These vendors train what our buyer
  *expects to see*, even solving a different job. Pricing v3 stands.
- ✅ **The MCP model** — AI plumbing is job-agnostic.
- ✅ **UX borrows** — good UX transfers.

## 2. servermind.dev — checked 2026-07-17

Our own rebrand decision (CLAUDE.md, 2026-06-29) flagged this as *"a near-identical AI VPS
assistant."* **Verified: the positioning really is near-identical; the product is not a
commercial threat.**

**Their pitch:** *"Manage your server by talking to it."* — vs our *"Manage any server in
plain English."* Repo description: *"Self-hosted AI assistant to monitor and manage your
Linux VPS from chat — PM2, Redis, MySQL, Nginx & more. Bring your own AI (free Gemini or
Claude)."*

**Reality check** (GitHub `AjjlalAhmed/servermind`):

| | |
|---|---|
| Created | **2026-06-13** — one month old |
| Stars / forks | **4 / 0** |
| Last push | 2026-07-05 |
| License / stack | MIT · TypeScript |
| Team | **Solo developer** |

**A solo side project, one month old.** Not a market threat today.

### But it is architecturally the opposite of us — and that is the useful part

| | servermind.dev | ServerAlly |
|---|---|---|
| Model | **Open-source, self-hosted, free** | **SaaS, hosted** |
| Install | **Agent ON the box** (Bun + PM2, ~2-min installer) | **Agentless** — we SSH in |
| Access | **Desktop app** (Mac/Win) over an SSH tunnel — no domain, proxy or certs | Web app |
| AI | **BYO only** — free Gemini or Claude | Hosted Ally **+** BYO |
| Scope | **One VPS** | **Fleet** |
| Depth | Chat + *"arm mutations"* | Missions, verification gate, incident response, threat scans, reports |
| Maturity | 1 month, 4 stars | Live-tested on real compromised production |

### Three things worth taking seriously

1. **⭐ "Nothing leaves your box."** They lead with this as a *feature*. It is the sharpest
   articulation of **the #1 objection to our entire model** — we hold root credentials for
   other people's production servers on our infrastructure. **The `/security` page on the
   new landing site must answer this head-on.** If we don't, the first technical
   prospect who thinks of it will not ask, they will just leave.
2. **"Free with Gemini" validates Layer 2(a).** An independent builder reached the same
   conclusion we did: BYO-AI is how you make the economics work. Reinforces flipping
   `SHOW_AI_PROVIDER_SETTINGS` ([PRICING-V3](PRICING-V3.md) §4.3).
3. **"Arm mutations when you actually want to change something"** — the same insight as our
   approval gates, independently arrived at. Read-only by default is becoming the category
   norm, not our invention. Worth saying we do it *better* (verify gate, quarantine-not-
   delete), not merely that we do it.

### And it confirms the rebrand was right

The name collision is live and real: `servermind.dev` ranks for the exact phrase, with an
identical pitch. Renaming ServerMind → **ServerAlly** (2026-06-29) avoided a genuine SEO
and brand-confusion problem. *(Note: our repo directory is still `ServerMind` — cosmetic,
but a rename would remove a lingering confusion.)*

## 3. Panelica OpsAI — the real head-to-head, NOT yet checked

From [PRICING-METRIC-RESEARCH.md](PRICING-METRIC-RESEARCH.md) §4bb — the only vendor found
doing our job commercially:

- *"Claude-powered OpsAI"*, natural language that **executes** (*"Create a domain with SSL
  and WordPress"* → 11 steps), plus CPU/log/MySQL diagnostics.
- **$4.99 / $9.99 / $24.99** per server, tiered by domains — with **no disclosed AI limit**.
- ⚠️ **The arithmetic should not close.** At our measured ~$0.096/request, **52 requests
  consume the entire $4.99 plan.** Either their AI is thin, there is an undisclosed cap,
  it is subsidised, or OpsAI is more marketing than product.

**This is the one competitor worth a hands-on trial.** Everything else in the
operate-and-repair column is either a side project (§2) or enterprise SRE tooling aimed at
a different buyer.

## 4. The honest competitor list

1. **A freelance sysadmin / agency retainer** — the real incumbent. That is who Ally replaces.
2. **Panelica OpsAI** — the genuine head-to-head (§3).
3. **Doing nothing** — the site stays broken. More common than any vendor.
4. *(watch)* **servermind.dev** — no threat now; interesting if it gains traction.
5. **Build-and-deploy panels** — adjacent, not competing. Useful as UX and pricing anchors only.

## 5. Rule for future competitor research

**Do not tear down another build-and-deploy panel.** RunCloud, Forge, SpinupWP and GridPane
all do Ploi's job; three more teardowns would repeat the same lesson at 3× the cost.

Research effort belongs on the **operate-and-repair** column, and on the incumbent that
actually holds the budget — **the human sysadmin**.

## 6. The open product question

**We do not provision servers.** We import existing ones. But an agency with 10 servers had
to create them somehow, and provisioning is Ploi's entire core.

Deliberate scope (we are the operator, not the builder) or a real gap? **Unresolved — worth
a PM decision**, and bigger than anything on the borrow list.

# Market research — what a complete server-management product looks like in 2026

> **Compiled 2026-07-25.** Commissioned after a strategy change by the owner:
> *"Ally is not the primary product now… we have to introduce more features like Ploi,
> ServerPilot, servermind.dev etc. and create plans and pricing based on the server
> quantity, pro-features. I want ServerAlly will cover all these services already in the
> market."*
>
> **This doc supersedes the conclusion of [COMPETITOR-LANDSCAPE.md](COMPETITOR-LANDSCAPE.md).**
> That doc closed with an open question (§6): *"We do not provision servers… Deliberate
> scope or a real gap? Unresolved — worth a PM decision."* **That decision is now made:
> we expand.** Its §5 rule ("do not tear down another build-and-deploy panel") is therefore
> void — we now need exactly that detail, because we intend to build those features.
>
> Pricing architecture in [PRICING-V3.md](PRICING-V3.md) is **confirmed, not replaced** —
> see §7.

---

## 0. The five findings that should change what we do

1. **The baseline is bigger than we thought, and half of it is free.** Ten control panels
   built by unrelated teams over 25 years converged on the *same ~20 capabilities* (§3).
   Five of those panels cost **$0**. We cannot win on baseline coverage and must not price
   as though we could.
2. **"AI that manages your server" is already commoditised. "AI that manages it *safely*"
   is not.** Hostinger's Kodee, Cloudways Copilot, Panelica, CtrlOps, aaPanel and Chaterm
   all ship chat-to-server today. **Not one** of the 15+ AI products reviewed has a
   verification gate, resumable missions, injection defence, or an incident narrative — all
   of which we already shipped and none of which we market (§5, §6).
3. **Our closest threat is not a startup — it is Hostinger.** Kodee reads logs, runs
   commands and applies fixes across ~200 VPS actions over MCP, **included free inside a
   $6.49/mo VPS**, reportedly resolving 91% of 914,000 conversations autonomously.
4. **A large price band is empty.** Hosting panels sit at $8–49/mo; enterprise AI-SRE starts
   at $99/mo and centres on $2,000+/mo. **Nothing serious occupies the middle**, which is
   exactly where our semi-technical agency/MSP buyer lives.
5. **Our per-server plan is uncompetitive and we capped the wrong resource.** At ~$19,
   Forge gives *unlimited* servers and RunCloud gives *50*; we planned **15**. Servers cost
   us almost nothing. (This confirms [PRICING-V3](PRICING-V3.md) §7 — it has not been fixed yet.)

---

## 1. Method and confidence

Five parallel researchers read **vendors' own pricing, feature and documentation pages** as
the primary source, with review sites, forums and GitHub used only for sentiment and
traction. A sixth pass verified published AI-SRE prices directly from AWS Marketplace
listings rather than search summaries.

**Confidence notes — read before quoting any number:**

- Prices are **list prices as of 2026-07-25**. Marketplace listings are anchors, not
  transaction prices — one third-party dataset shows ~28% average negotiated discount.
- Two search-summary figures were caught as **false** by fetching the source directly
  (a claimed "$1,000,000" listing is a $1.00 placeholder; a claimed "$25 per investigation"
  is $15.00). Treat any AI-SRE price not read off the vendor's own page as suspect.
- One researcher's output was produced while the safety classifier was unavailable; its
  figures carry citations and self-reported corrections, but the enterprise AI-SRE numbers
  in §7.4 are the least load-bearing part of this doc by design.
- Three researchers were killed by a session limit *after* writing their reports; the full
  reports are recovered and complete. Items they marked UNVERIFIED are flagged as such here.
- **Moss (moss.sh) is dead** — domain lapsed, DNS SERVFAIL since ~2026-03-22. Search
  engines still surface squatter content as if it were live. Do not cite it.

---

## 2. The market map

| Band | Who | Price | AI depth | Threat to us |
|---|---|---|---|---|
| **Bundled free, mass market** | **Hostinger Kodee** | **$0** (inside a $6.49/mo VPS) | Executes fixes, ~200 MCP actions | **Highest** — same promise, no price |
| **Cheap AI server tools** | CtrlOps, Panelica OpsAI | $4.99–$9.99/mo; CtrlOps **$7/user unlimited** | Panelica executes; CtrlOps suggests only | **High on price**, low on depth |
| **AI repair add-on** | **Cloudways Copilot + SmartFix** | $3.99–$80/mo, **credit-metered** | Diagnoses + executes on approval | **High** — proves the model, sets the price |
| **Deploy platforms** | Ploi, RunCloud, Forge, SpinupWP, ServerPilot | $9–$49/mo | **None** (Ploi ships MCP only) | Medium — feature + price anchor |
| **Control panels** | cPanel, Plesk, DirectAdmin, CyberPanel, aaPanel, Hestia, CloudPanel | **$0–$70/mo** | aaPanel shipped BYO-AI + MCP; cPanel/Plesk are roadmap | Medium — sets the baseline |
| **Agency / managed hosting** | GridPane, Enhance, Cloudways, Rocket.net, Kinsta | $0–$675/mo | Rocket.net ships free MCP | Medium — sets agency expectations |
| **Self-hosted PaaS** | Coolify, Dokploy, CapRover, Dokku, Easypanel | $0–$16.90/mo | MCP only, **no agent** | Low-medium — price anchor |
| **Enterprise AI SRE** | Cleric, NeuBird, Flip, Resolve, Datadog Bits | **$99/mo → $150k/yr** | Mostly investigate-and-recommend | Low — different buyer |

**The empty band:** nothing credible sits between **$49 and $99/mo**. That gap is our target.

---

## 3. ⭐ The baseline — what "complete" means in this market

Ten independently-built panels agree on this list. **A product missing Tier 1 is not
perceived as a server-management product at all**, however good its AI is.

### Tier 1 — universal; absence is disqualifying

Website/vhost creation · **DNS records + a real nameserver** · **full email stack**
(SMTP/IMAP, webmail, spam, DKIM/SPF/DMARC) · databases **+ phpMyAdmin specifically** ·
SSL auto-issue **and** auto-renew · FTP accounts · web file manager · **PHP version per
site** · cron · backups + restore · account/user management **with a reseller tier** ·
resource monitoring · **one-click WordPress installer**.

> Email is not optional in this market: it is cited as **42% of provider support time**,
> and CloudPanel's omission of it is its single most-cited limitation.

### Tier 2 — expected; absence is a real objection

Firewall management (**cPanel's own users rank this their #1 request at 46.3%** — the
incumbent still doesn't have it natively) · **offsite backup targets** (S3/SFTP/Drive) ·
security scanning / malware / WAF · browser terminal · API · CLI · staging/cloning.

### Tier 3 — differentiators; open ground

**Multi-server management from one place** — the structural weakness of the whole panel
category, since panels are licensed and installed *per server* · git integration · mobile
app · **AI that acts** (cPanel's is roadmap and explicitly *"assist but not independently
act"*; Plesk's Copilot has no ship date).

### The three-sentence version

> Baseline = sites, DNS, email, databases, SSL, FTP, files, PHP versions, cron, backups,
> users/resellers, monitoring, one-click WordPress. All ten panels do essentially all of
> it, and five do it for **$0**. So we must either cover the baseline *as a floor* or sit
> deliberately above it — and win on the three things no incumbent has: **multi-server,
> AI that actually acts, and security response.**

---

## 4. Where ServerAlly actually stands

From a full code inventory (not from CLAUDE.md, which was found to contain six stale claims).

**Strong — genuinely ahead:** agentic missions (durable, resumable, detached, concurrent)
with an adversarial **verification gate** · 16 expert skill runbooks · proactive threat
detection + guided incident response · AI incident/server reports · MCP with full OAuth 2.1
(22 tools, 3 consent tiers) · teams/roles enforced on every execution path · browser
terminal · SFTP file manager with secret redaction · security scanning (19 Linux + 5
Windows checks) · breadth: SSH + WinRM + RDP + panels + 5 clouds · 8-language AI.

**The gaps — one consistent pattern: we do not manage lifecycle objects.**

| Gap | Reality today | Market status |
|---|---|---|
| **Offsite backups** | Backups write to the **same server** | Tier 2, near-universal |
| **DNS management** | None — Ally can only *read* DNS | **Tier 1** |
| **PHP/Node version switching** | Detect only | **Tier 1** |
| **Uptime / HTTP monitoring** | CPU/RAM/disk alerts only — no "site is down" | Universal |
| **Sites model on plain servers** | Only works on CyberPanel | **Tier 1** |
| **Deploy pipeline** | No push webhook, no rollback, no zero-downtime, no staging | Universal in Group A |
| **Queue workers / supervisor** | None | Common |
| **Server log viewer** | We log *ourselves*, not the server | Tier 2 |
| **Firewall rule manager · SSH key manager** | Playbooks only, no UI | Tier 2 |
| **White-label / client portal** | Nothing | Always gated, always present in agency tier |
| **Cloud lifecycle** | Import only — cannot create/resize/reboot/destroy | Universal in Group A |
| **Public API keys · CLI** | Neither (MCP is our only programmatic surface) | Tier 2 |

**Email, nameserver, phpMyAdmin, FTP accounts and reseller accounts are also missing** —
and §8 argues we should deliberately *not* build them.

---

## 5. The five real threats, ranked

1. **Hostinger Kodee — free, mass-market, same promise.** Executes fixes in the VPS
   terminal, ~200 actions over MCP, included at no charge.
   **Counter (all factually true):** *"Your host's AI only manages your host's servers."*
   An agency with servers at five providers cannot use Kodee at all. Plus: *"it fixes; we
   prove it fixed"* (verification gate), and *"it answers; we run the whole job"* (missions).
2. **Cloudways Copilot + SmartFix — proves the model and sets the price.**
   $3.99/$9.99/$19.99–80 per month for 4/12/25–100 AI credits. **They explicitly do NOT
   auto-fix application-level problems (WordPress 5xx) — only diagnose them.** Our WordPress
   rescue missions do exactly that, live-proven. That is a precise, provable gap.
3. **aaPanel — already shipped our exact bet.** A BYO-API-key AI assistant *and* an official
   MCP server, on a very large install base. "Nobody has done this" is **false** — say
   *"acting safely across a whole fleet"* instead of *"AI in a panel"*.
4. **Ploi — the only deploy platform with a first-party OAuth MCP server** (60 tools, Pro+).
   Its design choices mirror ours almost exactly. Also the only one with white-label +
   client billing (Ploi Core).
5. **cPanel putting MCP in WHM** (published 2026 roadmap). Our lead is **months, not years**,
   and theirs will be pre-installed. Our defensible edge is **cross-server** MCP — one
   connection, whole fleet — versus their inevitably per-server scope.

**Also worth knowing:** Rocket.net already gives every customer a free MCP server. **"We
have MCP" is no longer a differentiator.**

⚠️ **servermind.dev — corrected 2026-07-25.** This doc (and COMPETITOR-LANDSCAPE) judged it
from its GitHub repo (4 stars, solo, one release) and called it a non-competitor. Read off
the **product site** it is far more developed: fleet management via dial-out agents, live
dashboard, custom commands, alerts incl. **expiring TLS certificates**, daily health emails,
a desktop app, WireGuard mesh — **completely free (MIT), with free Gemini AI, no paid tier**.
It is not a revenue rival, but it **sets the free floor we must price against**. See
[PRO-FEATURES-PLAN.md](PRO-FEATURES-PLAN.md) §2.

---

## 6. What we have that nobody else does

Verified across all 15+ AI products reviewed — **not one** has:

1. **A verification gate** — an independent, read-only-enforced adversarial check that the
   fix actually worked. Nobody else checks outcomes.
2. **Multi-step resumable missions** with per-step safety validation, mid-mission approval,
   budgets and detached execution. Every competitor's AI is single-shot.
3. **Prompt-injection defence on server-derived data** — nobody else even discusses it,
   despite all of them feeding attacker-controllable logs into an LLM.
4. **Packaged expert runbooks with a routing layer.**
5. **Incident narratives from a durable transcript** — an owner-facing story of what happened.

> Independent corroboration: **Portainer built an LLM chatbot, deleted it, and rebuilt it**
> as an assistant that *"fetches live diagnostic data before answering"* and *"avoids
> executing irreversible operations directly."* A funded competitor re-derived our Live Look
> + approval gate after failing with the naive version.

**All five are shipped and unmarketed. Our engineering lead is far bigger than our
marketing lead.**

---

## 7. Pricing — what the evidence says

### 7.1 The metric is confirmed: servers, never usage

Every surviving vendor gates on servers (or servers × apps). **Not one meters usage of the
product.** Forge states it outright: *"Is Forge usage-based pricing? No."* The only
"requests/minute" numbers in this market are **API rate limits printed in the plan table**
(Ploi 60/120/240, Forge 60/min) — a guardrail, never a billed unit. **This is the precedent
for how our AI limit should read.** [PRICING-V3](PRICING-V3.md) Layer 1 is validated.

### 7.2 $19 is the anchor — and our server count is below median

| At ~$19/mo | Servers |
|---|---|
| Laravel Forge Growth | **Unlimited** |
| RunCloud Professional | **50** |
| Ploi Pro (€13) | 10 |
| SpinupWP Advanced | 1 + $1/extra |
| **ServerAlly Pro (planned)** | **15** ⚠️ |

Servers cost us almost nothing. **Be generous.**

### 7.3 What the market gates behind higher tiers — the answer to "pro-features"

**Always gated (safe to gate):**
white-label / branded panel · **client billing and invoicing** · client sub-accounts and
dashboards · automated provisioning from an order · commercial perks (directory listings,
revenue share) · **API access** (RunCloud gates it to $49).

**Gated by *some*, and it is their loudest complaint:**
Ploi puts **backups, monitoring, zero-downtime deploys, the file explorer and even support**
behind Pro €13 — eleven features struck through on its €8 plan. RunCloud gates staging and
team seats.

**Never gated anywhere:** SSL · SSH/SFTP access · migrations · staging (in Group B) · and
notably **team roles** — Kinsta gives unlimited users and roles on every plan.

> ⚠️ **Conflicting evidence on teams, stated honestly:** Ploi gates team management to its
> €30 tier; the agency/hosting segment never gates it. The segments genuinely differ — do
> not average them into a wrong answer.

**Recommendation:** gate **agency and scale** features (white-label, client portal, client
billing, SSO, API volume). **Never gate safety** — backups, monitoring, security scanning
and incident response. Ploi's €8 plan ships without backups or monitoring, and that is
precisely the thing we can name in a comparison. Keeping safety open is a differentiator we
can *say out loud*, not merely a principle.

### 7.4 The AI-layer reality check

| Vendor | Charges | Per unit |
|---|---|---|
| **Hostinger Kodee** | **$0**, unmetered | — |
| **CtrlOps** | $7/user/mo, unlimited | — |
| **Cloudways Copilot** | $3.99–$80/mo | credit-metered |
| **Datadog Bits** | ~$6.50 | per autonomous investigation |
| **Cleric** | $20 | per Issue ($2,000/mo minimum) |
| **NeuBird** | $7.50–$15.00 | per investigation |
| **ServerAlly measured COGS** | **$0.096** | per action |

Two readings, both true and both important:

- **Our cost is not the catastrophe it looked like** — we spend roughly **1.5%** of what
  the market *charges* for comparable AI work. $0.096/action is a pricing-model problem, not
  a cost crisis.
- **But the price expectation is being set at zero** by Hostinger and at $7-unlimited by
  CtrlOps. We cannot charge enterprise AI-SRE prices to this buyer.

**Cloudways is the precedent that matters:** it sells AI credits successfully. That does
**not** refute [PRICING-V3](PRICING-V3.md) §3's ban on credits — the ban's real principle is
that *the metered unit must be user-intent-shaped, not vendor-decision-shaped*. A Cloudways
credit = one user-requested insight or fix. A token = our choice of model and step count.
**The rule stands; it just needs restating in terms of the principle rather than the word.**

---

## 8. What to build — and what to deliberately refuse

### 8.1 Do NOT become a control panel

Building Tier 1 in full means a mail stack, a nameserver, phpMyAdmin, FTP accounts and a
WordPress installer — **years of work, competing against five free products**, in a category
whose own users rate it NPS 28. We already sit *on top of* panels (CyberPanel CLI over SSH,
hosting adapters). The right frame is **"ServerAlly manages your servers *and* your
panels"**, never *"ServerAlly instead of your panel."*

**Refuse:** full email stack · authoritative nameserver (BIND/PowerDNS) · phpMyAdmin
clone · FTP account management · reseller/account hierarchy.

### 8.2 The ranked build list

> ⚠️ **REVISED 2026-07-25 — see [PRO-FEATURES-PLAN.md](PRO-FEATURES-PLAN.md) §1.** The owner
> confirmed ServerAlly is *not* a control-panel replacement. Two items below (**a sites
> model** and **PHP version management**) are panel features and are **dropped**; SSH-key and
> firewall managers are **deferred**. The three shipped items — offsite backups, uptime
> monitoring, log viewer — are operator features and stand. Pro-tier work now follows
> PRO-FEATURES-PLAN.md.

**Wave 1 — stop being disqualified.** These are the gaps a buyer notices in the first hour.

1. ~~**A real sites model for plain servers**~~ — **DROPPED**: a panel's job, not ours.
2. **Offsite backups** (S3/R2/B2/SFTP) — our single biggest functional gap, and a *safety*
   feature, so it must stay ungated.
3. **Uptime / HTTP monitoring + "site is down" alerts** — we currently cannot alert on the
   one thing every owner actually cares about.
4. ~~**PHP/Node version management per site**~~ — **DROPPED**: a panel's job, not ours.
5. **Server log viewer** (nginx/php-fpm/journald tail + search) — also the **#1 requested AI
   capability** in this market, and it makes Ally visibly better.
6. **SSH key manager + firewall rule manager** — **DEFERRED**: borderline panel territory;
   revisit only on customer demand.

**Wave 2 — compete on equal terms.**

7. Git deploy + auto-deploy webhook + **rollback** (zero-downtime after).
8. **DNS via Cloudflare integration** (this is exactly what Ploi and RunCloud do — not a
   nameserver).
9. Staging / clone site.
10. Queue workers / supervisor management.
11. Cloud lifecycle — create, reboot, resize, destroy (we import only).
12. Public API keys + CLI.

**Wave 3 — monetisable agency tier.**

13. White-label branding + client portal.
14. Client billing hooks (or WHMCS provisioning, which we partly have).
15. Status pages.

### 8.3 The positioning that survives contact with this market

> **"One place for every server you own — any provider, any OS, any panel — with an AI that
> doesn't just suggest, it does the job and proves it worked."**

Three defensible claims, all currently true and all unmarketed: **cross-provider fleet**
(Kodee, Rocket.net and every panel are locked to one host), **verification** (nobody checks
outcomes), and **security response** (the category ceiling is firewall + Fail2Ban).

---

## 9. Open decisions for the PM

1. **Server counts per tier.** Ours is below median at the same price. Fix before launch.
2. **Do we gate any safety feature?** Recommendation: **no** — it is a nameable differentiator.
3. **Teams: gate or not?** Evidence conflicts by segment (§7.3). Recommendation: don't gate
   basic teams; gate SSO/seat volume.
4. **The AI layer's price**, against a market where the biggest player gives it away free.
5. **Wave 1 order** — confirm the six, or re-rank.

---

## 10. Sources

Vendor pricing/feature pages were the primary source throughout. Full per-vendor reports
with complete citation lists are in the research working directory (Groups A–D + inventory).
Key primary sources:

[Ploi pricing](https://ploi.io/pricing) · [Ploi MCP](https://ploi.io/features/mcp) ·
[RunCloud pricing](https://runcloud.io/pricing) · [Forge pricing](https://laravel.com/forge/pricing) ·
[SpinupWP pricing](https://spinupwp.com/pricing/) · [ServerPilot pricing](https://serverpilot.io/pricing/) ·
[Cloudways AI Copilot](https://www.cloudways.com/en/cloudways-ai-copilot.php) ·
[Hostinger Kodee](https://www.hostinger.com/blog/kodee-vps-terminal) ·
[Hostinger Kodee MCP](https://www.hostinger.com/blog/vps-kodee-mcp) ·
[aaPanel AI + MCP](https://www.aapanel.com/new/feature/ai.html) ·
[cPanel built-in AI](https://www.cpanel.net/blog/products/the-next-evolution-of-cpanel-built-in-ai-for-faster-smarter-hosting-management/) ·
[Rocket.net MCP](https://rocket.net/blog/rocket-net-launches-a-new-developer-hub-with-full-mcp-integration/) ·
[Enhance pricing](https://enhance.com/pricing) · [GridPane pricing](https://gridpane.com/pricing/) ·
[Cleric pricing](https://cleric.ai/pricing) · [Doctor Droid pricing](https://drdroid.io/pricing) ·
[Datadog AI Credits](https://www.datadoghq.com/pricing/?product=ai-credits) ·
[servermind.dev repo](https://github.com/AjjlalAhmed/servermind)

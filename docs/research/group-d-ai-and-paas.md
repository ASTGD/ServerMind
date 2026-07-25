# Group D Competitor Research — AI-Native Server Tools & Self-Hosted PaaS

**Prepared for:** ServerAlly (AI-powered server management SaaS)
**Research date:** 2026-07-25
**Rule applied throughout:** every factual claim carries a source URL. Where a fact could not be confirmed from a primary source it is marked **UNVERIFIED** rather than guessed.

---

## 0. Executive summary — the seven things that matter

1. **The scariest competitor is not a startup — it is Hostinger.** Hostinger's **Kodee** is an AI assistant embedded in the VPS terminal and hPanel that reads logs, runs commands, applies fixes and deploys apps, wired to ~200 VPS actions over MCP. It is **included free** in a **$6.49/mo VPS**, with no published usage limits, and has reportedly **resolved 91% of 914,000 conversations autonomously**. ([Hostinger blog](https://www.hostinger.com/blog/kodee-vps-terminal), [MCP blog](https://www.hostinger.com/blog/vps-kodee-mcp), [hostingdiscussion](https://hostingdiscussion.com/news/hostingers-kodee-ai-now-fixes-vps-problems-directly/)) This is ServerAlly's exact value proposition, bundled at zero marginal price by a company with mass-market distribution.
2. **AI diagnose-and-repair IS being sold commercially today, and it is metered by CREDITS.** Cloudways (owned by DigitalOcean) sells **Copilot** with **SmartFix**: AI detects the issue, explains root cause, and on approval **executes the fix**. Pricing is **$3.99 / $9.99 / $19.99–$80.00 per month for 4 / 12 / 25–100 AI credits**. ([Cloudways](https://www.cloudways.com/en/cloudways-ai-copilot.php)) See §3 — the single most decision-relevant finding for ServerAlly's pricing.
3. **servermind.dev — the name-collision rival that triggered ServerAlly's rebrand — is effectively a non-competitor.** GitHub shows **4 stars, 0 forks, one release (v0.1.0), repo created 2026-06-13**. ([GitHub](https://github.com/AjjlalAhmed/servermind)) A solo MIT side project, not a funded rival.
4. **The direct AI-server-tool rivals price cheap and DON'T meter AI.** CtrlOps: **$7/user/month, unlimited servers, no AI limits**. Panelica: **$4.99–$24.99/month gated on domains**, Claude-Code-powered OpsAI included. Both undercut a metered model.
5. **In the self-hosted PaaS tier, three of six ship an official MCP server — but NOT ONE ships an AI agent.** Their AI story is uniformly *"here's an API so YOUR AI can drive us."* And **Portainer built an LLM chatbot and then deleted it** (§2.5) — then rebuilt it correctly as a separate product whose assistant *"fetches live diagnostic data before answering"* and *"avoids executing irreversible operations directly."* That is an independent re-derivation of ServerAlly's Live Look + approval gate by a funded competitor who failed with the naive version first.
6. **The enterprise "AI SRE" cohort repairs Kubernetes, not servers.** Every vendor's remediation vocabulary is scale/rollback/drain/revert — **not one** restarts MariaDB, quarantines a webshell or fixes `wp-content` permissions. **The single-server / hosting-panel repair problem is unclaimed.** Datadog — the player best positioned to do autonomous repair — **deliberately stopped at "open a PR for review."** (§4)
7. **A large price band is empty.** Hosting panels sit at **$8–49/mo**; AI SRE starts at **$99/mo** and centres on **$2,000+/mo** (Cleric = $24,000/yr). Nothing serious occupies the gap where ServerAlly's semi-technical agency/MSP buyer lives.

> **The cost number worth carrying into the pricing conversation:** ServerAlly measures **$0.096 per action**. Datadog charges **~$6.50 per autonomous investigation**; Cleric charges **$20 per Issue**. ServerAlly's per-action COGS is on the order of **1.5% of what the market charges** for comparable AI work. The $0.096 figure is a *pricing-model* problem, not a cost catastrophe.

---

# PART 1 — AI-NATIVE SERVER TOOLS (direct rivals)

## 1.1 servermind.dev — *the name collision, and a non-threat*

| | |
|---|---|
| **URL** | https://servermind.dev/ |
| **Repo** | https://github.com/AjjlalAhmed/servermind |
| **Tagline** | "Manage your server by talking to it" — "A self-hosted AI assistant for people who own the Linux box but never signed up to be its sysadmin." ([servermind.dev](https://servermind.dev/)) |
| **License / price** | **Free, open-source, MIT.** No account, no telemetry, no cloud backend. ([servermind.dev](https://servermind.dev/)) |

**Positioning + buyer.** Self-hosted, privacy-first, bring-your-own-AI. Targets indie devs, solo founders, agencies, startups without DevOps, homelabbers. ([servermind.dev](https://servermind.dev/))

**What the AI does — EXECUTES, but behind an explicit "arm" gate.** This is the most interesting design in the product. By default the assistant is **read-only**: it checks and explains. Any change (restart/stop/start) is **blocked until the user flips an "arm" switch on the server side, which auto-expires after use**. It **cannot** run raw shell commands, cannot delete or write, cannot do network operations, and cannot read restricted files such as `/etc/shadow`. Everything runs through a strict allowlist. ([servermind.dev](https://servermind.dev/))

**Features.** Chat control + live dashboard (CPU/memory/disk/uptime, PM2 processes, service health); multi-server fleet via one controller + lightweight agents; user-defined custom tools (frozen commands, read-only DB queries, parameterised commands); email alerts and daily health reports; password + TOTP 2FA, HttpOnly sessions, brute-force lockout, strict CSP. Covers PM2, Redis, MySQL/MariaDB, Nginx, Caddy, systemd, Docker, fail2ban, Postfix, DNS. Desktop app for macOS + Windows reached over **a single outbound SSH tunnel — no domain, proxy or certificates required**. ([servermind.dev](https://servermind.dev/))

**AI providers (BYO key).** Google Gemini free tier (~1,500 req/day, default), Claude subscription, any OpenAI-compatible API (xAI Grok, Groq, OpenRouter, DeepSeek), or local Ollama. Install is `curl -fsSL https://servermind.dev/install.sh | bash`; binds to localhost, opens no inbound ports. ([servermind.dev](https://servermind.dev/))

**Maturity — very low.** GitHub API, fetched 2026-07-25:

| Metric | Value |
|---|---|
| Stars | **4** |
| Forks | **0** |
| Watchers | 0 |
| Open issues | 2 |
| Created | **2026-06-13** |
| Last push | 2026-07-05 |
| Releases | **v0.1.0 only** (2026-06-21), 11 asset downloads total |
| License | MIT |
| Language | TypeScript |

Author: **Ajjlal Ahmed** (© 2026), a single individual. ([servermind.dev](https://servermind.dev/), [GitHub API](https://api.github.com/repos/AjjlalAhmed/servermind))

**Verdict.** Six weeks old, 4 stars, one pre-1.0 release, one developer. The rebrand away from "ServerMind" was still correct on trademark/SEO grounds, but this project is **not** a commercial threat.

**Worth stealing:** the **auto-expiring "arm" switch**. ServerAlly's model is per-step approval; an explicitly armed, time-limited write window is a cleaner mental model for non-technical users ("Ally is allowed to change things for the next 10 minutes") and is a genuinely good safety UX. Also the **single outbound SSH tunnel desktop app** — no domain, no certs, no inbound ports — is a very low-friction onboarding story.

---

## 1.2 Panelica OpsAI — *Claude-powered AI inside a cPanel replacement*

| | |
|---|---|
| **URL** | https://panelica.com/ · https://panelica.com/opsai |
| **Tagline (OpsAI)** | **"15 AI Experts. One Panel. Zero Complexity"** ([panelica.com/opsai](https://panelica.com/opsai)) |
| **Positioning** | A modern cPanel/WHM and Plesk replacement with 5-layer isolation, Docker, and a built-in AI assistant. ([panelica.com](https://panelica.com/)) |

**The pitch, verbatim:** *"OpsAI isn't a chatbot. It's 15 specialized DevOps experts that understand your server, execute multi-step operations, and handle real infrastructure tasks through natural language."* ([panelica.com/opsai](https://panelica.com/opsai))

**What the AI does — EXECUTES.** The marketing is explicit that this is execution, not advice: *"OpsAI gives you experts that understand context and execute"* and it handles *"real infrastructure tasks."* Worked examples include provisioning domains, configuring DNS, installing SSL, and *"Creates Docker Compose stack with 5 services and network isolation."* It operates **through the same RBAC-aware panel API a human admin would**, and is **trained on the panel's 1,263 API endpoints**. ([panelica.com/opsai](https://panelica.com/opsai))

**The 15 specialists.** General (orchestration/routing), Domain, Security, System, Database, Backup, Files, Email, WordPress, Docker, Cloudflare, Git, FTP, SSH, Cron. ([panelica.com/opsai](https://panelica.com/opsai))

**Model + key ownership — CONFLICTING SOURCES, treat as PARTIALLY VERIFIED.**
- The homepage lists OpsAI's core as **"Claude Code · 15 specialist experts · 1,263 endpoints"**, describes it as *"powered by Claude Code"*, and states it *"runs locally from the binary, no external runtime, no data leaving the server."* A direct fetch of the homepage found **no statement that the customer must supply an Anthropic API key**, and the comparison table marks OpsAI as **"✓ included."** ([panelica.com](https://panelica.com/))
- However, a search-engine extract of Panelica's own pages stated: *"OpsAI is powered by Claude Code (Anthropic), and a Claude Code API key is required to use this feature."* This could not be reproduced on direct fetch of either the homepage or the OpsAI page.
- **Conclusion: OpsAI is Claude-Code-powered and marketed as included in the panel; whether the customer must bring an Anthropic key is UNVERIFIED and contradictory between sources.** Worth a manual check — it materially affects whether Panelica has solved the AI-COGS problem the same way ServerAlly's Pricing v3 Layer 2(a) does.

**Safety / approval gates — UNVERIFIED.** Neither the OpsAI page nor the features page documents any approval workflow, dry-run, change review, or rollback. There is an **RBAC-aware sandbox demo mode** for safe exploration. ([panelica.com/opsai](https://panelica.com/opsai)) Given ServerAlly's heavy investment in approval gates, verification gates and injection defence, this looks like a genuine differentiator — but absence of documentation is not proof of absence.

**EXACT pricing** (panelica.com/pricing, fetched 2026-07-25). **Gated on DOMAINS + feature count — not servers, not AI usage:**

| Tier | Monthly | Yearly | Domains | Features |
|---|---|---|---|---|
| **Starter** | **$0** — free forever, no credit card | — | **3** | Limited |
| **Professional** | **$4.99** | $49.70/yr (saves $10) | **15** | 34 of 41 (83%) |
| **Business** | **$9.99** | $99.50/yr (saves $20) | **50** | 37 of 41 (90%) |
| **Enterprise** | **$24.99** | $248.90/yr (saves $51) | **Unlimited** | All 41 (100%) |

Databases, email accounts and FTP users are **unlimited on all paid plans**; all tiers include the full security stack, WordPress toolkit and one-click migration. 30-day money-back guarantee. **No AI credits, AI quota or AI usage limit is published anywhere.** ([panelica.com/pricing](https://panelica.com/pricing))

> Note: the homepage separately advertises a tier called **"Star — Free forever for personal use — Full features"**, which conflicts with the pricing page's "Starter — free — 3 domains — limited features." ([panelica.com](https://panelica.com/) vs [panelica.com/pricing](https://panelica.com/pricing)) Treat the free tier's exact scope as **UNVERIFIED**.

**Feature surface (40+ modules across 11 categories).** Server management (11), Security (9: ModSecurity WAF, nftables, ClamAV, Fail2ban, 5-layer isolation, 2FA, IP blocking, audit logging, RBAC), WordPress toolkit (11), Docker manager (11, incl. **170+ templates**), Migration (6, incl. password-hash preservation and **automatic rollback**), Backup/restore (8), Developer tools (6: REST API, Git auto-deploy, webhooks, CLI, API keys), Cloudflare (5), Email (6), Databases (5), UX (6: **31 languages**, remote desktop, global search). ([panelica.com/features](https://panelica.com/features))

**Maturity — opaque.** No launch date, version number, customer count, team size or company location is disclosed on the homepage, features page or pricing page. Copyright reads "© 2026 Panelica, LLC". A live demo exists at https://demo.panelica.com/ and a YouTube channel at https://www.youtube.com/@panelica. ([panelica.com/features](https://panelica.com/features)) **Funding: UNVERIFIED / none found.**

**Worth stealing:**
- **"15 specialist experts" as packaging.** Functionally this is what ServerAlly's *skills* already are (9 packaged expert procedures), but Panelica sells them as a **visible roster of named specialists**, which is far more legible to a buyer than an invisible routing layer. ServerAlly has the better engineering and the worse merchandising here.
- **"Trained on 1,263 panel API endpoints"** — a concrete, checkable number used as a trust signal.
- **RBAC-aware sandbox demo mode** — lets a prospect watch the AI work without owning a server. ServerAlly has no try-before-you-connect path.

---

## 1.3 Hostinger Kodee — *the mass-market threat*

| | |
|---|---|
| **URL** | https://www.hostinger.com/blog/kodee-vps-terminal |
| **Positioning** | AI assistant built into the VPS terminal and hPanel of a mass-market hosting company. TechRadar headline: *"Meet VPS Kodee: your new AI sysadmin."* ([TechRadar](https://www.techradar.com/pro/meet-vps-kodee-your-new-ai-sysadmin)) |

**What the AI does — EXECUTES, including fixes.** Hostinger's own description: Kodee can *"read logs and configs, troubleshoot issues, run commands, apply fixes, deploy applications, and improve security."* It operates **inside the terminal** rather than suggesting commands to copy-paste: *"A task that would normally require terminal skills became as simple as a chat."* ([Hostinger blog](https://www.hostinger.com/blog/kodee-vps-terminal))

**MCP integration — ~200 VPS actions.** In April 2025 Hostinger connected Kodee to servers via **Model Context Protocol**, unlocking roughly **200 VPS management actions**: hostname changes, firewall management, snapshots, password resets, SSH access control, malware scanner enablement, resource monitoring, control-panel management. ([Hostinger MCP blog](https://www.hostinger.com/blog/vps-kodee-mcp))

**Safety.** **Destructive actions require explicit user confirmation** — VPS reinstallation, OS template changes, backup restoration. ([Hostinger MCP blog](https://www.hostinger.com/blog/vps-kodee-mcp)) Beyond that, no approval workflow, guardrail or rollback detail is published. ([Hostinger blog](https://www.hostinger.com/blog/kodee-vps-terminal))

**Pricing and limits — the critical part.** Kodee is *"already integrated into your VPS experience – available 24/7 and **included for free**"* and *"requires **no separate subscription**, manual installation, or complex permission setup."* It is included on **all VPS tiers**, with **no published rate limits, conversation caps or usage quotas**. ([Hostinger VPS](https://www.hostinger.com/vps-hosting), [Hostinger blog](https://www.hostinger.com/blog/kodee-vps-terminal)) The underlying **AI model/provider is not disclosed**. ([Hostinger blog](https://www.hostinger.com/blog/kodee-vps-terminal), [Hostinger MCP blog](https://www.hostinger.com/blog/vps-kodee-mcp))

**The price it is bundled against** ([hostinger.com/vps-hosting](https://www.hostinger.com/vps-hosting), fetched 2026-07-25):

| Plan | Promotional | Renewal (2-year term) |
|---|---|---|
| KVM 1 | **$6.49/mo** | $11.99/mo |
| KVM 2 (most popular) | **$8.79/mo** | $14.99/mo |
| KVM 4 | **$12.99/mo** | $28.99/mo |
| KVM 8 | **$25.99/mo** | $49.99/mo |

So the real competitive statement is: **an unmetered AI sysadmin that executes fixes, bundled into a $6.49/month VPS.** ServerAlly cannot win a price argument against that; it has to win a *scope* argument (see below).

**Maturity — and the scale number that should worry ServerAlly most.** Kodee (the broader product) launched **2024**; the terminal-integrated version launched **early 2026** (article dated 2026-05-11); MCP integration **April 2025**. Third-party coverage confirms the fixes capability: *"Hostinger's Kodee AI now fixes VPS problems directly."* ([hostingdiscussion.com](https://hostingdiscussion.com/news/hostingers-kodee-ai-now-fixes-vps-problems-directly/))

That same report gives the traction figure: **Kodee resolved 91% of cases autonomously across 914,000 conversations**, with only 7% needing a human agent. It can *"create firewall rules or rotate SSH keys"* and *"run commands and deploy applications directly."* It deliberately hands off *"account suspensions, active DDoS attacks, anything involving billing policy or a customer who specifically wants to talk to a person."* ([hostingdiscussion.com](https://hostingdiscussion.com/news/hostingers-kodee-ai-now-fixes-vps-problems-directly/))

**914,000 conversations at 91% autonomous resolution is, by a wide margin, the largest proven deployment of AI server management found in this entire research.** Note the number is vendor-reported and includes general hosting support conversations, not only VPS terminal sessions — treat the 91% as a support-deflection metric rather than a pure sysadmin-task metric. Exact Hostinger VPS pricing: **UNVERIFIED** (not fetched) — but the line is entry-level priced, so the practical comparison is *"free AI sysadmin bundled with a cheap VPS."*

**Strategic read for ServerAlly.** This is the most dangerous competitor found in Group D, for three reasons:
1. **Same buyer, same promise.** "Manage your VPS without being a sysadmin" is verbatim ServerAlly's positioning.
2. **Zero marginal price.** Bundled free. ServerAlly cannot win a price fight against a loss-leader whose purpose is to retain hosting revenue.
3. **Distribution.** Hostinger already owns the non-technical VPS customer at signup.

**But it has a hard structural limit worth attacking:** Kodee only works on **Hostinger's own servers**. ServerAlly is provider-agnostic — it manages any Linux/Windows box, any cloud, any panel, and a *fleet* across providers. Agencies and MSPs with servers at 5 different hosts cannot use Kodee. **The counter-positioning writes itself: "Your host's AI only manages your host's servers. Ally manages all of them."**

**Worth stealing:** MCP as the execution substrate for ~200 bounded actions is exactly the architecture ServerAlly shipped in 2026-07-23. Hostinger validating that approach at mass-market scale is a strong signal ServerAlly's MCP bet is correct.

---

## 1.4 CtrlOps — *closest analogue, and a pricing warning*

| | |
|---|---|
| **URL** | https://ctrlops.io/ |
| **Tagline** | **"Deploy, Debug, Manage Linux servers with AI"** ([ctrlops.io](https://ctrlops.io/)) |
| **Architecture** | Local-first **desktop app** built with **Tauri + Rust**; multi-server, no cloud dependency. ([ctrlops.io](https://ctrlops.io/)) |

**Positioning + buyer.** Developers, DevOps engineers, solo founders, **and explicitly non-technical users (designers, product managers)** managing Linux infrastructure across AWS, GCP, Azure or any VPS. ([ctrlops.io](https://ctrlops.io/)) This is a near-exact overlap with ServerAlly's stated buyer.

**What the AI does — ADVISES, with a mandatory approval gate.** The model is *"AI suggests, you approve"*: the AI terminal turns natural language into commands, **displays the exact command, and requires human review before execution**. Strictly advisory + gated — notably **less autonomous than ServerAlly's missions**. ([ctrlops.io](https://ctrlops.io/))

**Features.** AI Terminal (NL→bash with approval gate); visual file manager (upload/download/unzip/edit); multi-server fleet view with aliasing; real-time monitoring (CPU/memory/disk/network); **single-click GitHub deployments** (handles PM2, Nginx, SSL); SSH access management/audit; automated backups; saved scripts/playbooks; **MCP server integration**; web search integration. ([ctrlops.io](https://ctrlops.io/))

**EXACT pricing — per USER, unlimited servers, AI not metered** (ctrlops.io/pricing, fetched 2026-07-25):

| Plan | Price | Notes |
|---|---|---|
| **Free trial** | **$0 for 1 month** | All Pro features, **no credit card**, no auto-charge |
| **Monthly** | **$7 / user / month** | Cancel anytime, all features |
| **Yearly** | **$70 / user / year** (≈$5.83/mo) | 20% off, priority support, early access |
| **Lifetime** | **$149 / user, one-time** | 1 year premium support + updates, unlimited device activations |

Their explicit anti-gating stance: *"We don't gate basics behind upgrades. Unlimited servers, the AI terminal, fleet monitoring, and one-click deployments ship in every plan."* **No AI request limits, no credits, and no BYO-API-key option are mentioned.** There is **no permanent free tier** — only the 1-month trial. ([ctrlops.io/pricing](https://ctrlops.io/pricing))

**Maturity.** Version **1.1.0**. Co-founders **Daxesh Italiya, Hiren Kalariya, Parth Makwana**, formerly of TST Technology (an IT services firm). Product Hunt daily-ranking badge and G2 reviews present on site. ([ctrlops.io](https://ctrlops.io/)) **Funding: UNVERIFIED / none found. Exact PH rank, G2 score and review count: UNVERIFIED.**

**Strategic read.** CtrlOps is the most direct structural analogue to ServerAlly found. Two implications:
1. **Their pricing is a direct threat to ServerAlly's Pricing v3.** $7/user/month with **unlimited servers and unmetered AI** is the opposite of a per-server + AI-allowance model. ServerAlly's Layer-1-per-server pricing must beat this on value, because it will lose on sticker simplicity. Note however that CtrlOps is a **local desktop app** — the customer's own machine does the work, so their AI-COGS story is likely BYO or thin; a hosted SaaS cannot copy $7/user/unlimited safely. **Verify their AI cost model before reacting to their price.**
2. **Their AI is weaker.** "AI suggests, you approve" is one-shot command generation. ServerAlly's missions (plan→run→observe→repeat, verification gate, resumable, detached) are a genuinely deeper capability. **The gap to sell is autonomy-with-safety, not chat.**

**Worth stealing:** the **Lifetime $149 tier** — unusual for infra SaaS, excellent for early cash and for the self-hosted/licensed edition ServerAlly has already scoped. Also the explicit **"we don't gate basics"** copy, which converts a pricing page into a trust statement.

---

## 1.5 Chaterm — *the credible open-source rival (3,036 stars)*

| | |
|---|---|
| **Repo** | https://github.com/chaterm/Chaterm |
| **Tagline** | "Open source AI terminal for cloud and infrastructure management, enabling you to deploy, troubleshoot, and automate services using natural language and intelligent agents." ([GitHub](https://github.com/chaterm/Chaterm)) |

**What the AI does — AUTONOMOUS EXECUTION across multiple hosts.** It *"autonomously plan[s] and execute[s] complex operations across multiple hosts or clusters."* Safety is **post-hoc rather than preventive**: *"Every operation is auditable and traceable, and supports rapid log rollback, making AI automation more secure and reliable."* ([GitHub](https://github.com/chaterm/Chaterm))

**Features.** Multi-host autonomous problem analysis and execution; smart command completion using context + user habits; knowledge-base integration (manuals, docs, scripts); **reusable "agent skills"** for structured automation (directly comparable to ServerAlly's skills); plugin system for auth and resource access; database workspace (MySQL, PostgreSQL, SQLite, Oracle). Desktop apps for **macOS, Windows, Linux, iOS and Android**. ([GitHub](https://github.com/chaterm/Chaterm))

**Maturity — the strongest OSS traction in this category** (GitHub API, fetched 2026-07-25):

| Metric | Value |
|---|---|
| Stars | **3,036** |
| Forks | **288** |
| Created | 2025-04-14 |
| Last push | **2026-07-23** (actively developed) |
| Language | TypeScript |
| License | NOASSERTION (non-standard — verify before assuming permissive) |

Models: "Qwen Large Models" is referenced in connection with agent skills; a full supported-model list is **UNVERIFIED**. Company/backer: **UNVERIFIED** (appears community-driven; the Qwen association and mobile-first breadth hint at a China-based sponsor, but this is **not confirmed**). Paid/cloud/enterprise tier: **none found — UNVERIFIED**. ([GitHub](https://github.com/chaterm/Chaterm))

**Worth stealing:** **iOS and Android apps.** ServerAlly's backlog lists a mobile app as unbuilt; Chaterm already ships one. "Fix my server from my phone" is a strong emotional hook for the on-call moment, and it is the single feature most likely to be demoed in a review.

---

## 1.6 Other AI server assistants found (swept, lower priority)

**Open-source, verified star counts** (GitHub API, fetched 2026-07-25):

| Project | Stars | Forks | Created | Last push | What it is |
|---|---|---|---|---|---|
| [bytebot-ai/bytebot](https://github.com/bytebot-ai/bytebot) | **11,070** | 1,485 | 2025-02-03 | 2025-09-12 | Self-hosted AI **desktop** agent in a containerised Linux desktop — adjacent, not server management. Note: **no push since 2025-09**. |
| [chaterm/Chaterm](https://github.com/chaterm/chaterm) | **3,036** | 288 | 2025-04-14 | 2026-07-23 | See §1.5 — the real OSS rival. |
| [veithly/vibeshell](https://github.com/veithly/vibeshell) | **59** | 9 | 2026-02-13 | 2026-07-11 | *"The first SSH client built for AI agents"* — lets Claude Code/Codex manage servers via **MCP skills**. Rust. Same architectural bet as ServerAlly's MCP connector. |
| [noxgle/term_agent](https://github.com/noxgle/term_agent) | **5** | 1 | 2025-05-14 | 2026-05-26 | Linux terminal agent, multi-provider (Ollama/ChatGPT/OpenRouter/Groq/Gemini). MIT. |
| [jamro/term-800](https://github.com/jamro/term-800) | **3** | 0 | 2025-02-23 | 2025-03-02 | AI sysadmin chatbot over SSH. **Abandoned** (no push since 2025-03). |
| [AjjlalAhmed/servermind](https://github.com/AjjlalAhmed/servermind) | **4** | 0 | 2026-06-13 | 2026-07-05 | See §1.1. |

**Also noted:**
- **Netcatty** — open-source SSH client with a built-in AI agent doing natural-language command execution, service diagnosis and multi-host task orchestration. ([en.xiaoz.org](https://en.xiaoz.org/post/22874)) Stars **UNVERIFIED**.
- **Cloudways Copilot** — see §3; the most commercially significant AI-repair product found.
- **machine0** (YC ecosystem) — spin up VMs with dedicated CPU/RAM/GPU via natural-language commands, pre-installed with Node/Python/Docker and agents like Claude Code. Provisioning-focused, not management. Details **UNVERIFIED** beyond a YC directory listing. ([YC infrastructure companies](https://www.ycombinator.com/companies/industry/infrastructure))
- A curated list of **474 AI DevOps tools** exists at [hammadhaqqani/awesome-devops-ai](https://github.com/hammadhaqqani/awesome-devops-ai) (updated July 2026) — the best single directory for ongoing monitoring of this space.

**Category note:** searches for "AI sysadmin"/"AI DevOps assistant" return overwhelmingly **SEO listicle spam** and **enterprise observability** vendors (Dynatrace Davis, Datadog Bits AI, Energent.ai). Those are a different buyer (enterprise SRE teams with existing observability stacks) and a different price point. They are covered in §3 only insofar as they answer the diagnose-and-repair question.

---

# PART 2 — SELF-HOSTED PaaS / DEPLOYMENT PLATFORMS

> Full working notes with every source URL: [`part2-paas-raw.md`](./part2-paas-raw.md). All figures fetched **2026-07-25** via the GitHub API and vendor pricing pages.

## 2.0 The headline: three of six ship an official MCP server. **Not one ships an AI agent.**

Every AI feature found in this entire category is one of three shapes:
1. **An API for someone else's AI** (MCP) — Coolify, Dokploy, Portainer
2. **A single-shot generator** — Dokploy: describe → Docker Compose file
3. **A single-shot summarizer** — Dokploy: read logs → explain the error

**None has:** multi-step autonomous execution, safety validation of AI-proposed commands, verification that a claimed fix actually worked, incident narratives, long-term memory, or proactive monitoring. ServerAlly's mission engine + verification gate + skills is **unmatched in this set**.

## 2.1 Traction — exact GitHub numbers (GitHub API, 2026-07-25)

| Repo | Stars | Forks | Open issues | Contributors | Created | Last push | Latest release | License |
|---|---:|---:|---:|---:|---|---|---|---|
| [coollabsio/coolify](https://github.com/coollabsio/coolify) | **59,468** | 5,134 | 808 | 414 | 2021-01-25 | 2026-07-24 | v4.1.2 (2026-06-04) | Apache-2.0 |
| [portainer/portainer](https://github.com/portainer/portainer) | **38,040** | 2,870 | 740 | 230 | 2016-05-19 | 2026-07-24 | 2.39.5 LTS (2026-07-13) | zlib |
| [Dokploy/dokploy](https://github.com/Dokploy/dokploy) | **36,076** | 2,789 | 734 | 328 | **2024-04-19** | 2026-07-22 | v0.29.13 (2026-07-21) | Apache-2.0 + `/proprietary` carve-out |
| [dokku/dokku](https://github.com/dokku/dokku) | **32,055** | 2,063 | **25** | 407 | **2013-06-08** | 2026-07-24 | v0.38.25 (2026-07-22) | MIT |
| [caprover/caprover](https://github.com/caprover/caprover) | **15,106** | 984 | 175 | **70** | 2017-10-25 | 2026-07-24 | v1.14.2 (2026-05-14) | Apache-2.0 |
| **Easypanel** | **closed source — no public repo** ([404](https://api.github.com/repos/easypanel-io/easypanel)) | — | — | — | — | — | — | proprietary |

**Funding: Portainer is the only VC-backed one** — **$6M Series A, 2021-05-04, led by Bessemer Venture Partners** ([Portainer blog](https://www.portainer.io/blog/container-management-solution-portainer-io-raises-6m-series-a-round-to-accelerate-global-expansion), [FinSMEs](https://www.finsmes.com/2021/05/portainer-io-raises-6m-in-series-a-funding.html)); **$7.2M total across 3 rounds** per [Tracxn](https://tracxn.com/d/companies/portainer/__nUeaIlp1s8fLqur6S6tk1G5eaXTnJS2JgP0sr5qvmbc/funding-and-investors).

**A sobering economics data point:** Coolify — the 59k-star category leader — is unfunded, and its founder publicly posted **February 2026 gross income of $15,700/month** (Cloud ~$10.5k + donations ~$5.2k), net ~$12,900. ([@heyandras](https://x.com/heyandras/status/1901894087604916396)) Open-source PaaS is a hard business even at the top of the category.

## 2.2 EXACT pricing — the whole category in one table (2026-07-25)

| Product | Free tier | Entry paid | Mid | Top | **Gates on** |
|---|---|---|---|---|---|
| **Coolify** | Self-hosted, unlimited, *"no limitation or restrictions"* | **$5/mo** (2 servers) | **+$3/mo per extra server** | — | **servers** |
| **Dokploy** | Self-hosted — **deliberately not shown on the pricing page** | **$4.50/mo per server** | **$15/mo** (3 servers) | Custom | **servers × users × orgs × environments × jobs** |
| **Easypanel** | **$0** — up to **3 projects** | **$10.90/mo** | **$16.90/mo** | **$29.90/mo** | **projects → backups → users → white-label**, plus per-server license |
| **Dokku** | OSS, unlimited (MIT) | **$849 one-time, lifetime** | — | — | servers (1 prod + 2 pre-prod) |
| **CapRover** | **Free forever** | **no paid tier at all** | — | — | — |
| **Portainer** | **3 nodes with ALL Business features** | **$105/mo** or $1,045/yr | **$209/mo** or $2,095/yr | Custom | **nodes × vCPU-per-node × company annual revenue** |

Sources: [coolify.io/pricing](https://coolify.io/pricing), [dokploy.com/pricing](https://dokploy.com/pricing), [easypanel.io/pricing](https://easypanel.io/pricing), [pro.dokku.com](https://pro.dokku.com/), [caprover.com](https://caprover.com/), [portainer.io/pricing](https://www.portainer.io/pricing).

**Category price anchor: $4.50–$16.90/month.** Portainer at $105+/mo is a different market (enterprise IT/OT, node-licensed, with **revenue ceilings**: Starter *"limited to organizations with ≤ $50 million in annual revenue"*, Scale ≤ $100M).

## 2.3 AI feature matrix

| Product | In-product AI assistant | AI troubleshooting | Official MCP | MCP mode | BYO-key | AI safety layer |
|---|---|---|---|---|---|---|
| **Dokploy** | Yes — NL → Docker Compose | **Yes** — log + build-error analysis | **Yes — 508 tools / 49 categories** | Read+write, **auto-generated from OpenAPI** | **Yes, required** | **None** |
| **Coolify** | No | No | **Yes — built-in, v4.1.0 (2026-05-18)** | **Read-only**, Streamable HTTP, team-scoped | n/a | Read-only *is* the safety layer |
| **Portainer** | **REMOVED from core (2.32.0)**; present in new Portainer-Run (6★) | Portainer-Run fetches live diagnostics | Yes — portainer-mcp (**203★**) + Portainer-Run `/mcp` (**6 curated tools**) | Read-only mode available; *"NOT recommended to expose on the public internet"* | Yes (Anthropic/OpenAI) | Portainer-Run: *"avoids executing irreversible operations directly"* |
| **Dokku** | **No** | No | No — community only (6★) | — | — | — |
| **CapRover** | **No** | No | No — community only (3★, stale since 2025-06) | — | — | — |
| **Easypanel** | **No** | No | No — community only (4★) | — | — | — |

## 2.4 Per-product notes

**Coolify** — *"Self-hosting with superpowers."* ([coolify.io](https://coolify.io/)) 334 one-click templates counted directly from the shipped manifest (marketing says "280+"). Cloud is a **hosted control plane only** — you still bring your own servers, so Coolify carries almost no infra cost. *That is structurally the same model as ServerAlly and validates it.* Claims **"3,641+ customers in the cloud"**. MCP is **read-only**, *"with write operations planned for a future release"*, scoped to the API token's team. ([coolify.io/docs/integrations/mcp](https://coolify.io/docs/integrations/mcp)) Notably, a **community** MCP server ([StuMason/coolify-mcp](https://github.com/StuMason/coolify-mcp), **521★**) is more popular than the official one and offers writes.

**Dokploy** — *"Simplify Application and Database Deployments."* ([dokploy.com](https://dokploy.com/)) **The most AI-forward competitor by a wide margin**, all shipped in **v0.29.0 (2026-04-17)**: AI log/build-error debugging, NL→Compose generation, an official MCP server (**508 tools**) and CLI (**449 commands**), both auto-generated from their OpenAPI spec. Strictly BYO-key: *"**Dokploy does not include its own AI model.** You need to connect an external provider (like OpenAI, Anthropic, or any OpenAI-compatible API) with your own API key."* ([docs.dokploy.com/docs/core/ai](https://docs.dokploy.com/docs/core/ai), [v0.29.0 blog](https://dokploy.com/blog/v0-29-0-ai-powered-debugging-mcp-server-cli-shared-git-providers)) **500 templates** (exact, counted via git-tree API). **36k stars in 26 months — the fastest growth in the category**, and their LICENSE already reserves a `/proprietary` directory for paid features.

**Portainer** — *"Operational control for Kubernetes and Docker; without the specialist overhead."* ([portainer.io](https://www.portainer.io/)) Not a PaaS — a container/K8s management UI sold to **enterprise IT and industrial/OT** buyers. See §2.5 for the AI story, which is the most valuable finding in Part 2.

**Dokku** — *"The smallest PaaS implementation you've ever seen."* ([dokku.com](https://dokku.com/)) The original git-push PaaS, 13 years old, **25 open issues** (ruthless scope discipline). **Zero official AI, deliberately.** Dokku Pro is **$849 one-time for life with "free upgrades forever"** — essentially "Dokku gets a web UI" (JSON API, HTTPS git push, datastore management, env-var UI, scaling UI, log tailing, team management, email support). ([pro.dokku.com](https://pro.dokku.com/))

**CapRover** — *"Scalable, free, and self-hosted PaaS."* ([caprover.com](https://caprover.com/)) **353 one-click apps** (counted exactly). **Free forever, no paid tier, no revenue model at all.** The laggard: 15k stars (smallest), only **70 contributors** (4–6× fewer than everyone else), copyright line stops at 2024. Lowest-priority competitor.

**Easypanel** — *"Next Generation Server Control Panel."* ([easypanel.io](https://easypanel.io/)) **The closest positional competitor of the six** — it targets the cPanel/Plesk install base rather than Heroku, and its stated buyer is *"developers, system administrators, and full-stack engineers who need to deploy applications and manage server infrastructure **without extensive DevOps expertise**"* — the nearest thing to ServerAlly's "without the expertise" framing. Closed source with **no public repo**, so all traction is **UNVERIFIED** — which is also why it has no community MCP momentum.

## 2.5 ⭐ The most valuable finding in Part 2: **Portainer built an AI chatbot, then deleted it**

> **2.33.0 LTS (2025-08-20):** *"The OpenAI integration experimental feature is deprecated in this release and will be removed in 2.33 LTS."*
> **2.32.0 STS (2025-07-24):** *"The OpenAI integration experimental feature has been removed in this release."*
> — [docs.portainer.io/release-notes](https://docs.portainer.io/release-notes)

A VC-funded ($7.2M), 38k-star, 10-year-old container-management company shipped an LLM chat assistant (Business Edition 2.18.3) and **pulled it after roughly two years**.

**Two readings, and both matter:**
- **Bear case:** a bolted-on chatbot over an infrastructure API adds little real value. If ServerAlly is "a chat box on top of SSH," this is the outcome.
- **Bull case — and this is what the evidence actually supports:** Portainer built the **shallow** version (an OpenAI wrapper on a UI). ServerAlly built the **deep** version — skills, missions, the verification gate, injection defence, Live Look, safety blocklists, memory, incident reports. **Portainer's failure is evidence that the shallow version doesn't work, which is precisely the argument for the deep one.**

**Portainer's own second attempt proves it.** They rebuilt AI as a separate product, **Portainer-Run** (*"The enterprise landing pad for apps your business teams build with AI"*, [portainer.ai](https://portainer.ai/)), whose assistant is described as *"**context-aware and fetches live diagnostic data before answering** health questions"* and *"**avoids executing irreversible operations directly**."* ([github.com/portainer/portainer-run](https://github.com/portainer/portainer-run))

That is an **independent re-derivation of ServerAlly's Live Look + approval gate** by a funded competitor who had already failed once with the naive version. It is the strongest external validation of ServerAlly's architecture found anywhere in this research. Portainer-Run is very new and tiny (repo created 2026-03-31, **6 stars**), targets *"finance leads, ops managers, analysts, and designers"*, and exposes a deliberately curated **6-tool** MCP endpoint — the opposite of Dokploy's 508.

## 2.6 What Part 2 means for ServerAlly

1. **MCP is table stakes, not a differentiator — but ServerAlly's is architecturally ahead.** Coolify is read-only; Portainer is explicitly local-only (*"NOT recommended to expose on the public internet"*); Dokploy is 508 uncurated auto-generated tools. **Nobody else has an OAuth 2.1 AS.** That is the moat inside the MCP lane and it should be said out loud in marketing.
2. **Pricing-v3's Layer 2(a) "bring your own AI" is Dokploy's shipped feature today.** BYO-key is not a moat on its own. The mission engine + verification gate + skills is what is genuinely unmatched.
3. **Two concrete pricing holes.** (a) Portainer caps **vCPUs per node** alongside node count — ServerAlly's per-server pricing has exactly that hole, and panel2 (90 sites on one box) is the abuse shape. Consider a second dimension before per-server pricing hardens. (b) The market puts **backups behind the first paid tier** (Easypanel); ServerAlly deliberately does not (Pricing v2: "never gate safety features") — **market that choice out loud instead of absorbing it quietly.**
4. **Dokploy is the competitor to watch** — 36k stars in 26 months, BYO-key AI shipped, and a `/proprietary` licence carve-out already in place for paid AI features.
5. **Worth stealing:** Coolify's **"Founder-tested"** stability-as-a-paid-feature; Portainer's **revenue-based tier ceilings** (margin capture as a contract term, zero engineering); Portainer's **free tier = all features on 3 nodes**; Easypanel's **project-based free tier** (feel the whole product on 3 projects); Dokku's **$849 lifetime** (a real option for ServerAlly's already-scoped self-hosted edition); and the **separate community template repo** pattern (CapRover 639★ / Coolify 334 templates / Dokploy 500) — turn the playbook library into its own community asset.

---

# PART 3 — THE SPECIFIC QUESTION: is anyone commercially doing AI *diagnose and repair*?

> **Short answer: YES — and the most important example is Cloudways Copilot, owned by DigitalOcean. It detects the problem, explains root cause, and on your approval executes the fix. It is sold at $3.99 / $9.99 / $19.99–$80.00 per month, and — critically — it is metered in AI CREDITS.**

This matters disproportionately to ServerAlly because [PRICING-V3](../../../docs/PRICING-V3.md) makes credits a **hard forbidden rule**. The largest player in the adjacent market has gone the other way. That does not make the rule wrong, but it means the rule now needs a defence, not just an assertion.

## 3.1 Cloudways Copilot + SmartFix — the direct precedent

| | |
|---|---|
| **Vendor** | Cloudways (**owned by DigitalOcean**) |
| **URL** | https://www.cloudways.com/en/cloudways-ai-copilot.php |
| **Tagline** | **"Managed Hosting, Now More Intelligent"** |
| **GA date** | **12 August 2025**, phased rollout to existing users through 30 September 2025 ([announcement](https://www.cloudways.com/blog/announcing-ai-copilot-general-availability/)) |

**What it does.** 24/7 monitoring that **detects** server and application issues, **diagnoses** root cause via AI, and delivers actionable recommendations by email and dashboard notification. ([Cloudways Copilot](https://www.cloudways.com/en/cloudways-ai-copilot.php))

**Does it REPAIR? Yes — with a mandatory approval gate, and only at server level.** This is the nuance that matters:

- **Server-level issues → the AI executes the fix.** *"Turn AI insights into quick resolutions with Copilot SmartFix. From service restarts to disk cleanup, Copilot SmartFix applies the best practice solution."* The announcement is more explicit: SmartFix will *"automatically apply the steps needed to resolve the issue **after you verify its actions**."* ([Cloudways Copilot](https://www.cloudways.com/en/cloudways-ai-copilot.php), [announcement](https://www.cloudways.com/blog/announcing-ai-copilot-general-availability/))
- **Application-level issues → recommendations only.** For WordPress/WooCommerce 5xx problems, Copilot *"generates Insights that contain a root-cause explanation and a set of actionable resolution steps"* — diagnostic steps, **not** automatic fixes. ([Cloudways Copilot](https://www.cloudways.com/en/cloudways-ai-copilot.php))
- **Explicit safety statement:** *"No. Cloudways Copilot does not make any changes on its own. All SmartFix actions require your review and approval."* ([Cloudways Copilot](https://www.cloudways.com/en/cloudways-ai-copilot.php))

So on the four-level scale: **(c) executes a fix with approval** for server issues, **(b) suggests a fix** for application issues. **This is the same posture ServerAlly has taken** — which is strong validation that the approval-gated execution model is the commercially accepted answer, not an over-cautious one.

**What it detects.** Server-level: host health (DoS, bot traffic, brute-force attacks), web-stack health (Apache, NGINX, MySQL, PHP-FPM, caching), disk usage thresholds, inode exhaustion, backup failures. Application-level: WordPress/WooCommerce 5xx errors from plugins, themes, core, database or cache. ([Cloudways Copilot](https://www.cloudways.com/en/cloudways-ai-copilot.php))

**EXACT pricing and AI usage limits — credit-metered:**

| Plan | Monthly cost | AI credits / month |
|---|---|---|
| **Starter** | **$3.99** | **4** |
| **Growth** | **$9.99** | **12** |
| **Scale** | **$19.99 – $80.00** | **25 – 100** |

Source: [Cloudways Copilot page](https://www.cloudways.com/en/cloudways-ai-copilot.php).

**What happens at the limit:** *"Running out of credits halts Insight generation and SmartFix application; basic monitoring continues."* ([Cloudways Copilot](https://www.cloudways.com/en/cloudways-ai-copilot.php)) — i.e. the AI stops, the product keeps working. That is a notably humane cap design worth copying if ServerAlly ever needs one.

**What consumes a credit.** A Cloudways help-centre extract describes the Starter plan as **4 AI Insights credits per month (2 Server Insights + 2 Application Insights) plus 2 SmartFixes**, with **additional credit packs purchasable** on Scale. ([support.cloudways.com](https://support.cloudways.com/en/articles/11959655-how-does-cloudways-copilot-pricing-and-billing-work) — *direct fetch returned HTTP 403; content is from a search-engine extract, so treat the exact split as PARTIALLY VERIFIED*). The same extract states Starter is included at **no additional cost for accounts with a monthly invoice greater than $100** — which **conflicts** with the $3.99 price on the product page. **Treat the Starter tier's true cost as UNVERIFIED**; the most likely reconciliation is "$3.99, waived above $100/month spend," but that is inference, not fact.

**Launch promotion (verified):** *"5 free AI credits monthly (good for 5 detailed Insights), plus 2 Free SmartFixes"* for every Cloudways customer on paid Flexible plans. The announcement says **6 months**; a separate extract says **12 months**. **Duration UNVERIFIED.** ([announcement](https://www.cloudways.com/blog/announcing-ai-copilot-general-availability/))

**Claimed results:** 4× faster issue resolution, 75% time saved, 30+ minutes saved per incident. ([Cloudways Copilot](https://www.cloudways.com/en/cloudways-ai-copilot.php)) Vendor-reported, unaudited.

## 3.2 The other commercial diagnose-and-repair players

| Vendor | Diagnoses? | Repairs? | Price | AI limits |
|---|---|---|---|---|
| **Cloudways Copilot** | Yes | **Yes — server-level, approval-gated** | **$3.99 / $9.99 / $19.99–$80 per month** | **4 / 12 / 25–100 credits per month** |
| **Hostinger Kodee** | Yes | **Yes — "apply fixes", ~200 MCP actions; destructive actions need confirmation** | **Free with VPS hosting** | **None published** |
| **Panelica OpsAI** | Yes | **Yes — "execute multi-step operations", "real infrastructure tasks"** | **Included in $0 / $4.99 / $9.99 / $24.99 per month tiers (gated on domains)** | **None published** |
| **CtrlOps** | Yes | **No — "AI suggests, you approve", command generation only** | **$7/user/mo, $70/yr, $149 lifetime** | **None published** |
| **servermind.dev** | Yes | **Yes — but allowlisted service actions only, behind an auto-expiring "arm" switch** | **Free (MIT), BYO AI key** | Whatever the user's AI provider allows |
| **Chaterm** (OSS) | Yes | **Yes — autonomous multi-host execution, rollback after the fact** | **Free (OSS)** | BYO |

Enterprise AIOps vendors (Datadog Bits AI, Dynatrace Davis, and the AI-SRE startup cohort — Cleric, Resolve.ai, Traversal, NeuBird, Parity, Flip AI, Deductive, Mezmo, Middleware OpsAI, TierZero, Wild Moose, DrDroid, SRE.ai, Ciroos, Datafruit, KnoxOps, Edge Delta) are catalogued in [awesome-devops-ai](https://github.com/hammadhaqqani/awesome-devops-ai) and analysed separately in §4. They target enterprise SRE teams, almost universally hide pricing behind "contact sales", and mostly stop at **investigate + recommend** rather than execute.

## 3.3 What this means for ServerAlly

1. **The approval-gated-execution posture is validated.** DigitalOcean/Cloudways landed on exactly the same answer as ServerAlly: AI executes, human approves, and the vendor says so loudly on the marketing page. ServerAlly's verification gate and read-only-enforced verify step go *further* than anything found in this research — that is a real, defensible differentiator, and it is currently unmarketed.
2. **The credits question deserves a written rebuttal, not a rule.** PRICING-V3 forbids credits on the strength of the Cursor/Replit blowups. Cloudways sells credits for this exact use case without apparent revolt — plausibly because their unit ("an Insight", "a SmartFix") is **user-intent-shaped**, which is precisely the distinction PRICING-V3 itself draws (the Cursor/Replit failure was vendor-side decisions driving the meter). **Cloudways is therefore not a counter-example to the rule — it is a confirming example of the rule's underlying principle.** That is a much stronger position than "credits are banned", and it should be written down that way, because a PM will eventually ask "but Cloudways does it."
3. **The "halt AI, keep monitoring" cap is the best idea found in this research.** Running out of allowance degrades the product to non-AI monitoring rather than locking the customer out. If ServerAlly ever arms `ENFORCE_PLAN_LIMITS`, this is the behaviour to copy.
4. **Application-level repair is an unclaimed gap.** Cloudways explicitly does **not** auto-fix application issues (WordPress 5xx) — only diagnoses them. ServerAlly's `wordpress-rescue` skill and its live-proven WordPress incident missions do exactly that. **This is a concrete, provable "we do what the market leader won't" claim.**

---

# PART 4 — THE ENTERPRISE "AI SRE" COHORT (adjacent category, different buyer)

> Full working notes with every source URL: [`part1b-ai-sre-raw.md`](./part1b-ai-sre-raw.md). All pricing verified against vendor-owned pages on 2026-07-25.

## 4.1 Does the enterprise AI-SRE category actually REPAIR? Mostly no — and the biggest player deliberately refuses to.

| Vendor | Level | Executes fixes on infrastructure? |
|---|---|---|
| **NeuBird** | **(d) autonomous** | Yes — claims scale/rollback/restart on its own |
| **Traversal** | **(c)/(d)** | Yes — claims "automated remediation"; UI shows rollback + approve/dismiss |
| **Doctor Droid** | **(c)/(d)** | Yes — via automated runbooks (auto-scale, drain node) |
| **Resolve.ai** | **(c)** | Yes, but mostly **software-side** (revert commits, PRs, GitHub workflows, silence alerts) |
| **Cleric** | **(b) → (c)** | **Read-only by default**, opt-in write |
| **Datadog Bits AI SRE** | **(a)+(b)** | **No** — investigates, then opens tickets/PRs for humans |
| **Flip AI** | UNVERIFIED | Remediation claimed in a CEO quote; site not machine-fetchable |
| **Parity (YC S24)** | **GONE** | Appears to have left the category entirely |

**The exact wording, vendor by vendor:**

- **NeuBird** — the strongest autonomy claim in the category: *"Executes remediation the way your best engineer would: **scale, roll back, restart**, or hand off with a full audit trail"*, and it *"detects, investigates, and **resolves** production incidents on its own."* ([neubird.ai](https://neubird.ai/))
- **Traversal** — *"Converts diagnosis into action with **automated remediation**."* Its UI screenshots show *"Rolled back to v4.2.0"* and *"Engaged circuit breaker."* ([traversal.com](https://traversal.com))
- **Doctor Droid** — *"automated remediation"* via runbooks it can **RUN**: *"Auto-scale on memory pressure"*, *"Drain node-12 · disk-full."* Note the architecture: **a human authored the runbook; the AI decides when to fire it.** That is meaningfully safer than free-form AI-invented repair. ([drdroid.io](https://drdroid.io))
- **Resolve.ai** — executes, but only on the **software plane**: *"Takes actions within guardrails like **silencing alerts, reverting commits, opening PRs, and executing GitHub workflows**"*, plus *"Define what runs autonomously and what requires approval."* Every action is CI/CD — not a machine. ([resolve.ai](https://resolve.ai))
- **Cleric** — the instructive case, because its own pages are in tension. Homepage: *"**Read-only by default.** Every action logged, every investigation auditable"* and *"Read access by default, write access when you're ready."* Product page: *"**For routine fixes, let Cleric apply them directly.**"* But the docs list write permissions only for **Jira** (create issues) and **GitHub** (branches, PRs) — tickets and code, **not infrastructure mutation**. ([cleric.ai](https://cleric.ai/), [cleric.ai/product](https://cleric.ai/product), [docs.cleric.ai](https://docs.cleric.ai/integrations/overview))
- **Datadog Bits AI SRE — the most important data point in Part 4.** It has a "Take action" docs page, and the **complete** list is: Slack/Teams messages, create incidents, page engineers, create cases, open Jira tickets, and open a PR *"for review in GitHub, and merge when ready."* **Zero infrastructure mutation.** The vendor with the most telemetry, the most trust and the most to lose stopped at diagnose-and-propose. ([Datadog docs](https://docs.datadoghq.com/bits_ai_sre/))

**Take the lesson:** *"automated remediation"* in this category is a marketing claim more often than a documented capability — Traversal and Flip AI both use remediation language that could not be confirmed with a permission model or docs page. Expect exactly the same scepticism to be applied to ServerAlly's claims, which is why the **verification gate is worth marketing as evidence rather than as an adjective.**

## 4.2 EXACT published prices — and every single one is credit-metered

Most of the category hides pricing behind "contact sales". Four vendors publish:

| Vendor | Published price | Unit economics |
|---|---|---|
| **Doctor Droid** | **$99/month** (Teams) | 99 investigation credits; top-up **$1/credit**; **unlimited users**; 14-day trial ([drdroid.io/pricing](https://www.drdroid.io/pricing)) |
| **Datadog Bits AI SRE** | **$500 per 500 credits/month** (annual) or **$1.30/credit** on-demand | **1 autonomous investigation ≈ 6.5 credits ≈ $6.50** ([datadoghq.com/pricing](https://www.datadoghq.com/pricing/?product=ai-credits)) |
| **Cleric** | **$2,000/month billed annually = $24,000/year** | 1,000 credits; **1 "Issue" = 10 credits = $20**; credits roll over 1 month up to 2×; trial = 14 days / 500 credits ([cleric.ai/pricing](https://cleric.ai/pricing)) |
| **NeuBird** | Custom | Credit *consumption* published (investigation = 1 credit/run); credit *price* not published, so not convertible to dollars |
| Resolve.ai | **No public price** — contact sales | Logo wall: Coinbase, DoorDash, Expedia, Snowflake, MongoDB, Robinhood, Autodesk, Toast ([resolve.ai](https://resolve.ai)) |
| Traversal | **No public price** — contact sales | "Strategic Investment from Amex Ventures", amount undisclosed ([traversal.com](https://traversal.com)) |

**Every vendor that publishes a price meters AI investigations. Not one prices per-server.** That is the exact inverse of the infrastructure-management market (Ploi/RunCloud/Forge = flat per-server) — and ServerAlly's Pricing-v3 hybrid (per-server platform + AI as a separate choice) sits deliberately between the two.

Datadog's per-action table is the cleanest cost benchmark in the whole research: Bits Chat message ~0.5 credits (~$0.50), Agent Builder run ~3 (~$3.00), Code Fix ~5 (~$5.00), **autonomous investigation ~6.5 (~$6.50)**. ([datadoghq.com/pricing](https://www.datadoghq.com/pricing/?product=ai-credits))

> **Put ServerAlly's own number beside that:** the admin console measures **$0.096 per action**. Datadog charges **~$6.50 for one autonomous investigation** and Cleric **$20 per Issue**. ServerAlly's per-action COGS is roughly **1.5% of what Datadog charges** for a comparable unit of AI work. The $0.096 problem is a *pricing-model* problem, not a cost-of-goods catastrophe — the market is charging 60–200× that per investigation.

## 4.3 Funding / maturity (verified only)

- **Flip AI** — **$6.5M seed, 2023-11-09**, led by Factory (Morgan Stanley Next Level Fund, GTM Capital participating). ([DBTA](https://www.dbta.com/Editorial/News-Flashes/Flip-Debuts-its-Observability-Platform-Powered-by-an-LLM-Announces-65M-in-Funding-161379.aspx))
- **Traversal** — Strategic Investment from **Amex Ventures**; **amount undisclosed**. ([traversal.com](https://traversal.com))
- **Parity / CreativeMode** — **YC Summer 2024**, founded 2024, **team size 5**; backed by YC and General Catalyst; amounts undisclosed. ([YC](https://www.ycombinator.com/companies/parity))
- **Resolve.ai** — a third-party page referenced a "$1B valuation". **UNVERIFIED, single secondhand source — do not cite.**
- **NOT FOUND / UNVERIFIED:** Cleric funding & team size; Resolve.ai funding/founding/team; Traversal amount/founding/team; NeuBird funding/founding/team; Doctor Droid funding/founding/team; Flip AI founding date & team size.

## 4.4 The four findings that matter for ServerAlly

1. **Nobody is repairing the machines ServerAlly manages.** Every vendor's remediation vocabulary is Kubernetes: scale a replicaset, roll back a deploy, restart a pod, drain a node, revert a commit. **Not one** says: restart MariaDB, fix the PHP-FPM socket, quarantine a webshell, re-issue an expired cert, fix `wp-content` permissions. No vendor's docs describe SSH-based repair of a non-containerised host. **The single-server / hosting-panel / small-business repair problem is genuinely unclaimed by this entire category.**
2. **The buyer is completely different, and it cuts both ways.** These sell into enterprise SRE orgs that already run Datadog/Prometheus and have an on-call rotation — their whole input assumption is a mature observability stack. ServerAlly's user has **no observability stack at all; the agent *is* the observability.** So they are not competitors for ServerAlly's buyer — but their pricing and proof points don't transfer either.
3. **There is a large empty price band.** Hosting control panels sit at **$8–49/mo**; AI SRE starts at **$99/mo** (Doctor Droid) with the category's centre of gravity at **$2,000+/mo** (Cleric $24k/yr). **Nothing serious occupies the gap** — which is where ServerAlly's semi-technical agency/MSP buyer actually lives.
4. **Datadog's refusal is the single most important signal in Part 4.** The player with the most telemetry, the most trust and the largest install base **deliberately stopped at "open a PR for review"** rather than execute infrastructure repair. Everyone doing true repair is a startup. That is simultaneously the opportunity (incumbents are conservative) and the warning (they have reasons).

## 4.5 Honest counter-evidence

- **Parity's disappearance is a real negative signal — and the evidence is concrete.** Their domain now refuses connections, and their YC page shows a different company: **CreativeMode, "Lovable for Minecraft mods"** — same three founders (Wilson Spearman, Coleman Smith, Jeffrey Tsaw), same S24 batch, team of 5. ([YC](https://www.ycombinator.com/companies/parity)) A well-publicised "world's first AI SRE" abandoned the category in roughly two years. Whatever the cause, it is evidence that this is a hard category to build a venture-scale business in, and it belongs in any honest internal case for ServerAlly — not buried.
- **Doctor Droid at $99/mo with unlimited users and BYO-LLM (OpenAI/Anthropic/Bedrock/local on Enterprise) is architecturally the closest thing to ServerAlly's Layer-2 plan** that anyone has shipped. Not a competitor today (Kubernetes buyer), but the nearest candidate if it moves down-market. **Worth monitoring.**
- **Doctor Droid also markets model-switching as a customer benefit** — one credit reportedly covers ~3 investigations because it *"routes simple investigations to cheaper models."* **That is exactly ServerAlly's Smart Model Ladder**, sold as "your credit goes further" rather than hidden as an internal cost optimisation. **Worth stealing: make the ladder a customer-visible value, not just a margin lever.**

---

# PART 5 — STRATEGIC SYNTHESIS FOR SERVERALLY

## 5.1 The competitive map, drawn honestly

| Band | Who | Price | AI depth | Threat to ServerAlly |
|---|---|---|---|---|
| **Bundled-free, mass-market** | **Hostinger Kodee** | **$0 (in a $6.49/mo VPS)** | Executes fixes, ~200 MCP actions, 914k conversations | **Highest** — same buyer, same promise, zero price |
| **Cheap AI server tools** | CtrlOps, Panelica OpsAI | **$4.99–$9.99/mo**; CtrlOps **$7/user** | Panelica executes; CtrlOps suggests-only | **High on price**, low on depth |
| **AI-repair add-on** | **Cloudways Copilot** | **$3.99–$80/mo, credit-metered** | Diagnoses + executes server fixes on approval | **High** — proves the model, sets the price |
| **Self-hosted PaaS** | Coolify, Dokploy, Dokku, CapRover, Easypanel | **$4.50–$16.90/mo** | MCP only; no agent | **Medium** — price anchor, not AI rivals |
| **Enterprise AIOps / AI SRE** | Portainer, Cleric, Resolve, Traversal, et al. | **$105/mo → "contact sales"** | Mostly investigate-and-recommend | **Low** — different buyer entirely |
| **Open-source AI terminals** | Chaterm (3,036★), vibeshell, servermind.dev (4★) | **Free** | Chaterm executes autonomously | **Low-medium** — no commercial motion |

## 5.2 The five things ServerAlly has that nobody in Group D has

Verified across all 15+ products researched, **not one** has:

1. **A verification gate** — an independent, read-only-enforced adversarial check that a claimed fix actually worked. The closest anyone gets is Portainer-Run's *"fetches live diagnostic data before answering"*, which is input-side, not outcome-side.
2. **Multi-step resumable missions** with per-step safety validation, mid-mission approval, budget limits and detached background execution. Every competitor's AI is single-shot: one prompt → one command or one summary.
3. **Prompt-injection defence on server-derived data.** Nobody else even discusses it — despite all of them feeding attacker-controllable logs and file contents into an LLM.
4. **Packaged expert skills with a routing layer.** Panelica's "15 experts" is the only comparable *packaging*, and it appears to be persona routing rather than procedural runbooks.
5. **Incident narratives from a durable transcript** — the "explain how this happened" report. Nothing in this category produces an owner-facing story of an incident.

**These are all real, all shipped, and all currently unmarketed.** The research says ServerAlly's engineering lead is larger than its marketing lead by a wide margin.

## 5.3 The three uncomfortable truths

1. **"AI that manages your server" is no longer differentiated — "AI that manages your server *safely and autonomously*" still is.** Kodee, Panelica, Cloudways, Chaterm and CtrlOps all ship chat-to-server. The commodity is the chat box. The scarce thing is the safety architecture.
2. **BYO-key AI (Pricing-v3 Layer 2a) is already shipped by Dokploy and servermind.dev.** It is a cost strategy, not a moat. Do not build marketing around it.
3. **ServerAlly's measured AI cost is the real strategic risk, not competitors.** The admin console reads **$0.096/action against a $0.05 assumption**, while Hostinger gives an unmetered AI away free and CtrlOps charges $7/user unlimited. Competitors are setting a price expectation that ServerAlly's current COGS cannot meet. The Cloudways credit model exists precisely because that math is hard — and Cloudways is owned by DigitalOcean, who can afford it better than ServerAlly can.

## 5.4 The counter-positioning that actually works

Against **Hostinger Kodee** (the main threat), three defensible lines, all factually true:

- **"Your host's AI only manages your host's servers."** Kodee is locked to Hostinger. ServerAlly manages any Linux/Windows box, any cloud, any panel — and a *fleet across providers*. An agency with servers at five hosts cannot use Kodee at all.
- **"It fixes; we prove it fixed."** The verification gate is a claim no competitor can make.
- **"It answers questions; we run the whole job."** Missions vs single-shot commands.

Against **Cloudways Copilot**: they explicitly **do not auto-fix application-level problems** (WordPress 5xx) — only diagnose them. ServerAlly's WordPress rescue missions do exactly that, live-proven. That is a precise, provable gap.

Against **CtrlOps** ($7/user, unlimited): they are *"AI suggests, you approve"* — command generation. Sell autonomy-with-safety, not chat. But note their price is a local desktop app with near-zero AI COGS; do not price-match without understanding that.

## 5.5 Recommended next action

**Write the competitive-defence note into `docs/PRICING-V3.md` before the beta cohort sets numbers.** Specifically: (a) record that Cloudways sells credits successfully and *why that is consistent with — not a refutation of — the credits ban* (their unit is user-intent-shaped, which is the rule's actual principle); (b) adopt Cloudways' **"AI halts, monitoring continues"** cap behaviour as the design for `ENFORCE_PLAN_LIMITS`; and (c) close the per-server pricing hole Portainer's vCPU cap exposes, before per-server pricing hardens.

---

## Appendix — items explicitly UNVERIFIED

- **Panelica**: whether OpsAI requires the customer's own Anthropic API key (**sources conflict**); any approval/safety gate; launch date, team size, customer count, funding; the free tier's true scope (homepage "Star / full features" vs pricing page "Starter / 3 domains / limited").
- **Hostinger Kodee**: which AI model powers it; any internal rate limits; whether the 91%/914k figure covers VPS terminal sessions specifically or all hosting support.
- **Cloudways Copilot**: the exact Starter cost ($3.99 on the product page vs "free above $100/mo invoice" in a help-centre extract — the help-centre page returned **HTTP 403** on direct fetch); credit rollover policy; extra credit-pack pricing; promo duration (6 vs 12 months).
- **CtrlOps**: funding; exact Product Hunt rank; G2 score and review count; their own AI cost model (BYO vs bundled).
- **Chaterm**: the backing company; full supported-model list; the non-standard "NOASSERTION" licence terms; whether any paid tier exists.
- **Easypanel**: all structural traction (closed source, no repo); exact licence terms; template count; annual prices; funding.
- **Coolify MCP tool count** (docs say "50+", another source says ~10); **Dokploy MCP auth mechanism**; **Dokploy funding**; **Portainer total funding** ($7.2M per Tracxn, one source claims $14M); **Portainer-Run maturity** (alpha/beta/GA).
- **Netcatty**, **machine0**: noted but not researched in depth.
- **AI SRE cohort (Part 4):** **Flip AI's entire current product** — site returns no fetchable content; positioning and any repair capability rest on a Nov-2023 press release, and the only remediation claim is a CEO quote about reducing MTTR, which is **not evidence of execution**. **Resolve.ai's rumoured $1B valuation** and its founder attribution both **failed primary-source verification — do not cite either.** **NeuBird's credit dollar value** is unpublished, so its pricing is not convertible to dollars. **Datadog's older per-investigation pricing** (~$500/20 investigations) and its **2025-12-02 GA date** come from third-party blogs only. **Funding, team size and founding dates are unpublished for Cleric, Resolve.ai, Traversal, NeuBird and Doctor Droid.** **Cloud-marketplace (AWS/Azure/GCP) listings were not checked** — a background pass was still running when the search budget ran out.
- **Whether ANY vendor's "remediation" touches a bare Linux server:** no vendor's docs described SSH-based repair of a non-containerised host. That is absence of evidence rather than evidence of absence — but it was **consistent across all seven** vendors examined.

**Method note:** this session exhausted its 200-call web-search budget. Remaining gaps above are answerable with a handful of targeted fetches in a follow-up session; the highest-value ones are the Panelica BYO-key question and the Cloudways Starter price.

# Competitor Research — GROUP A: "Build & Deploy" Server Control Platforms

**Prepared for:** ServerAlly competitive positioning
**Date:** 2026-07-25
**Vendors:** Ploi.io · RunCloud · Laravel Forge · SpinupWP · ServerPilot · Moss (moss.sh)

**Method:** Vendor's own pages treated as authority (pricing page, features page, docs, changelog, docs `llms.txt`, docs sitemaps). Third-party sources (reviews, comparison sites) used only for user sentiment and where the vendor page is JS-rendered and unreadable. DNS/WHOIS checked directly for Moss. Anything I could not confirm is marked **UNVERIFIED** rather than guessed.

---

## 0. Executive summary — the five findings that matter most

1. **Moss (moss.sh) is DEAD.** Not "declining" — gone. The domain lapsed, was drop-caught by a backorder registrar on 2025-09-27, briefly repopulated with a WordPress copy of Moss's old marketing copy, and has had **global DNS SERVFAIL since ~2026-03-22**. Search engines still surface the squatter content as if it were a live product. Evidence in §6. **Do not cite moss.sh as a live competitor.**

2. **The market prices on SERVERS, not usage.** Every surviving vendor gates on servers (Ploi, RunCloud, Forge, SpinupWP) or servers **and** apps (ServerPilot). None meters AI, actions, deployments-in-production, or requests. Forge says so explicitly: *"Is Forge usage-based pricing? No."* ([laravel.com/forge/pricing](https://laravel.com/forge/pricing)). The only "req/min" numbers in the market are **API rate limits inside the plan table** (Ploi 60/120/240; Forge 60), never a billed unit.

3. **Ploi is the only vendor with a first-party, OAuth-secured MCP server** — 60 tools, "Included in the Pro plan and up" ([ploi.io/features/mcp](https://ploi.io/features/mcp)). RunCloud, Forge and SpinupWP have **community/third-party** MCP servers only (unofficial GitHub projects). This is ServerAlly's closest direct competition on the "bring your own AI" lane, and Ploi's design choices (read-only marking, no destructive deletes, OAuth not API keys) mirror ServerAlly's MCP plan almost exactly.

4. **Nobody in Group A does AI reasoning/remediation.** Ploi's MCP is a thin API adapter (the customer's AI does the thinking). SpinupWP's "Assistant" sounds like AI but is a deterministic maintenance-todo engine. No vendor offers agentic missions, natural-language incident response, or plain-English explanation. **This is the whole gap ServerAlly occupies.**

5. **Support quality is the #1 churn driver across the group**, ahead of missing features. RunCloud ("the support is abysmall", price-increase anger), Ploi (tickets unsolved 15+ days), SpinupWP ("support is so-so and quite slow") all show the same pattern. Feature complaints are secondary and specific (staging, per-client roles, backup reliability).

---

## 1. PLOI.IO

### 1.1 Positioning & buyer

**One-liner:** "Server Management Tool" — provision, deploy and monitor servers on your own cloud account, with a strong Laravel/PHP tilt but broad app support.
**Buyer:** Developers and small-to-medium dev teams; "built by developers, for developers" ([ploi.io](https://ploi.io/)). Laravel-first (queue workers, scheduler, Octane management) but explicitly supports WordPress, Statamic, Craft CMS, Node. Agencies are served via the separate **Ploi Core** white-label product.

### 1.2 Exact pricing

Source: [ploi.io/pricing](https://ploi.io/pricing). Prices shown in both EUR and USD; annual = 10% discount.

| Plan | Monthly | Annual | Servers | Sites | Deployments | API rate limit |
|---|---|---|---|---|---|---|
| **Free** | €0 / $0 | €0 | **Up to 1** | Up to 1 | **"5 per month"** | **None** |
| **Basic** | €8 / $10 | €86.40 / $108 | **Up to 5** | Unlimited | Unlimited | "60/req. per min." |
| **Pro** | €13 / $16 | €140.40 / $172.80 | **Up to 10** | Unlimited | Unlimited | "120/req. per min." |
| **Unlimited** | €30 / $36 | €324 / $388.80 | **Unlimited** | Unlimited | Unlimited | "240/req. per min." |

**Gates on:** servers (primary), plus API rate limit tier, plus feature gating.
**Free trial:** 5-day free trial on the Pro plan, no credit card required.

**Feature gating by tier** (from the pricing page):
- **Basic (€8)** adds: Scheduled deployments, Website Isolation, Domain Aliases, Tenants, Script Access, Firewall Management
- **Pro (€13)** adds: **File Explorer, Automatic Backups, Server Monitoring, Zero Downtime Deployment**, and **MCP**
- **Unlimited (€30)** adds: **Team Management**, Site Monitoring, Status Pages

> ⚠️ Note the aggressive gating: **backups, monitoring, zero-downtime deploys and the file manager are all Pro-only**, and **team management is Unlimited-only (€30)**. This is the source of the recurring complaint that "Ploi seems to be missing a lot of features unless you get their best plan" ([LowEndTalk](https://lowendtalk.com/discussion/202240/enhance-vs-runcloud-vs-serveravatar-vs-ploi)).

### 1.3 Exhaustive feature checklist

Sources: [ploi.io/features](https://ploi.io/features), [ploi.io](https://ploi.io/), [ploi.io/features/mcp](https://ploi.io/features/mcp), [ploi.io/whitelabel](https://ploi.io/whitelabel), [ploi-core.io](https://ploi-core.io/)

| Capability | Status | Detail |
|---|---|---|
| Server provisioning from blank VPS | ✅ Yes | "Production-ready servers … configured and secured in under 12 minutes" |
| Cloud provider integrations | ✅ Yes | UpCloud, Hetzner, Scaleway, Hostinger, DigitalOcean, AWS (EC2), Vultr, Linode + custom VPS |
| One-click app installs | ✅ Yes | Laravel, WordPress, Statamic, OctoberCMS, Craft CMS, Nextcloud, phpMyAdmin |
| Git deployment + auto-deploy on push | ✅ Yes | GitHub, GitLab, Bitbucket; webhooks; "Automatic deployment on git push" |
| Custom deploy scripts | ✅ Yes | "Script Access" (Basic+); deploy scripts |
| Zero-downtime / atomic deploys | ✅ Yes | **Pro+ only** — "Zero downtime atomic deployments" |
| Staging sites + clone/push-to-live | ⚠️ Partial | "Staging-to-production workflow" advertised; no dedicated one-click clone/refresh product surface documented — **push-to-live specifics UNVERIFIED** |
| Scheduled deployments | ✅ Yes | Basic+; "Scheduled releases during off-peak hours" |
| PHP / Node / Python / Ruby versions | ⚠️ Partial | PHP multi-version + Node supported (testimonials cite Node apps). Python/Ruby **UNVERIFIED** |
| SSL (Let's Encrypt / wildcard / custom) | ✅ Yes | Let's Encrypt; SSL expiry notifications. Wildcard/custom **UNVERIFIED** |
| DNS management | ✅ Yes | "DNS management (Cloudflare integration)" |
| Database management | ✅ Yes | Databases, dedicated database servers, phpMyAdmin one-click |
| Email hosting/forwarding | ⚠️ Partial | An "Email" **server type** can be provisioned; mailbox/forwarder management **UNVERIFIED** |
| Cron / scheduled jobs | ✅ Yes | Cronjobs (MCP exposes list + create) |
| Queue/daemon workers (supervisor) | ✅ Yes | "Daemons & queues", Laravel queue workers, Octane |
| Firewall management | ✅ Yes | Basic+; firewall rules list/create |
| Backups | ✅ Yes | **Pro+**. Database **and** file backups, scheduled; destinations **S3, Google Drive, Dropbox**. Retention/restore specifics **UNVERIFIED** |
| Monitoring (CPU/RAM/disk) + alerts | ✅ Yes | **Pro+** server monitoring; real-time CPU/memory/disk/network + historical analytics. Alerts via **email, Slack, Discord, Telegram** |
| Uptime / site monitoring + status pages | ✅ Yes | **Unlimited only** — uptime + response time + public status pages |
| Log viewer | ✅ Yes | Server logs and site logs (MCP exposes "view logs") |
| File manager | ✅ Yes | **Pro+** — browser-based "File Explorer", no SSH needed |
| SSH key management | ✅ Yes | Standard |
| Team members + roles/permissions | ✅ Yes | **Unlimited only** — "Invite team members, assign granular permissions per server" |
| White-label / agency branding | ✅ Yes | Via **Ploi Core** (separate self-hosted product) |
| Client billing / reselling | ✅ Yes | **Ploi Core**: "Built-in billing with Stripe", assign customers websites or server space |
| Marketplace / templates / recipes | ✅ Yes | "Marketplace for third-party integrations" |
| WordPress-specific tooling | ⚠️ Partial | One-click WP install; no WP-specific update/cache management surface documented |
| Site migration tools | ⚠️ Partial | Testimonials mention migration support; no documented migration product — **UNVERIFIED** |
| REST API | ✅ Yes | Full REST API; rate limit by plan (60/120/240 req/min); **not available on Free** |
| CLI | ⚠️ UNVERIFIED | Not advertised on the features page |
| Mobile app | ✅ Yes | "Mobile app for on-the-go management" |
| **AI features / MCP server** | ✅ **Yes — first-party** | See §1.4 |
| Load balancer / Docker / Redis / Elasticsearch server types | ✅ Yes | Provisionable server types: load balancer, Docker, Redis, Valkey, Worker, Meilisearch, Elasticsearch, Storage, Email, Plain |

### 1.4 Ploi's MCP server — the closest thing to a direct ServerAlly competitor

Source: [ploi.io/features/mcp](https://ploi.io/features/mcp)

- **60 curated tools** across: Servers (list/get/create/logs/services/restart), Sites (list/get/create/logs/env vars/nginx config), Deployments (deploy/logs/scripts/quick-deploy toggle), Databases (list/create/duplicate/users/reset passwords), Cronjobs, SSL certificates, Daemons & queues, Firewall rules, Tenants & aliases, Insights.
- **Auth: OAuth with PKCE**, not API keys. "Add the server, approve it once in your browser, and start asking." Granular scopes matching the REST API; team-level access restrictions.
- **Clients:** "Works with Claude · Claude Code · ChatGPT · Cursor · VS Code · Windsurf + any MCP client".
- **Safety design:** *"Read tools are marked read-only for your assistant, mutations queue safely on your server, and destructive deletes are left out by design."* And: *"Servers, sites and databases cannot be deleted through MCP. Removing things stays a human decision."*
- **No shell/run-command tool** — the toolset is bounded to Ploi API operations.
- **Plan requirement:** *"Included in the Pro plan and up"* (i.e. €13/mo+).
- Endpoint: `ploi.io/api/mcp`.

**Read-across for ServerAlly:** Ploi validated (a) MCP as a paid-tier feature, (b) OAuth over static keys, (c) bounded tools with no destructive deletes — all three match ServerAlly's shipped design. ServerAlly's differentiators remaining: the `mcp:admin` shell tool (Ploi has none), multi-OS/Windows/hosting-panel coverage, and the entire first-party AI layer (Ally) that Ploi does not attempt.

### 1.5 Praise and complaints

**Praise:** Feature velocity — a customer testimonial on the homepage: *"New features ship every single week."* Long-term users cite "incredible feature set, lovely UI". Discord support is praised by some.

**Complaints** (Trustpilot, [trustpilot.com/review/ploi.io](https://www.trustpilot.com/review/ploi.io) — page is bot-protected, quotes below relayed via search-engine summaries of that page, so treat as **indicative not verbatim-verified**):
- Support responsiveness is the dominant theme: *"tickets left unsolved for 15+ days"*, *"very low quality of support with 1–2 days response time"*, *"support mostly providing ideas instead of checking problems in depth"*.
- Bugs: *"a cron process feature not working as expected for months"*.
- Feature gating: *"lack of support for basic plans limiting access to features"*.
- Docs: *"limited documentation requiring community interaction for solutions"*.
- LowEndTalk: *"Ploi seems to be missing a lot of features unless you get their best plan"* ([source](https://lowendtalk.com/discussion/202240/enhance-vs-runcloud-vs-serveravatar-vs-ploi)).

Trustpilot summary metric reported as "5 stars with 100 customer reviews" — **the star figure is UNVERIFIED** (could not load the page directly).

### 1.6 Notable

- **Ploi Core** ([ploi-core.io](https://ploi-core.io/)): self-hosted, white-label hosting panel built on Ploi as backbone. *"Ploi Core is now completely free! No license fees, no renewal costs."* Requires an **Unlimited** Ploi subscription (€30/mo). Includes **Stripe billing**, unlimited customers with no per-customer cost, customer logins for site creation + FTP, custom branding/colors/logo, auto-updates, multi-language, dark mode, GDPR (you host the data). **This is a serious agency/MSP play** and the most complete reselling story in Group A.
- **Ploi Cloud** ([ploi.cloud](https://ploi.cloud/features/ai)) is a *separate* managed PaaS product from the same company, also with AI/MCP messaging — worth tracking separately.

---

## 2. RUNCLOUD

### 2.1 Positioning & buyer

**One-liner:** "PHP Cloud Server Management Panel" — a cPanel alternative for PHP/WordPress on your own VPS.
**Buyer:** WordPress-heavy freelancers, agencies and small hosts. Their own marketing positions against cPanel and ServerPilot: *"straightforward, flat-rate pricing"* with *"no per-site charges"* and *"no per-app costs"* ([runcloud.io/blog/cpanel-alternatives](https://runcloud.io/blog/cpanel-alternatives)). Enterprise tier targets "enterprise hosting companies" ([runcloud.io/pricing](https://runcloud.io/pricing)).

### 2.2 Exact pricing

> **Sourcing note:** [runcloud.io/pricing](https://runcloud.io/pricing) renders prices client-side via Paddle JS and could not be read directly. I confirmed the **plan names** from the live page's server-rendered HTML (Essentials · Professional · Business · Enterprise) and took the **prices and limits from RunCloud's own blog content** on runcloud.io. Cross-checked across two RunCloud articles.

| Plan | Monthly | Servers | Web apps | Backup storage | Staging envs | Team seats | API |
|---|---|---|---|---|---|---|---|
| **Essentials** | **$9/mo** | **1** | Unlimited | 2 GB | 1 | — | ✗ |
| **Professional** | **$19/mo** | **50** | Unlimited | 10 GB | 10 | — | ✗ |
| **Business** | **$49/mo** | **100** | Unlimited | 30 GB | Unlimited | **10** | ✅ |
| **Enterprise** | **$399/mo** | **500** | Unlimited | 100 GB | Unlimited | **50** | ✅ high-volume |

Sources: [runcloud.io/blog/cpanel-alternatives](https://runcloud.io/blog/cpanel-alternatives), [runcloud.io/blog/best-node-js-hosting](https://runcloud.io/blog/best-node-js-hosting). Plan names confirmed at [runcloud.io/pricing](https://runcloud.io/pricing).

**Gates on:** servers (primary) + backup storage + staging environments + team seats + API access.
**Free trial:** 5-day free trial ([runcloud.io/blog/best-node-js-hosting](https://runcloud.io/blog/best-node-js-hosting)).
**Annual pricing:** **UNVERIFIED** — could not read the annual toggle.
**Per-plan API rate limits:** **UNVERIFIED** — the docs confirm limits exist and that "upgrading plans increases API limits" ([runcloud.io/docs/runcloud-limits-usage](https://runcloud.io/docs/runcloud-limits-usage)) but the numbers are not published there.

**Feature gating highlights:**
- **Professional ($19)** adds: application cloning, custom NGINX configs, 6G/7G firewall
- **Business ($49)** adds: **zero-downtime atomic deployments**, advanced SSL, **team management**, **Cloudflare DNS**, ModSecurity WAF, **API access**

> ⚠️ **API access is gated to the $49 tier.** That is unusually high — Ploi gives API from €8, Forge and SpinupWP give it on every paid plan. Any agency wanting automation must buy Business.

> ⚠️ **Pricing changed recently.** Older third-party pages still list Basic $8 / Pro $15 / Business $45 (e.g. [propicked.com](https://propicked.com/hosting/runcloud/pricing) titled "$8–$45/mo: All 3 Plans"). The live plan names (Essentials/Professional/Business/**Enterprise**) confirm the newer four-tier structure is current. Multiple Trustpilot complaints reference a price increase "that went into effect immediately".

### 2.3 Exhaustive feature checklist

Sources: [runcloud.io/features](https://runcloud.io/features), RunCloud docs navigation ([runcloud.io/docs/runcloud-limits-usage](https://runcloud.io/docs/runcloud-limits-usage) sidebar), [runcloud.io/backup](https://runcloud.io/backup), [runcloud.io/docs/category/dns-manager](https://runcloud.io/docs/category/dns-manager)

RunCloud's own docs navigation enumerates its capability areas: *Servers · Web Applications · Backup · WordPress · Laravel · Git Deployment · Atomic Deployment · User Management · DNS Manager · NGINX · OpenLiteSpeed & LiteSpeed Enterprise · Containerized/Docker · Account & Billing · Migration · API Documentation · Monitoring*.

| Capability | Status | Detail |
|---|---|---|
| Server provisioning from blank VPS | ✅ Yes | "server configuration is automated with the best configuration" |
| Cloud provider integrations | ✅ Yes | Provider list **UNVERIFIED** in detail; connects to any VPS + major providers |
| One-click app installs | ✅ Yes | One-click WordPress; Laravel; general PHP apps |
| Git deployment + auto-deploy | ✅ Yes | Dedicated "Git Deployment" docs section |
| Custom deploy scripts | ✅ Yes | Deployment scripts (part of git deployment) |
| Zero-downtime / atomic deploys | ✅ Yes | **Business ($49)+** — "Atomic Deployment" docs section |
| Staging sites + clone | ✅ Yes | Staging environments (1 / 10 / unlimited by tier); **application cloning** from Professional |
| PHP version management | ✅ Yes | "Web Applications can be configured to different PHP versions" |
| Node / Python / Ruby | ⚠️ Partial | Docker/containerized section exists; RunCloud is PHP-first. Native Node/Python management **UNVERIFIED** |
| SSL (Let's Encrypt / wildcard / custom) | ✅ **Yes, all three** | "1-click installation of free SSL/TLS by Let's Encrypt" **including wildcard SSL**, plus custom provider options |
| DNS management | ✅ Yes | **DNS Manager via Cloudflare** (Business+). "RunCloud automatically creates or updates DNS records when you deploy a new web application" |
| Database management | ✅ Yes | Databases + users; phpMyAdmin **UNVERIFIED** |
| Email hosting/forwarding | ❌ No | Not in docs nav or features |
| Cron / scheduled jobs | ✅ Yes | Supported (part of web app management) |
| Queue/daemon workers (supervisor) | ✅ Yes | Supervisor jobs supported |
| Firewall management | ✅ Yes | Default firewall (22/80/443 + 34210 for RunCloud); dashboard port control; **Fail2Ban** (10-hour IP ban on failed SSH, unban from UI); **6G/7G firewall** (Professional+); **ModSecurity WAF** (Business+) |
| Backups | ✅ Yes | Files + databases + web apps. Schedules **"from a 12-hours interval to a 7-day interval"**; retention **"up to 1 month"**; **restore to any server** (used for duplicating staging). Destinations: RunCloud native storage (2/10/30/100 GB by plan) + external providers (S3 etc., "no strict limit"), + local server-side storage. Storage upgradeable **"up to 3 TB"** |
| Monitoring + alerting | ✅ Yes | Monitoring docs section; alert channel list **UNVERIFIED** |
| Log viewer | ⚠️ UNVERIFIED | Not explicitly confirmed on vendor pages read |
| File manager | ⚠️ UNVERIFIED | Not confirmed |
| SSH key management | ✅ Yes | SSH key + user management |
| App isolation | ✅ Yes | "Web Applications … are sandboxed and isolated from each other" |
| Team members + roles | ✅ Yes | **Business+** — 10 seats ($49) / 50 seats ($399). Workspaces + team member resource allocation. "share resources with clients or team members" |
| White-label / agency branding | ❌ Not found | No white-label capability surfaced on vendor pages |
| Client billing / reselling | ❌ Not found | — |
| Marketplace / templates | ⚠️ UNVERIFIED | — |
| **WordPress-specific tooling** | ✅ **Strong** | **RunCloud Hub** — WordPress caching plugin with Cloudflare cache integration, purge from WP dashboard; dedicated WordPress docs section |
| Site migration tools | ✅ Yes | Dedicated "Migration" docs section |
| REST API | ✅ Yes | **Business ($49)+ only**. Rate limits exist and scale with plan (numbers **UNVERIFIED**) |
| CLI | ⚠️ UNVERIFIED | — |
| Mobile app | ✅ Yes | iOS app exists ([apps.apple.com/…/runcloud/id1636235308](https://apps.apple.com/mm/app/runcloud/id1636235308)) |
| **AI features / MCP** | ❌ **No first-party** | Community MCP only: [github.com/aleksanderem/runcloud-mcp](https://github.com/aleksanderem/runcloud-mcp) (requires user's `RUNCLOUD_API_KEY`/`API_SECRET`). A separate "RunCloud AI" at myrun.cloud appeared in search but **the host refused connection when tested (2026-07-25) and its affiliation with RunCloud is UNVERIFIED — assume third-party** |
| OpenLiteSpeed / LiteSpeed Enterprise | ✅ Yes | Dedicated docs section — a genuine differentiator vs Forge/SpinupWP |
| Docker / containerized | ✅ Yes | Dedicated docs section |

### 2.4 Praise and complaints

RunCloud has the **most negative sentiment in Group A.** Themes from [trustpilot.com/review/runcloud.io](https://www.trustpilot.com/review/runcloud.io) (page bot-protected; quotes relayed via search-engine summaries of that page — **indicative, not verbatim-verified**):

- **Support is the dominant complaint:** *"The general product is fine, the support is abysmall"*; support *"barely understands basic terminal commands"*; technical support *"too limited, with unsatisfactory responses even for WordPress apps"*.
- **Backup reliability:** *"the backup function was buggy and didn't backup every week even though it was supposed to."* — a serious trust failure for the feature agencies buy the product for.
- **RunCloud Hub caching bug — data leakage:** the Hub caching feature was reported buggy with site exclusion not working, *"leading to WooCommerce customers seeing other customers' data."* This is the single most damaging complaint found across all six vendors.
- **Price increases + added limits driving churn:** users reported wanting to offboard after *"a price increase that went into effect immediately"*, and that RunCloud *"kept increasing pricing and adding limits"*, with a perception the company *"cares more about profit than customer satisfaction."*
- LowEndTalk reports *"significant degradation and more bugs … over time"* ([source](https://lowendtalk.com/discussion/202240/enhance-vs-runcloud-vs-serveravatar-vs-ploi)).

**Praise:** one-click installers, backups (when working), breadth of features, no per-app charges (vs ServerPilot), and being the most actively developed direct ServerPilot alternative.

### 2.5 Notable

- Four-tier structure with a **$399 Enterprise** tier is the most aggressive upmarket move in Group A — they're chasing hosting companies, not just agencies.
- The **Essentials tier is 1 server** — noticeably stingier than Ploi's 5 at a similar price, and against Forge's unlimited.
- **Churn signal:** the combination of support complaints + immediate price increases + a data-leak-class bug is the strongest "winnable customers" signal in this group.

---

## 3. LARAVEL FORGE

### 3.1 Positioning & buyer

**One-liner:** *"Forge gives root access to servers without the cognitive overhead. One-click instant provisioning, zero-downtime deployments, and automated SSL."* ([laravel.com/forge](https://laravel.com/forge))
**Buyer:** PHP/Laravel developers, dev shops, agencies and SaaS teams. Built by the Laravel team. Explicitly not Laravel-only: *"it also supports vanilla PHP, WordPress, Statamic, and other stacks, including Node.js, Nuxt, and Next.js."*
**Scale (vendor-stated):** 970k servers · 3M sites · 56.9M deployments · 99.9% uptime · "Trusted by 1000+ companies" (logos include OpenAI, The Guardian, WP Engine, Intel, Duolingo, Red Hat).

### 3.2 Exact pricing

Source: [laravel.com/forge/pricing](https://laravel.com/forge/pricing)

| Plan | Monthly | Servers | Sites | Deployments | Support | DB backups | Health checks & heartbeats |
|---|---|---|---|---|---|---|---|
| **Hobby** | **$12/mo** | **1 external server** + *unlimited Laravel VPS servers* | Unlimited | Unlimited | Community | ✗ | ✗ |
| **Growth** | **$19/mo** | **Unlimited** (+5% Laravel VPS discount) | Unlimited | Unlimited | Standard / prioritized | ✅ | ✅ |
| **Business** | **$39/mo** | **Unlimited** (+15% Laravel VPS discount) | Unlimited | Unlimited | Advanced / high priority | ✅ | ✅ |
| **Enterprise** | Contact sales | — | — | — | Enterprise Support add-on | — | — |

**Gates on:** **external servers** (Hobby = 1; higher tiers unlimited), **support level**, **database backups**, **health checks/heartbeats**, and **team/role features**. Sites and deployments are unlimited on every tier.
**Annual pricing:** the page has a Monthly/Annual toggle but the annual figures did not render — **UNVERIFIED**.
**Free tier / trial:** none advertised on the pricing page — **UNVERIFIED**.
**API rate limit:** **60 requests/minute** per authenticated user, raisable on request ([forge.laravel.com/docs/api-reference/rate-limiting](https://forge.laravel.com/docs/api-reference/rate-limiting)).

**Explicit anti-usage-pricing stance (quote):** *"Is Forge usage-based pricing? **No.** Forge uses flat-rate monthly pricing. You only pay for your Forge subscription and whatever your cloud provider charges."*

**Laravel VPS:** Forge now sells its own VPS with instant provisioning ("under 10 seconds"), and the higher plans discount it (5% / 15%) — Forge is monetizing infrastructure, not just management. Includes an **integrated shared web terminal with SSH collaboration**.

**Envoyer folded in:** *"All new Laravel Forge subscriptions include zero-downtime deployments for a single server."* Envoyer remains for multi-server zero-downtime deploys; Forge has a migration tool but is **single-server only** for zero-downtime.

### 3.3 Exhaustive feature checklist

Sources: [laravel.com/forge](https://laravel.com/forge), [laravel.com/forge/pricing](https://laravel.com/forge/pricing), and the complete docs index at [forge.laravel.com/docs/llms.txt](https://forge.laravel.com/docs/llms.txt)

| Capability | Status | Detail |
|---|---|---|
| Server provisioning from blank VPS | ✅ Yes | Full stack: Nginx, PHP, MySQL/Postgres, Redis |
| Cloud provider integrations | ✅ Yes | DigitalOcean, AWS, Hetzner "and others" + **Laravel VPS** (own) + custom servers. Docs: "Server Providers" |
| One-click app installs | ⚠️ Partial | Deploys/supports Laravel, vanilla PHP, WordPress, Statamic, Nuxt, Next.js — via site creation, not an app-store marketplace |
| Git deployment + auto-deploy on push | ✅ Yes | GitHub, GitLab, Bitbucket ("Source Control" docs) |
| Custom deploy scripts | ✅ Yes | "Scriptable deployments"; **stacked and queued deployments**; deployment rollbacks (changelog) |
| Zero-downtime / atomic deploys | ✅ Yes | On **all** plans (single server) |
| Staging sites + clone/push-to-live | ❌ **No dedicated feature** | Users run staging as separate sites/servers (testimonial: "manage the production and staging versions of our site"). No clone/refresh/push-to-live product surface |
| PHP version management | ✅ Yes | Docs: "PHP — manage PHP versions" |
| Node / Python / Ruby | ⚠️ Partial | Node/Nuxt/Next supported; FAQ: non-PHP *"manually today, and natively in the future"*. Python/Ruby ❌ |
| SSL (Let's Encrypt / custom) | ✅ Yes | "Free SSL certificates", automated; docs "Domains — domains and SSL certificates". Wildcard **UNVERIFIED** |
| **DNS management** | ❌ **No** | No DNS docs section. Offers **hosted `on-forge.com` domains** instead so you can ship before DNS is set up |
| Database management | ✅ Yes | MySQL, Postgres, MariaDB; **Managed Databases** (fully managed clusters); **Managed Cache** clusters; Redis/Memcached |
| Email hosting/forwarding | ❌ No | Not in docs |
| Cron / scheduled jobs | ✅ Yes | "Scheduler" — predefined intervals or custom cron expressions, human-readable names; **Heartbeats** alert if a scheduled job is delayed |
| Queue/daemon workers (supervisor) | ✅ Yes | "Queues" + "Background Processes"; Supervisor-managed, auto-restart on crash, auto-start on reboot |
| Firewall management | ✅ Yes | UFW; docs "Network — server network and firewall"; per-site redirect + security rules |
| **Backups** | ⚠️ **Database only** | Docs: "**Database Backups**" + "Storage Providers … **for database backups**". **No file/site backup.** Gated to **Growth+** |
| Object storage | ✅ Yes | Create/manage **S3-compatible buckets** from Forge |
| Monitoring + alerting | ✅ Yes | Server monitoring (CPU/memory/disk/load/bandwidth charts) with **configurable alerts**; **Real-Time Metrics**; **Health checks** (post-deploy liveness ping); **Heartbeats**; Laravel Nightwatch integration |
| Log viewer | ✅ Yes | "Log access"; docs "Logs — understand and manage logs for your sites" |
| File manager | ❌ No | Not in docs |
| **Run arbitrary commands** | ✅ Yes | Docs "Commands — run arbitrary commands from the Commands panel"; plus **web terminal with shared SSH sessions** (Laravel VPS) |
| SSH key management | ✅ Yes | Docs "SSH Keys" |
| Team members + roles/permissions | ✅ Yes | **Organizations** + **Teams** + **role-based access** + **orgs as billable entities**. Sharing servers with teammates is on **all** plans; role-based access is tier-gated |
| White-label / agency branding | ❌ No | — |
| Client billing / reselling | ❌ No | Org-level billing separation only |
| **Marketplace / templates / recipes** | ✅ Yes | **Recipes** — "Save and run common Bash scripts across your servers"; **Nginx Templates** |
| WordPress-specific tooling | ⚠️ Partial | Deploys WordPress; no WP-specific management tooling |
| Site migration tools | ⚠️ Partial | Envoyer→Forge migration tool only |
| REST API | ✅ Yes | Full REST API + **OpenAPI spec** + filtering/sorting/pagination/relationships; 60 req/min |
| CLI | ✅ Yes | **Laravel Forge CLI** |
| SDK | ✅ Yes | **PHP SDK** |
| Load balancing | ✅ Yes | Horizontal scaling via load balancers |
| User isolation | ✅ Yes | Per-site isolation |
| Integrations | ✅ Yes | **Aikido** (security scanning), **Sentry** (error monitoring), **Envoyer**, **OpenClaw** ("Deploy OpenClaw AI agent servers on Laravel Forge" — i.e. *hosting* AI agents, not managing servers with AI) |
| **AI features / MCP** | ❌ **No first-party** | Nothing in the docs index. Community: [github.com/bretterer/forge-mcp-server](https://github.com/bretterer/forge-mcp-server). Note **Laravel Boost** and **Laravel MCP** ([laravel.com/ai/boost](https://laravel.com/ai/boost), [laravel.com/ai/mcp](https://laravel.com/ai/mcp)) are AI tooling for *writing Laravel apps* and *building* MCP servers — **not** for managing Forge infrastructure |
| Command palette | ✅ Yes | "⌘K anything" |

### 3.4 Praise and complaints

Forge has, by far, the **strongest sentiment in Group A** — the homepage carries ~25 named public testimonials with links. Representative:
- *"Forge is one of those services you couldn't pay me to leave."* — Alex MacArthur, Sr. Software Engineer at Ramsey ([x.com](https://x.com/amacarthur/status/1970145599497621704))
- *"Been using Forge to manage 60+ server instances for the past 10 years. Can't imagine using anything else."* — Herman Schutte, Founder of SiteSpeakAI
- *"It just works."* — John Koster, Razor Tracking
- Deployment speed: *"my deployment time went from 5-10 minutes to under 1 minute"* — Camilo Martinez

**Gaps rather than complaints** (structural, from the docs): no DNS management, no file manager, **no file backups (database only)**, no staging product, no white-label, no email, single-server-only zero-downtime deploys. Forge is deliberately narrow — a deployment platform, not a hosting control panel.

I did not find a substantial body of Forge complaints in the sources searched — **churn-reason evidence for Forge is UNVERIFIED/thin.** Note the pricing page is 100% vendor-curated testimonial, so treat the sentiment above as marketing-selected.

### 3.5 Notable

- **Envoyer absorbed** into Forge (zero-downtime now included) — a consolidation move that removed a $10/mo upsell.
- **Laravel VPS** — Forge now sells the infrastructure itself, with plan-tier discounts. This is a margin/lock-in strategy the others don't have.
- **Laravel Cloud** is the sibling serverless product; Forge is explicitly positioned for those who *"want full control over your servers"* ([laravel.com/forge/forge-vs-cloud](https://laravel.com/forge/forge-vs-cloud)).
- Forge is the **price-per-server leader by a mile**: unlimited servers at $19/mo vs RunCloud's 50 at $19 and Ploi's 10 at €13.

---

## 4. SPINUPWP

### 4.1 Positioning & buyer

**One-liner:** A modern cloud server control panel purpose-built to **host WordPress** on your own VPS, "lightning fast".
**Buyer:** WordPress developers and agencies who want self-hosted WP without managed-WP-host prices. Built by **Delicious Brains** (WP Migrate DB Pro, WP Offload Media).
**Scope:** narrowest of the six — WordPress-first by design.

### 4.2 Exact pricing

Source: [spinupwp.com/pricing/](https://spinupwp.com/pricing/)

| Plan | Monthly | Servers | Sites | Users | Backups | Site monitoring | Support |
|---|---|---|---|---|---|---|---|
| **Essentials** | **$12/mo** | 1 included; **"As low as $1 / mo per additional server"** | Unlimited | **Single user only** (additional users **not available**) | "1 daily scheduled snapshot per site" | ✗ Not included | Standard email |
| **Advanced** | **$19/mo** | 1 included; same add-on pricing | Unlimited | 1 included; **"$2 / mo per user"** additional | "Up to 4 daily, 4 weekly, 4 monthly scheduled snapshots per site" | **"$1/month per site monitor"** | Priority email |

**Gates on:** **servers (metered add-on)** + **users (metered add-on)** + **backup retention depth** + **site monitoring (metered per site)**. Sites are unlimited.
**Volume discount:** additional servers scale down to **$1/mo/server at 61+ servers** on both tiers.
**Free trial:** **7-day free trial, no credit card required** (trial includes Essentials features).
**Annual pricing:** **UNVERIFIED** — not surfaced.
**API rate limits:** **UNVERIFIED** — the developer docs point to api.spinupwp.com for specs.

> **This is the only genuinely metered pricing in Group A** (per-server + per-user + per-site-monitor add-ons on a low base). It's cheap for 1–3 servers/1 user and grows linearly. Note **Essentials is hard-locked to a single user** — an agency with two staff must take Advanced.

### 4.3 Exhaustive feature checklist

Sources: [spinupwp.com](https://spinupwp.com/), [spinupwp.com/pricing](https://spinupwp.com/pricing/), [spinupwp.com/docs/](https://spinupwp.com/docs/), doc sitemap ([spinupwp.com/doc-sitemap.xml](https://spinupwp.com/doc-sitemap.xml)), [spinupwp.com/doc/account-user-roles](https://spinupwp.com/doc/account-user-roles/), [spinupwp.com/doc/understanding-dns](https://spinupwp.com/doc/understanding-dns/), [spinupwp.com/doc/assistant](https://spinupwp.com/doc/assistant/)

| Capability | Status | Detail |
|---|---|---|
| Server provisioning from blank VPS | ✅ Yes | Full root access, "no vendor lock-in" |
| Cloud provider integrations | ✅ Yes | **DigitalOcean, AWS (EC2/Lightsail), Google Cloud, Vultr, Hetzner, Akamai/Linode** |
| One-click app installs | ⚠️ WordPress only | Automated WP install + SSL; **WP multisite** (subdomain/subdirectory). Docs: "installing-other-web-apps" (manual) |
| Git deployment + auto-deploy on push | ✅ Yes | **Push-to-deploy**; GitHub, Bitbucket, custom git. Docs: `git`, `git-deploy-keys`, `configuring-push-to-deploy`, `adding-ssh-key-git-provider` |
| Custom deploy scripts | ✅ Yes | Deployment scripts (part of push-to-deploy) |
| Zero-downtime / atomic deploys | ❌ **No** | Not advertised — a real gap vs Ploi/RunCloud/Forge |
| **Staging + clone/push-to-live** | ✅ **Yes — best in group** | Docs: `staging-sites`, `clone-site` (to same **or different** server), `move-site`, **`refresh-site`**. "Unlimited" staging on both plans |
| PHP version management | ✅ Yes | Multiple PHP versions per server; `remove-php-version`, `how-to-change-php-settings`, `understanding-php-pools` |
| Node / Python / Ruby | ❌ No | WordPress/PHP only |
| SSL (Let's Encrypt / custom) | ✅ Yes | Free Let's Encrypt; `custom-https-certificate`; `common-reasons-certificate-renewals-fail` |
| **DNS management** | ❌ **Explicitly No** | Direct quote: *"It's important to note that **SpinupWP does not manage the DNS for your domains**. Therefore, you should have a good understanding of how to manage the DNS for your domains before using SpinupWP."* It tells you which records to add |
| Database management | ✅ Yes | `connecting-database`, **`phpmyadmin`**, **`external-databases`** (Advanced plan; DO/Vultr/Akamai/Lightsail managed DBs) |
| Email hosting/forwarding | ❌ **No** | Docs instead cover `setting-up-transactional-email-wordpress` — i.e. use a third-party service |
| Cron / scheduled jobs | ✅ Yes | Auto-configured WP cron; `add-cron-jobs`, `managing-active-cron-jobs`, `understanding-wp-cron` |
| Queue/daemon workers | ❌ No | Not applicable to WP-only scope |
| Firewall management | ✅ Yes | "Blocks all except HTTP/HTTPS/SSH"; **Fail2Ban** (`how-to-unban-and-whitelist-ip-addresses-in-fail2ban`); `whitelisting-ip-addresses` |
| **Backups** | ✅ **Yes — strongest destination list** | Files **and** database; scheduled + on-demand; **full server backup restore** (`restore-full-server-backup`, `restoring-backups`). Destinations: **Amazon S3, DigitalOcean Spaces, Google Cloud Storage, Backblaze B2, Wasabi, Cloudflare R2, Akamai, Vultr, Hetzner, SFTP**. Retention by plan (1 daily vs 4 daily/4 weekly/4 monthly) |
| Monitoring + alerting | ✅ Yes | **Server monitoring** included; **site (uptime) monitoring $1/mo per monitor on Advanced only**; New Relic integration doc |
| Log viewer | ✅ Yes | "Integrated logs", error log viewer, `wordpress-debug-log` |
| File manager | ❌ No | SFTP/SSH instead (`using-sftp-to-connect-to-your-spinupwp-servers`) |
| SSH key management | ✅ Yes | `how-to-ssh-keys`; **client SFTP/SSH access to individual sites**; `understanding-system-users`, `passwordless-sudo` |
| **Team members + roles** | ✅ Yes — 4 roles | **Site Admin** (create/update/delete sites, databases + DB users, add own SSH keys) → **Server Admin** (+ update servers, manage sudo users & SSH keys, server settings, restart server/services) → **Account Admin** (+ create/delete servers, providers, external DBs, account settings, invite users, manage roles & server access) → **Owner** (+ billing). **Access is granted per-SERVER, not per-site** |
| White-label / agency branding | ⚠️ Partial | `custom-spinupwp-dashboard` doc exists (build your own dashboard on the API). No turnkey white-label — **UNVERIFIED** |
| Client billing / reselling | ❌ No | — |
| Marketplace / recipes | ❌ No | — |
| **WordPress-specific tooling** | ✅ **Yes — best in group** | **WP-CLI pre-installed**; **WordPress Magic Login** (one-click admin access); plugin/theme **update management from the dashboard**; **Redis object caching**; **full-page caching** with preconfigured rules + `customizing-page-cache-exclusions`, `page-cache-key`, `cache-daemon`; browser caching; `woocommerce-performance-optimizations`; `wordpress-file-ownership-permissions`; `updating-wordpress-core-themes-plugins`; Composer support |
| Site migration tools | ✅ Yes | `site-migration-guide`, `move-site`; `how-to-install-wordpress-on-{aws-ec2,hetzner,vultr,any-provider}` |
| REST API | ✅ Yes | *"With the REST API you can spin up servers and create and manage sites remotely"* — on **all** plans; docs at api.spinupwp.com |
| SDK | ✅ Yes | **PHP SDK** ([github.com/spinupwp/spinupwp-php-sdk](https://github.com/spinupwp/spinupwp-php-sdk)) |
| CLI | ✅ Yes | `spinupwp/spinupwp-cli` via Composer |
| Mobile app | ❌ Not found | — |
| **AI features / MCP** | ❌ **No** | The **"Assistant"** is **not AI** — it's a deterministic maintenance engine: *"identifies maintenance tasks, or 'todos' … prioritizes them, and when something is urgent, alerts you"* (disk space, software updates, PHP/Ubuntu EOL, WP updates), color-coded Critical/High/Medium/Low, in-app notifications at High, optional weekly/monthly email digest of the top 20 todos. Community MCP only: [github.com/farukgaric/spinupwp-mcp](https://github.com/farukgaric/spinupwp-mcp) (4 tools: list_servers, get_server, reboot_server, restart_service) |
| Notable non-support | — | Docs page: `why-we-dont-offer-openlitespeed` — deliberate Nginx-only stance |

### 4.4 Praise and complaints

**Praise:** Cost-effectiveness vs managed WP hosts; UX; caching performance; the staging/clone workflow.

**Complaints** (Trustpilot / Capterra / G2 / Software Advice — relayed via search summaries, **indicative not verbatim-verified**):
- **Stability/bugs:** *"The idea is great, the UX is great, the features are... well, buggy, and it's a beautiful alpha with a long way to go before it's stable."* And a pointed cost warning: *"bugs can cost you a fortune, so take that into account when you look at that slightly more expensive competitor."*
- **Feature depth:** *"not as feature rich as some other competitors"*; *"limited features … particularly around instance management and required SSH adjustments"* — e.g. *"adjusting the memory level for each instance … must be done via SSH."*
- **Access control — the clearest product gap:** *"backup access limitations that prevent client-specific roles and complicate onboarding of new sites"*; *"lack of site-specific access roles for clients."* This matches the docs exactly: **roles grant access per server, not per site** — so an agency cannot give a client access to only their own site on a shared server.
- **Support:** *"Support is so-so and quite slow"*; unresolved issues causing setup frustration.

Sources: [trustpilot.com/review/spinupwp.com](https://www.trustpilot.com/review/spinupwp.com), [capterra.com/p/10012241/SpinupWP/reviews/](https://www.capterra.com/p/10012241/SpinupWP/reviews/), [g2.com/products/spinupwp/reviews](https://www.g2.com/products/spinupwp/reviews)

### 4.5 Notable

- **Metered per-user pricing is a churn tax on agencies** ($2/user/mo, and Essentials permits no second user at all) — combined with the missing per-site client roles, SpinupWP is structurally weak for agencies serving end clients.
- **No zero-downtime deploys** and **no DNS** are the two clearest feature holes.
- Backup destination breadth (10 providers incl. Cloudflare R2 and plain SFTP) is best-in-group.

---

## 5. SERVERPILOT

### 5.1 Positioning & buyer

**One-liner:** Simple control panel to run PHP/WordPress apps on your own cloud server, priced hourly per server **and per app**.
**Buyer:** Cost-sensitive solo devs and small hosts running a handful of PHP/WP apps. The oldest and simplest product in the group.
**Company size:** 5 employees as of 2024-12-31 ([Tracxn](https://tracxn.com/d/companies/serverpilot/__e5K7xvWWjgQt3oFH_M61Z9QtkxFwcB8Ytf1ePI9uVPU)) — **UNVERIFIED** for 2026.

### 5.2 Exact pricing

Source: [serverpilot.io/pricing/](https://serverpilot.io/pricing/)

**Structure: hourly billing, no subscription. Charged PER SERVER *plus* PER APP.**

| Plan | Per server / month | Per app / month | Adds |
|---|---|---|---|
| **Economy** | **$5** | **$0.50** | Base: SSL, firewall, WordPress installer. Monitoring features **locked** |
| **Business** | **$10** | **$1.00** | **Log viewer**, **server resource metrics**, **PHP process metrics**; priority support |
| **First Class** | **$20** | **$2.00** | **App request and error metrics**, **MySQL health and cache metrics**; high-priority support |

**Gates on:** **servers AND apps** (the only per-app pricing in Group A) + **monitoring/observability depth** + support priority.
**No explicit server or app caps.**
**Free trial:** *"We have a 14-day trial period that begins when you sign up. No credit card is required."* — the **longest trial in the group**.
**Annual pricing:** none (hourly billing).
**Currency:** USD assumed, not explicitly stated on the page.

> **Cost trap for agencies:** 1 server + 30 WordPress sites on Business = $10 + 30×$1 = **$40/mo**. The same workload on Forge Growth is $19/mo flat, on Ploi Basic €8. RunCloud markets directly against this: *"no per-site charges"*, *"no per-app costs"*.

### 5.3 Exhaustive feature checklist

Sources: [serverpilot.io/features/](https://serverpilot.io/features/), [serverpilot.io/docs/](https://serverpilot.io/docs/), [serverpilot.io/blog/](https://serverpilot.io/blog/)

| Capability | Status | Detail |
|---|---|---|
| Server provisioning from blank VPS | ✅ Yes | Connect any Ubuntu server; "full root access"; server resizing |
| Cloud provider integrations | ⚠️ Partial | *"Use any cloud provider"*; explicit integration with **Google Cloud and DigitalOcean** only |
| One-click app installs | ⚠️ WordPress only | *"One-click WordPress"*; otherwise *"Run apps in any language"* generically |
| **Git deployment + auto-deploy** | ❌ **No built-in** | Git is installed, but there is **no deployment UI for external repos**. Docs offer a **GitHub Actions** guide ([serverpilot.io/docs/guides/apps/deploy/](https://serverpilot.io/docs/guides/apps/deploy/)). Third-party review: *"ServerPilot lacks Git deployment"* ([SitePoint](https://www.sitepoint.com/lets-compare-runcloud-vs-forge-vs-serverpilot/)) |
| Custom deploy scripts | ❌ No | — |
| Zero-downtime / atomic deploys | ❌ No | — |
| **Staging sites + clone** | ❌ **No** | *"ServerPilot lacks staging environments and easy server/application cloning"* (SitePoint). Partly addressed by **ServerPilot Migrations** (Dec 2025) |
| PHP version management | ✅ Yes | Multiple PHP versions on the same server, auto-installed. **PHP 8.5 available Oct 2025** |
| Node / Python / Ruby | ⚠️ Claimed | "Run apps in any language" — but tooling is PHP-centric; **UNVERIFIED** |
| SSL | ✅ Yes | **"AutoSSL"** — automatic Let's Encrypt deployment; TLS 1.3 |
| DNS management | ⚠️ Partial | Features page lists *"DNS management (Google Cloud and DigitalOcean)"*; docs list "Manage DNS" under **Cloud providers** — i.e. it operates the provider's DNS, not its own zone editor. Depth **UNVERIFIED** |
| Database management | ✅ Yes | MySQL; **remote access** guide; MySQL slow-query monitoring; database migration |
| **Email** | ⚠️ Partial | Docs have a dedicated **"Email" guides section** — mail queues, relay services, hosting. This is **guidance**, not a mailbox management product |
| Cron / scheduled jobs | ⚠️ Partial | "Schedule cron jobs" **guide** + cron job **logs**. A third-party review says ServerPilot is *"missing Git deployment and scheduling capabilities"* as first-class features |
| Queue/daemon workers | ❌ Not found | — |
| Firewall | ✅ Yes | iptables, blocks private service traffic |
| App isolation | ✅ Yes | Separate system users per app |
| **Backups** | ⚠️ Partial | Docs: "Snapshots and backups" under **Cloud providers** — i.e. provider snapshots, not a ServerPilot backup product. **No first-party scheduled app/DB backup found — UNVERIFIED but likely absent** |
| Monitoring + alerting | ⚠️ Partial | Metrics dashboards for CPU/memory/disk; per-app request + error rates; MySQL health/cache — **all tier-gated**. **Alerting channels not advertised** — the features page says nothing about alerts |
| **Log viewer** | ✅ Yes | *"Quickly view and search server and app log files"* — **Business tier+** |
| File manager | ❌ No | — |
| SSH / SFTP / FTP users | ✅ Yes | Extensive docs section; SSH key auth |
| Team members + roles | ❌ **No** | No team management documentation found |
| White-label / agency branding | ❌ No | — |
| Client billing / reselling | ❌ No | — |
| Marketplace / recipes | ❌ No | — |
| WordPress tooling | ⚠️ Partial | One-click installer only; no WP-CLI/cache/update management surface |
| **Site migration tools** | ✅ Yes | **ServerPilot Migrations** (announced **Dec 15, 2025**) — transfer files and databases between servers or between apps on the same server. Also **DataShuttle** (separate external service) |
| REST API | ✅ Yes | API v1 ([github.com/ServerPilot/API](https://github.com/ServerPilot/API)); docs "API Overview" + third-party libraries. Rate limits **UNVERIFIED** |
| CLI | ❌ Not found | — |
| Mobile app | ❌ Not found | — |
| **AI features / MCP** | ❌ **No** | Nothing found. ⚠️ Beware: an **unrelated open-source project** named "serverpilot" ([github.com/jingyus/serverpilot](https://github.com/jingyus/serverpilot)) is an AI server-management platform with *no connection to ServerPilot.io* |
| Web server stack | ✅ Yes | Nginx front (HTTP/3, HTTP/2) + Apache internally for `.htaccess` compatibility; PHP-FPM auto-scaling |

### 5.4 Is ServerPilot declining?

**Mixed — the "abandoned" narrative is wrong, but the "stagnant" one is partly right.**

**Still actively maintained** ([serverpilot.io/blog/](https://serverpilot.io/blog/)):
- 2026-05-08 — Linux kernel "Dirty Frag" vulnerability mitigation
- 2026-05-03 — Linux kernel "Copy Fail" vulnerability mitigation
- 2026-04-28 — **Ubuntu 26.04 LTS support**
- 2025-12-15 — **ServerPilot Migrations** (new feature)
- 2025-10-22 — PHP 8.5

**But feature velocity is low.** In ~19 months the only *new capability* was Migrations; everything else is OS/PHP/CVE maintenance. Third-party framing: *"development has slowed, and users are looking for alternatives with active development and better features"* ([ctrlops.io](https://ctrlops.io/blog/putty-webmin-serverpilot-alternatives)); *"ServerPilot underperformed in both features and performance, with its web panel interface lacking many features"* ([SitePoint](https://www.sitepoint.com/lets-compare-runcloud-vs-forge-vs-serverpilot/)).

**Churn drivers:** no git deploy, no staging/cloning, no team management, per-app pricing that punishes agencies, and monitoring locked behind higher tiers.

---

## 6. MOSS (moss.sh) — ⚠️ DEFUNCT

### 6.1 Verdict

**Moss is dead. Do not treat it as a live competitor.** The domain has been out of the original owner's hands since 2025 and resolves to nothing today.

### 6.2 Evidence (checked directly, 2026-07-25)

| Check | Result |
|---|---|
| `dig @8.8.8.8 moss.sh` | **SERVFAIL** (also `www.` and `app.`) |
| `dig @1.1.1.1 moss.sh` | **SERVFAIL** |
| `curl https://moss.sh/` | `Could not resolve host` |
| WHOIS **original** creation | `created: 1997-09-23` |
| WHOIS **current** creation date | **`2025-09-27T15:15:38Z`** ← the domain **dropped and was re-registered** |
| WHOIS registrar | **`Backordr LLC`** (IANA 801502) — a domain **backorder / drop-catch** service |
| WHOIS expiry | `2026-09-27` |
| Nameservers | `ns9/ns10.nlkoddos.com` — the parent NS resolves (31.220.2.150) but the `moss.sh` zone itself returns SERVFAIL |

**Wayback Machine timeline** ([CDX API](http://web.archive.org/cdx/search/cdx?url=moss.sh)):

| Date | State |
|---|---|
| … through **2025-05-26** | ✅ Real Moss product site, footer: **"©2024 Doalitic S.L. All rights reserved. Designed in Murcia by Drool Studio."** |
| **2025-07-27** | 🅿️ Bare parked page: *"moss.sh · 2025 Copyright \| All Rights Reserved. Privacy Policy"* |
| **2025-09-27** | Domain re-registered via Backordr LLC |
| **2025-10-01 → 2026-03-07** | 👻 A **WordPress rebuild that copies Moss's original marketing copy** (`datePublished: 2025-09-29`, wp-block/wp-emoji assets, nav changed to "Reviews"). Not the real product |
| **2026-03-22 onward** | ❌ Capture failed; DNS dead ever since |

> ⚠️ **Trap for anyone researching this vendor:** search engines still return moss.sh pages (e.g. a blog post "Server Downtime: Causes and Solutions", a SaaSHub "not shutting down after all" item from **2020**) and summarize them as if Moss were operating. The 2020 "Moss is saved / acquired by a UK company" story is real but **five years stale**; the current moss.sh content is squatter content on a re-registered domain. Any "Sign up / Log in" on that site should be treated as untrusted.

### 6.3 What Moss was (historical — for pricing-model reference only)

Operator: **Doalitic S.L.**, Murcia, Spain. Positioning: *"Hi there! I'm Moss — **The virtual sysadmin for web developers**."* Targeted freelancers, agencies and startups; PHP, Node.js and static sites on Ubuntu.

**Historical pricing** (archived [moss.sh/pricing](http://web.archive.org/web/20240521104924/https://moss.sh/pricing/), 2024) — **and it is the most interesting pricing model in Group A:**

> *"All plans include **unlimited servers, sites, and teammates**"*

| Plan | Price | Integrations | Git deploys | Support |
|---|---|---|---|---|
| **Free** | $0/mo | 1 | **25/mo** | Help Center |
| **Starter** | $9/mo | 2 | **50/mo** | Help Center |
| **Professional** | $19/mo | 3 | **150/mo** | Basic Support |
| **Unlimited** | $49/mo | ∞ | ∞ | Prio Support |

Plus a **Monitoring add-on: "$5 server / month*"** — *"\*Maximum cost per server / month. Service billed hourly."*

**Moss gated on INTEGRATIONS and GIT DEPLOYS — not servers, sites or users.** An "integration" = a linked third-party account (AWS EC2, DigitalOcean, Google Cloud, Slack, Vultr); linked *git* providers explicitly did **not** count.

**Features:** unlimited servers/sites/users, zero-downtime deployments, GitLab/GitHub/Bitbucket/custom git, automatic security updates, databases, cron jobs, workers, firewall, monitoring + Slack/email alerts, HTTP/2 + OCSP stapling, SSH/SFTP + user permissions, teammate roles that *"won't have permission to mess with system configs"*, and **workspaces** to organize servers/sites/teammates per client or environment.

**Read-across for ServerAlly:** Moss is a cautionary data point — it chose a usage-shaped metric (deploys) that the rest of the market rejected, priced servers at zero, and did not survive. It reinforces the [PRICING-V3](../PRICING-V3.md) conclusion that **servers are the metric the market accepts**, and that a usage-shaped meter is the risky path.

---

## 7. Cross-vendor comparison

### 7.1 Pricing — what each tier actually gates on

| Vendor | Entry | Mid | Top | **Gating metric** | Trial |
|---|---|---|---|---|---|
| **Ploi** | Free (1 server/1 site/5 deploys) · **Basic €8** (5 servers) | **Pro €13** (10 servers) | **Unlimited €30** | **Servers** + API rate + hard feature gates (backups/monitoring/zero-downtime = Pro; teams = Unlimited) | 5-day (Pro) |
| **RunCloud** | **Essentials $9** (1 server) | **Professional $19** (50 servers) · **Business $49** (100) | **Enterprise $399** (500) | **Servers** + backup storage GB + staging count + team seats + **API access ($49+)** | 5-day |
| **Forge** | **Hobby $12** (1 external server) | **Growth $19** (unlimited) | **Business $39** (unlimited) · Enterprise: contact | **External servers** + support level + DB backups + health checks. *Sites/deploys unlimited everywhere* | UNVERIFIED |
| **SpinupWP** | **Essentials $12** (1 server + $1/extra, **1 user max**) | **Advanced $19** (+$2/user, +$1/site monitor) | — | **Servers, users AND site monitors — all metered add-ons** + backup retention | **7-day** |
| **ServerPilot** | **Economy $5/server + $0.50/app** | **Business $10 + $1/app** | **First Class $20 + $2/app** | **Servers × apps** + observability depth | **14-day** |
| **Moss** *(defunct)* | Free (25 deploys) · $9 | $19 | $49 | **Integrations + git deploys** (servers/sites/users unlimited) | n/a |

**Median "agency-shaped" plan (5–10 servers, unlimited sites, 1 user): ~$19/mo.** Four of five live vendors land within $12–$19 for that shape. **$19 is the market anchor.**

### 7.2 Feature comparison matrix

Legend: ✅ yes · ⚠️ partial/conditional · ❌ no · ❔ UNVERIFIED · **(P)** = requires a higher paid tier

| Feature | Ploi | RunCloud | Forge | SpinupWP | ServerPilot | Moss† |
|---|:--:|:--:|:--:|:--:|:--:|:--:|
| Provision from blank VPS | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cloud provider integrations | ✅ 8+ | ✅ | ✅ +own VPS | ✅ 6 | ⚠️ GCP/DO | ✅ 4 |
| One-click app installs | ✅ 7 apps | ✅ | ⚠️ | ⚠️ WP only | ⚠️ WP only | ⚠️ |
| Git deploy + auto-deploy on push | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ |
| Custom deploy scripts | ✅ **(P)** | ✅ | ✅ | ✅ | ❌ | ✅ |
| Zero-downtime / atomic deploys | ✅ **(P Pro)** | ✅ **(P $49)** | ✅ all tiers | ❌ | ❌ | ✅ all tiers |
| Staging + clone/push-to-live | ⚠️ | ✅ **(P)** | ❌ | ✅ **best** | ❌ | ❔ |
| PHP version management | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Node support | ✅ | ⚠️ | ⚠️ | ❌ | ⚠️ | ✅ |
| Python / Ruby | ❔ | ❔ | ❌ | ❌ | ❔ | ❌ |
| SSL Let's Encrypt | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Wildcard / custom SSL | ❔ | ✅ **both** | ❔ | ⚠️ custom | ❔ | ❔ |
| **DNS management** | ✅ Cloudflare | ✅ Cloudflare **(P)** | ❌ | ❌ **explicit** | ⚠️ via provider | ❌ |
| Database management | ✅ | ✅ | ✅ +managed clusters | ✅ +phpMyAdmin | ✅ +remote | ✅ |
| **Email hosting/forwarding** | ⚠️ server type | ❌ | ❌ | ❌ | ⚠️ guides | ❌ |
| Cron / scheduled jobs | ✅ | ✅ | ✅ +heartbeats | ✅ | ⚠️ | ✅ |
| Queue/daemon workers | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ |
| Firewall | ✅ **(P)** | ✅ +WAF **(P)** | ✅ UFW | ✅ +Fail2Ban | ✅ | ✅ |
| **Backups — files** | ✅ **(P)** | ✅ | ❌ | ✅ | ⚠️ | ❔ |
| **Backups — database** | ✅ **(P)** | ✅ | ✅ **(P)** | ✅ | ⚠️ | ❔ |
| Offsite/S3 destinations | ✅ 3 | ✅ many | ✅ | ✅ **10** | ⚠️ | ❔ |
| Restore | ❔ | ✅ **to any server** | ❔ | ✅ **full server** | ❔ | ❔ |
| Monitoring CPU/RAM/disk | ✅ **(P)** | ✅ | ✅ | ✅ | ⚠️ **(P)** | ✅ add-on |
| **Alert channels** | ✅ email/Slack/Discord/Telegram | ❔ | ✅ | ✅ | ❌ | ✅ Slack/email |
| Uptime / site monitoring | ✅ **(P Unlim)** | ❔ | ✅ health checks | ⚠️ **$1/monitor** | ❌ | ✅ add-on |
| Log viewer | ✅ | ❔ | ✅ | ✅ | ✅ **(P)** | ❔ |
| **File manager** | ✅ **(P)** | ❔ | ❌ | ❌ | ❌ | ❌ |
| Run arbitrary commands / web terminal | ✅ script access | ❔ | ✅ **both** | ❌ | ❌ | ❔ |
| SSH key management | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Team members + roles** | ✅ **(P €30)** | ✅ **(P $49)** | ✅ orgs+RBAC | ✅ **4 roles** (per-server) | ❌ | ✅ all tiers |
| **White-label** | ✅ **Ploi Core** | ❌ | ❌ | ⚠️ custom dash | ❌ | ❌ |
| **Client billing / reselling** | ✅ **Stripe (Core)** | ❌ | ❌ | ❌ | ❌ | ❌ |
| Marketplace / recipes / templates | ✅ | ❔ | ✅ **Recipes + Nginx templates** | ❌ | ❌ | ❌ |
| WordPress-specific tooling | ⚠️ | ✅ **Hub** | ⚠️ | ✅ **best** | ⚠️ | ⚠️ |
| Site migration tools | ⚠️ | ✅ | ⚠️ Envoyer only | ✅ | ✅ **Migrations** | ❔ |
| REST API | ✅ (not Free) | ✅ **(P $49)** | ✅ +OpenAPI | ✅ all plans | ✅ | ❔ |
| API rate limit published | ✅ 60/120/240 | ❔ | ✅ 60/min | ❔ | ❔ | ❔ |
| CLI | ❔ | ❔ | ✅ | ✅ | ❌ | ❔ |
| SDK | ❔ | ❔ | ✅ PHP | ✅ PHP | ⚠️ 3rd-party | ❔ |
| Mobile app | ✅ | ✅ iOS | ❌ | ❌ | ❌ | ❌ |
| Load balancing | ✅ | ❔ | ✅ | ❌ | ❌ | ❌ |
| Docker / containers | ✅ server type | ✅ | ❌ | ❌ | ❌ | ❌ |
| **First-party MCP server** | ✅ **60 tools, OAuth, Pro+** | ❌ (community) | ❌ (community) | ❌ (community) | ❌ | ❌ |
| **First-party AI reasoning/agent** | ❌ | ❌ | ❌ | ❌ *(Assistant ≠ AI)* | ❌ | ❌ |
| Windows Server support | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Hosting-panel (cPanel/CyberPanel) mgmt | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

† Moss row = historical (defunct).

### 7.3 Where the whole group is weak — ServerAlly's openings

1. **No AI reasoning anywhere.** Ploi's MCP is an API adapter; the customer's AI does all thinking. Nobody diagnoses, remediates, explains in plain language, or runs multi-step missions. SpinupWP's "Assistant" is a rules-based todo list.
2. **All six are Linux+PHP only.** Zero Windows Server, zero hosting-panel management (cPanel/CyberPanel/Plesk), zero non-technical-user positioning. Every product assumes the buyer already knows sysadmin.
3. **Security is a checkbox, not a product.** Firewall + Fail2Ban + SSL is the ceiling. No threat detection, no malware/IOC scanning, no incident response, no security grading. **RunCloud's WooCommerce data-leak complaint shows the market has an unmet security-trust need.**
4. **File backups are patchy.** Forge is **database-only**. ServerPilot leans on provider snapshots. Only SpinupWP and RunCloud do full file+DB backup well.
5. **DNS is missing from Forge and SpinupWP entirely**, and gated to $49 on RunCloud.
6. **Agency/client tooling is thin except Ploi.** Only Ploi (via Ploi Core) offers white-label + client billing. SpinupWP's inability to give per-*site* client roles is an explicitly-complained-about gap.
7. **Support is the universal weak point** — the #1 complaint for RunCloud, Ploi and SpinupWP alike. An AI that resolves issues without a support ticket attacks the exact pain that drives churn in this category.
8. **Nobody meters usage** — which validates ServerAlly's per-server Layer 1, and means a usage-shaped meter would be an unfamiliar (and, per Moss, historically unsuccessful) ask.

### 7.4 Pricing read-across for ServerAlly

- **$19/mo is the anchor** for the agency-shaped plan across four of five live vendors.
- **Server counts at ~$19:** Forge **unlimited** · RunCloud **50** · Ploi **10** · SpinupWP **1 + $1/extra**. ServerAlly's Pro at 15 servers sits **below the median**; Forge and RunCloud both beat it decisively at the same price.
- **API rate limits published in the plan table are normal and uncontroversial** (Ploi 60/120/240, Forge 60/min). This is the precedent for how an AI request limit should read — a guardrail line in the table, not a billed unit.
- **Gating core safety features behind higher tiers generates the loudest complaints** (Ploi: backups+monitoring are Pro-only; RunCloud: API is $49-only). ServerAlly's "open features, two meters" decision avoids this failure mode.
- **Per-app pricing (ServerPilot) is actively used against them** by a competitor in that competitor's own marketing. Avoid per-site/per-app metrics.

---

## 8. Source index

**Ploi:** [pricing](https://ploi.io/pricing) · [features](https://ploi.io/features) · [homepage](https://ploi.io/) · [MCP](https://ploi.io/features/mcp) · [whitelabel](https://ploi.io/whitelabel) · [Ploi Core](https://ploi-core.io/) · [Ploi Cloud AI](https://ploi.cloud/features/ai) · [Trustpilot](https://www.trustpilot.com/review/ploi.io) · [LowEndTalk](https://lowendtalk.com/discussion/202240/enhance-vs-runcloud-vs-serveravatar-vs-ploi)

**RunCloud:** [pricing](https://runcloud.io/pricing) · [features](https://runcloud.io/features) · [backup](https://runcloud.io/backup) · [limits & usage docs](https://runcloud.io/docs/runcloud-limits-usage) · [DNS manager docs](https://runcloud.io/docs/category/dns-manager) · [Hub + Cloudflare docs](https://runcloud.io/docs/runcloud-hub-integration-with-cloudflare) · [blog: cPanel alternatives (pricing)](https://runcloud.io/blog/cpanel-alternatives) · [blog: Node.js hosting (pricing)](https://runcloud.io/blog/best-node-js-hosting) · [Trustpilot](https://www.trustpilot.com/review/runcloud.io) · [community MCP](https://github.com/aleksanderem/runcloud-mcp)

**Forge:** [pricing](https://laravel.com/forge/pricing) · [homepage/features](https://laravel.com/forge) · [full docs index (llms.txt)](https://forge.laravel.com/docs/llms.txt) · [API rate limiting](https://forge.laravel.com/docs/api-reference/rate-limiting) · [Recipes](https://forge.laravel.com/docs/recipes.md) · [Database Backups](https://forge.laravel.com/docs/resources/database-backups.md) · [Teams](https://forge.laravel.com/docs/teams.md) · [community MCP](https://github.com/bretterer/forge-mcp-server) · [Laravel Boost](https://laravel.com/ai/boost) · [Laravel MCP](https://laravel.com/ai/mcp)

**SpinupWP:** [pricing](https://spinupwp.com/pricing/) · [homepage](https://spinupwp.com/) · [docs](https://spinupwp.com/docs/) · [doc sitemap](https://spinupwp.com/doc-sitemap.xml) · [user roles](https://spinupwp.com/doc/account-user-roles/) · [understanding DNS](https://spinupwp.com/doc/understanding-dns/) · [Assistant](https://spinupwp.com/doc/assistant/) · [developers](https://spinupwp.com/docs/developers/) · [teams](https://spinupwp.com/docs/teams/) · [Trustpilot](https://www.trustpilot.com/review/spinupwp.com) · [Capterra](https://www.capterra.com/p/10012241/SpinupWP/reviews/) · [community MCP](https://github.com/farukgaric/spinupwp-mcp)

**ServerPilot:** [pricing](https://serverpilot.io/pricing/) · [features](https://serverpilot.io/features/) · [docs](https://serverpilot.io/docs/) · [blog](https://serverpilot.io/blog/) · [deploy guide](https://serverpilot.io/docs/guides/apps/deploy/) · [API](https://github.com/ServerPilot/API) · [SitePoint comparison](https://www.sitepoint.com/lets-compare-runcloud-vs-forge-vs-serverpilot/) · [ctrlops alternatives](https://ctrlops.io/blog/putty-webmin-serverpilot-alternatives) · [Tracxn profile](https://tracxn.com/d/companies/serverpilot/__e5K7xvWWjgQt3oFH_M61Z9QtkxFwcB8Ytf1ePI9uVPU)

**Moss:** live DNS/WHOIS checks 2026-07-25 · [archived homepage 2024](http://web.archive.org/web/20240521104924/https://moss.sh/) · [archived pricing 2024](http://web.archive.org/web/20240521104924/https://moss.sh/pricing/) · [archived features 2024](http://web.archive.org/web/20240521104924/https://moss.sh/features/) · [parked page 2025-07](http://web.archive.org/web/20250727195754/https://moss.sh/) · [squat site 2026-03](http://web.archive.org/web/20260307122740/https://moss.sh/) · [Wayback CDX](http://web.archive.org/cdx/search/cdx?url=moss.sh)

---

## 9. Confidence notes / what remains UNVERIFIED

| Item | Status |
|---|---|
| RunCloud exact prices | From **RunCloud's own blog**, not the pricing page (Paddle JS-rendered). Plan **names** confirmed on the live page. Cross-checked across 2 RunCloud articles + 2 third parties |
| RunCloud annual pricing | **UNVERIFIED** |
| RunCloud per-plan API rate limits | **UNVERIFIED** (docs confirm limits scale with plan; numbers unpublished) |
| Forge annual prices | **UNVERIFIED** (toggle didn't render) |
| Forge free tier / trial | **UNVERIFIED** (none advertised) |
| SpinupWP annual pricing & API rate limits | **UNVERIFIED** |
| ServerPilot backups (first-party scheduled) | **UNVERIFIED** — evidence points to provider snapshots only |
| ServerPilot alerting channels | **UNVERIFIED** — no alerting advertised |
| All Trustpilot/G2 quotes | Pages are bot-protected (403 / JS challenge). Quotes relayed via search-engine summaries of those pages — **indicative, not verbatim-verified.** Star ratings **UNVERIFIED** |
| "RunCloud AI" at myrun.cloud | Host **refused connection** on test; affiliation with RunCloud **UNVERIFIED** — treat as third-party |
| Ploi staging / migration / CLI | **UNVERIFIED** — not documented on pages read |
| Moss defunct status | ✅ **VERIFIED** — direct DNS (2 public resolvers), WHOIS, and Wayback CDX evidence |

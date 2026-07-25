# Competitor Research — GROUP B: Agency-Focused & Managed-Hosting Platforms

Research date: 2026-07-25. For ServerAlly competitive positioning.

**Method note:** Every factual claim below carries a source URL. Where a vendor's own page
could not be reached (403/404/SSL block) or the claim could only be found in secondary
review sites, it is labelled explicitly. Anything not confirmed is written **UNVERIFIED**
rather than guessed.

---

## 0. Executive summary — the two business models in this group

This group splits cleanly into **two different products** that are often confused:

| Model | Vendors | What you buy | Infra cost |
|---|---|---|---|
| **A. Control-plane / management software** (you bring or rent the servers) | GridPane, Enhance | A panel + automation layer | Separate, or bundled optionally |
| **B. Bundled managed hosting** (management fee is invisible, baked into the plan) | Cloudways, Rocket.net, Kinsta, Nexcess/Liquid Web | Hosting + management as one price | Included, not separable |

**Critical finding for ServerAlly:** only two vendors in this group (GridPane, Enhance) sell a
**management fee separate from infrastructure**, and *both have moved away from per-server
subscription pricing*:
- **Enhance** charges **per website, $0.15/site/mo**, no per-server fee at all
  ([enhance.com/pricing](https://enhance.com/pricing)).
- **GridPane** made its core panel **free forever for 25 sites** and now monetises via
  managed servers (PeakFreq) and future à-la-carte add-ons
  ([gridpane.com/plans](https://gridpane.com/plans/)).

The other four bundle everything and **gate on sites + storage + bandwidth**, never on
"servers managed" and never on usage of the management tools.

**Second critical finding:** **Rocket.net ships a full MCP server and native
Claude/ChatGPT/Gemini integration, free to all customers**
([rocket.net/solutions/ai-hosting-for-wordpress](https://rocket.net/solutions/ai-hosting-for-wordpress/)).
This is the closest direct competitor to ServerAlly's MCP connector strategy found in this
group — see §8.

---

## 1. GridPane

### 1.1 Positioning & buyer

> "GridPane helps serious WordPress agencies crush their hosting problems"
> — [G2 vendor description](https://www.g2.com/products/gridpane/reviews)

Self-managed WordPress server control plane. Buyer = **WordPress agency / developer who
wants to own their infrastructure** and resell hosting as care plans. Explicitly
positioned for agencies "looking to build enterprise-level hosting services with recurring
revenue" ([gridpane.com/gridpane-vs/runcloud](https://gridpane.com/gridpane-vs/runcloud/)).

### 1.2 Pricing — **MAJOR MODEL CHANGE, verified 2026-07**

GridPane's historic good/better/best subscription tiers are **gone**:

> "Panel and Developer Plus plans are no longer available for sign up… in the near future
> you will be able to access all GridPane features via addons."
> — [gridpane.com/plans](https://gridpane.com/plans/)

**Current plan structure** ([gridpane.com/pricing](https://gridpane.com/pricing/), [gridpane.com/plans](https://gridpane.com/plans/)):

| Plan | Price | Gates on | Notes |
|---|---|---|---|
| **Core** | **$0 — "100% free forever"** | **Up to 25 websites**; 5 sites per 1 GB RAM; min 2 GB RAM server; **Vultr servers only** | No support team access — community + KB only |
| **PeakFreq** | "From as low as **$19/month**" | Per **server**, billed hourly; **no website limits** on PeakFreq servers | Managed servers, bundled infra + management |
| **Bespoke** | "From as low as **$2000/year**" | Custom | 360 pre-emptive support, done-for-you security, agency partnerships, highest SLAs |

**Core plan explicit exclusions** ([gridpane.com/kb/core-plan-questions-and-answers](https://gridpane.com/kb/core-plan-questions-and-answers/)):
> "As the Core plan is 100% free, access to our support team is not included on this plan."
- Custom servers (bring-your-own-VPS) are "only available on paid plans" — Core is Vultr-only.
- 1 GB RAM servers not available; 2 GB minimum.

**PeakFreq server pricing** ([gridpane.com/peakfreq/pricing](https://gridpane.com/peakfreq/pricing/)) — 8 sizes, **bundled** infra + management ("we pay for these servers directly, and then lease them to you"):

| vCPU | RAM | Storage | Bandwidth | Hourly | Monthly |
|---|---|---|---|---|---|
| 1 | 2 GB | 64 GB NVMe | 2 TB | $0.0269 | **$18.08** |
| 2 | 2 GB | 80 GB NVMe | 3 TB | $0.0402 | $27.01 |
| 2 | 4 GB | 128 GB NVMe | 3 TB | $0.0536 | $36.02 |
| 3 | 8 GB | 256 GB NVMe | 4 TB | $0.1720 | $72.04 |
| 4 | 16 GB | 384 GB NVMe | 5 TB | $0.2143 | $144.01 |
| 6 | 24 GB | 448 GB NVMe | 6 TB | $0.3215 | $216.05 |
| 8 | 32 GB | 512 GB NVMe | 7 TB | $0.4286 | $288.02 |
| 12 | 48 GB | 768 GB NVMe | 8 TB | $0.5715 | $384.05 |

**Free tier:** yes (Core). **Trial:** n/a (Core *is* the trial).
**Legacy:** LTD was $1,500 in Nov 2023, no longer sold ([primeclub.co](https://primeclub.co/gridpane-lifetime-deal/)); GridPane says it is "sunsetting the good/better/best tiers and shifting towards an à-la-carte 'choose your own adventure' pricing model" ([managingwp.io live blog](https://managingwp.io/live-blog/gridpane-black-friday-deal-platform-updates-roadmap-change/)).

### 1.3 Feature checklist

| Feature | GridPane | Evidence |
|---|---|---|
| Server provisioning | **YES** — Vultr on Core; custom/BYO servers on paid plans only | [core Q&A](https://gridpane.com/kb/core-plan-questions-and-answers/) |
| Cloud provider integrations | **PARTIAL** — Vultr confirmed for current plans; other providers UNVERIFIED for 2026 lineup | [peakfreq KB](https://gridpane.com/kb/peakfreq-managed-hosting/) |
| One-click app installs | **PARTIAL** — WordPress-only ("Pre-install Bundles", "Blueprint Starter Websites") | [features](https://gridpane.com/features/), [core plan](https://gridpane.com/plans/core/) |
| Git deploy | **YES** — "Advanced Git" (exiting beta) | [features](https://gridpane.com/features/) |
| Staging + clone/push-to-live | **PARTIAL** — cloning in free Core; **staging is paid** (PeakFreq feature list) | [core plan](https://gridpane.com/plans/core/), [pricing](https://gridpane.com/pricing/) |
| PHP/runtime version mgmt | **YES** — "Easy, Unrestricted PHP Management" | [core plan](https://gridpane.com/plans/core/) |
| SSL | **YES** — A+ grade certs, free tier | [core plan](https://gridpane.com/plans/core/) |
| DNS | **YES** — Cloudflare, DNS Made Easy, GridPane-managed DNS | [features](https://gridpane.com/features/) |
| Databases | **YES** — one-click phpMyAdmin; MariaDB or Percona | [core plan](https://gridpane.com/plans/core/) |
| Email hosting | **NO** — not offered | [features](https://gridpane.com/features/) (absent) |
| Cron | **UNVERIFIED** | — |
| Firewall / WAF | **YES** — 7G WAF free; BitNinja WAF (was in Dev Plus, "$144/month value"); Fortress plugin integration; multiple WAFs + Fail2Ban | [features](https://gridpane.com/features/), [security suite](https://gridpane.com/wordpress-security-suite/) |
| Malware scanning | **YES** — Maldet + ClamAV; BitNinja anti-malware | [security suite](https://gridpane.com/wordpress-security-suite/) |
| Brute-force protection | **YES** — Fail2Ban, BitNinja DoS detection / IP reputation | [features](https://gridpane.com/features/) |
| Backups (local/offsite) | **YES but PAID** — "Local & Remote Backups" listed under PeakFreq, not Core | [pricing](https://gridpane.com/pricing/) |
| Monitoring / uptime / alerts | **PARTIAL, PAID** — server monitoring on PeakFreq; **uptime monitoring "on its way"** | [features](https://gridpane.com/features/), [pricing](https://gridpane.com/pricing/) |
| Log viewer | **YES** — "Full Access to ALL of Your Logs", free tier | [core plan](https://gridpane.com/plans/core/) |
| File manager | **UNVERIFIED** — SFTP confirmed, dedicated file manager not confirmed | — |
| SSH / SFTP user mgmt | **YES** — full root access + secure SFTP on free tier | [core plan](https://gridpane.com/plans/core/) |
| Teams + roles | **PARTIAL** — multi-user account support mentioned, detail UNVERIFIED | [features](https://gridpane.com/features/) |
| **White-label / agency branding** | **PARTIAL / UNVERIFIED** — marketing says agencies "offer white-label hosting services to their clients", but a **built-in client-facing branded dashboard is not confirmed on GridPane's own pages** | [aijet review](https://aijet.cc/item/gridpane) (secondary) |
| **Client billing / reselling** | **NO built-in billing.** A practitioner comment notes GridPane and RunCloud "lack automated billing" | [wpjohnny](https://wpjohnny.com/runcloud-cloudways-gridpane-2022-review/) |
| Marketplace / templates | **YES** — Blueprint Sites, Pre-install Bundles | [features](https://gridpane.com/features/) |
| WP: plugin/theme updates | **YES** — "UpdateSafely" (overhaul in progress) | [features](https://gridpane.com/features/) |
| WP: visual regression testing | **YES** — "visual regression testing for automated updates" | [features](https://gridpane.com/features/) |
| WP: WP-CLI | **YES** — GP-CLI + WP-CLI, free tier | [core plan](https://gridpane.com/plans/core/) |
| WP: multisite | **YES** — traditional multisite **plus multitenancy** (single codebase → thousands of sites, WaaS→SaaS) | [features](https://gridpane.com/features/), [aijet](https://aijet.cc/item/gridpane) |
| Migration tools | **PARTIAL** — cloning / clone-all-sites-to-new-server; dedicated migrator UNVERIFIED | [core plan](https://gridpane.com/plans/core/) |
| API | **YES** — "API Integrations"; process manager "for the API" in development | [features](https://gridpane.com/features/) |
| CLI | **YES** — GP-CLI | [core plan](https://gridpane.com/plans/core/) |
| Mobile app | **NO** | [features](https://gridpane.com/features/) (absent) |
| **AI features** | **NO** — no AI features mentioned anywhere on GridPane's feature pages | [features](https://gridpane.com/features/) |

**Notable unique features:** Snapshot Failover™ (managed failover with DNS integration, up to 50 sites); Fortress security plugin integration; **multitenancy for WaaS→SaaS**; Object Cache Pro + Relay.

### 1.4 Praise & complaints

**Praise:**
- Performance: users report sites "load more quickly than alternatives" vs RunCloud, Cloudways, SpinupWP, Ploi, ServerPilot ([wpjohnny](https://wpjohnny.com/runcloud-cloudways-gridpane-2022-review/)).
- G2: "Users consistently praise the performance and ease of use… quick server provisioning… extensive documentation and support" ([G2](https://www.g2.com/products/gridpane/reviews)).

**Complaints — pricing instability is the dominant theme:**
- > "despite their 'Transparent Pricing' label, it's anything but, and their pricing and business model changes all the time (like 2-3 times per year)" — [wpjohnny](https://wpjohnny.com/best-wordpress-hosting-reviews/)
- > "the GridPane lifetime LTD plans have turned out to be a scam, as all new features they develop are not included, but require a separate ongoing subscription payment" — [wpjohnny](https://wpjohnny.com/best-wordpress-hosting-reviews/). (Counterpoint: GridPane has publicly refunded LTD customers in full — [gridpane.com/blog/the-market-has-spoken-re-gridpane-ltds](https://gridpane.com/blog/the-market-has-spoken-re-gridpane-ltds/).)
- **Buggy new features:** "this panel makes many promises and [is] aggressive with feature development, [but] their latest features can be buggy" ([websiteplanet](https://www.websiteplanet.com/web-hosting/gridpane/)).
- **Dated UI:** users "would like to see a more modern UI and a better notification system… notifications are hard to follow, especially when there are several actions firing at once" ([G2 pros/cons](https://www.g2.com/products/gridpane/reviews?qs=pros-and-cons) via search).
- **Too technical for non-devs:** one user complained GridPane "obstructs WordPress site management, describing the interface as difficult to navigate for those without technical knowledge" ([alternativeto](https://alternativeto.net/software/gridpane)).
- Support "needs to be more extensive" ([websiteplanet](https://www.websiteplanet.com/web-hosting/gridpane/)).

> **⚠️ ServerAlly-relevant:** the two loudest GridPane complaints are **"too technical for
> non-technical users"** and **"pricing changes constantly."** Both are directly addressable
> — see §9.

### 1.5 Agency-specific features

Agencies get: Snapshot Failover™, multitenancy (WaaS→SaaS), Fortress security, higher SLAs
+ "agency partnerships" on Bespoke ($2,000/yr+), and 360 pre-emptive support. But **no
built-in client billing and no confirmed client-facing white-label dashboard** — agencies
must bolt on their own billing (WHMCS etc.).

---

## 2. Cloudways (a DigitalOcean company)

### 2.1 Positioning & buyer

Managed cloud hosting layered on top of five public clouds. Buyer = **freelancer/agency
that wants managed hosting without picking a host**, plus developers who want cloud
flexibility without sysadmin work.

### 2.2 Pricing — **BUNDLED** (management fee is not separable)

Cloudways has **two distinct product lines**, both bundling infra + management:

**(a) Cloudways Flexible** — pay per server, per hour ([cloudways.com/en/pricing.php](https://www.cloudways.com/en/pricing.php)):

| Provider | Entry price | Notes |
|---|---|---|
| DigitalOcean | **from ~$11/mo** (2 GB RAM, 1 vCPU, 50 GB) | cheapest |
| Vultr | from **$14/mo** standard; **$16/mo** high-frequency | secondary source: [managedwpguide](https://managedwpguide.com/cloudways-pricing/) |
| Linode/Akamai | from **$14/mo** | secondary source |
| AWS | from **$38.56/mo** (2 GB RAM) | ~3× DO for comparable specs |
| Google Cloud | from **$37.45/mo** (1.7 GB RAM) | ~3× DO |

Top of the DO range: **8XL at $342/mo** (128 GB RAM, 24 vCPU, 2,560 GB).
Mid: Medium **$88/mo** (8 GB RAM, 4 vCPU, 160 GB).
*(Cloudways' own pricing page renders "Micro" and "Small" both at $11 — likely a page artifact; treat the exact Micro/Small split as UNVERIFIED.)*

**What Flexible gates on:** **server size (RAM/vCPU/storage)** — explicitly
**"Unlimited Visits" and "Unlimited Websites"** per server
([cloudways.com/en/pricing.php](https://www.cloudways.com/en/pricing.php)). This is the
closest model in the group to "price per server."

**(b) Cloudways Autonomous** — fully-managed autoscaling WordPress ([cloudways.com/en/autonomous.php](https://www.cloudways.com/en/autonomous.php)):

| Plan | Price | Baseline servers | Disk | Bandwidth | Visits |
|---|---|---|---|---|---|
| Free Trial | **$0 / 3 days** | 1 | 20 GB | 150 GB | Unmetered |
| Growth | **$99/mo** | 1 | 20 GB | 150 GB | Unmetered |
| Scale | **$199/mo** | 2 | 50 GB | 250 GB | Unmetered |
| Plus | **$399/mo** | 3 | 100 GB | 1,000 GB | Unmetered |
| Enterprise | Custom | — | — | — | — |

All Autonomous plans: **1 WordPress application**, 100 PHP workers/server.
Overages: **Disk $1/GB, Bandwidth $0.04/GB**, autoscaling **$0.07–$0.12/hr per extra server**.
Autonomous **removed visit-based billing in Nov 2025** ([cloudways blog](https://www.cloudways.com/blog/autonomous-new-pricing/)).

**Separately-priced add-ons** (this is where the agency money is):

| Add-on | Price | Source |
|---|---|---|
| **Client Billing** — Free | $0 (1 client, 2 services, 1 report/mo) | [client-billing.php](https://www.cloudways.com/en/client-billing.php) |
| **Client Billing** — Growth | **$4.99/mo** (10 clients, 15 services, 10 reports/mo) | same |
| **Client Billing** — Scale | **$13.99/mo** (unlimited clients/services/reports) | same |
| Offsite backup storage | **$0.033/GB per server** | [pricing.php](https://www.cloudways.com/en/pricing.php) |
| SafeUpdates | **$3/site/mo** (up to 5 sites) | [cloudways.com/en/safeupdates.php](https://www.cloudways.com/en/safeupdates.php) via search |
| Malware Protection (Imunify360) | **from $4/app/mo** | [cloudways blog](https://www.cloudways.com/blog/introducing-malware-protection/) |
| Advanced Support | **$25/mo flat** (LTD; was $100/mo) | [hosting-for-agencies.php](https://www.cloudways.com/en/hosting-for-agencies.php) |
| **AI Copilot** Growth | **$9.99/mo** = 12 AI credits/mo | search result citing [support.cloudways.com](https://support.cloudways.com/en/articles/11959655-how-does-cloudways-copilot-pricing-and-billing-work) (page 403'd to direct fetch — treat as secondary) |
| AI Copilot free allowance | 5 free AI credits + 2 free SmartFixes/mo for first 6 months; **free entirely if monthly invoice > $100** | same secondary source |

**Bandwidth overage** varies by provider: AWS $0.12/GB, GCP $0.10–$0.17/GB, DigitalOcean $0.02/GB ([pricing.php](https://www.cloudways.com/en/pricing.php)).

**Free tier / trial:** 3-day free trial on Autonomous, **no credit card required** ([pricing.php](https://www.cloudways.com/en/pricing.php)). Client Billing has a genuine free tier.

*A "Flex" plan for agencies was mentioned in one secondary source ([cybernews](https://cybernews.com/best-web-hosting/best-website-hosting-for-agencies/)) — **UNVERIFIED**, not found on Cloudways' own pricing page.*

### 2.3 Feature checklist

| Feature | Cloudways | Evidence |
|---|---|---|
| Server provisioning | **YES** — launch servers on 5 clouds from the panel | [pricing.php](https://www.cloudways.com/en/pricing.php) |
| Cloud provider integrations | **YES** — DigitalOcean, Vultr, Linode/Akamai, AWS, Google Compute Engine | [pricing.php](https://www.cloudways.com/en/pricing.php) |
| One-click app installs | **YES** — WordPress, WooCommerce, Magento, Laravel, PHP | [cloudways.com](https://www.cloudways.com/en/) |
| Git deploy | **YES** — auto-deploy from GitHub/GitLab/Bitbucket via SSH | [hosting-for-agencies.php](https://www.cloudways.com/en/hosting-for-agencies.php); [cloudwards](https://www.cloudwards.net/what-is-cloudways/) |
| Staging + clone/push-to-live | **YES** — 1-click staging w/ push-to-live (files + DB); **1-Click Cloning of sites AND entire servers** | [hosting-for-agencies.php](https://www.cloudways.com/en/hosting-for-agencies.php) |
| PHP version mgmt | **YES** | [cloudwards](https://www.cloudwards.net/what-is-cloudways/) |
| SSL | **YES** — free Let's Encrypt, 1-click | [pricing.php](https://www.cloudways.com/en/pricing.php) |
| DNS | **PARTIAL** — DNS Made Easy listed as an *integration*, not native DNS | [cloudways.com](https://www.cloudways.com/en/) |
| Databases | **YES** — built-in database manager | [cloudwards](https://www.cloudwards.net/what-is-cloudways/) |
| Email hosting | **PARTIAL / add-on** — historically Rackspace email add-on; **current status UNVERIFIED** | — |
| Cron | **YES** — GUI cron scheduler, no CLI needed | [cloudwards](https://www.cloudwards.net/what-is-cloudways/) |
| Firewall / WAF | **YES** — OS firewall + bot protection; Cloudflare Enterprise (included in Autonomous, add-on for Flexible) | [autonomous.php](https://www.cloudways.com/en/autonomous.php) |
| Malware scanning | **YES — PAID ADD-ON** from $4/app/mo (Imunify360) | [cloudways blog](https://www.cloudways.com/blog/introducing-malware-protection/) |
| Backups (offsite/retention/restore) | **YES** — automated + on-demand + restore; offsite storage metered at **$0.033/GB/server**; Autonomous includes **unlimited offsite backups** | [pricing.php](https://www.cloudways.com/en/pricing.php), [autonomous.php](https://www.cloudways.com/en/autonomous.php) |
| Monitoring + alerts | **YES** — real-time CPU/RAM/disk-I/O/network; auto-healing; New Relic APM integration | [cloudwards](https://www.cloudwards.net/what-is-cloudways/) |
| Log viewer | **UNVERIFIED** (SSH access confirmed) | — |
| File manager | **UNVERIFIED** (SFTP confirmed) | — |
| SSH / SFTP user mgmt | **YES** — per-application credentials | [hosting-for-agencies.php](https://www.cloudways.com/en/hosting-for-agencies.php) |
| **Teams + roles** | **YES** — "assign custom roles to developers, designers, and project managers"; role-based permissions per client project | [hosting-for-agencies.php](https://www.cloudways.com/en/hosting-for-agencies.php) |
| **White-label** | **PARTIAL** — white-label **invoices** (logo + brand colour) in all Client Billing tiers; full white-label of the Cloudways panel itself **UNVERIFIED** | [client-billing.php](https://www.cloudways.com/en/client-billing.php) |
| **Client billing / reselling** | **YES — separate paid product.** Recurring billing, Stripe, 135+ currencies, refunds, taxes/discounts, offline payments | [client-billing.php](https://www.cloudways.com/en/client-billing.php) |
| Client reporting | **YES** — Client Reporting product; report counts gated by billing tier (1 / 10 / unlimited per month) | [client-billing.php](https://www.cloudways.com/en/client-billing.php) |
| Marketplace / templates | **UNVERIFIED** | — |
| WP: plugin/theme updates | **YES — PAID** SafeUpdates $3/site/mo | [safeupdates.php](https://www.cloudways.com/en/safeupdates.php) |
| WP: visual regression testing | **PARTIAL** — SafeUpdates does automated update testing; explicit "visual regression" wording UNVERIFIED | — |
| WP: WP-CLI | **YES** (via SSH) | [cloudwards](https://www.cloudwards.net/what-is-cloudways/) |
| WP: multisite | **UNVERIFIED** | — |
| Migration tools | **YES** — free managed migration + WP migrator plugin | [pricing.php](https://www.cloudways.com/en/pricing.php) |
| API | **YES** | [cloudways.com](https://www.cloudways.com/en/) |
| CLI | **UNVERIFIED** | — |
| Mobile app | **UNVERIFIED** | — |
| **AI features** | **YES — two products.** (1) **AI Copilot**: monitors servers/apps, detects issues, gives resolution steps, **1-click "SmartFix"**; credit-metered. (2) **Managed AI Agents**: host AI agents (OpenClaw, Hermes) on managed infra with your own LLM keys | [managed-ai-agents.php](https://www.cloudways.com/en/managed-ai-agents.php), [cloudways blog](https://www.cloudways.com/blog/introducing-ai-copilot/) |

### 2.4 Praise & complaints

**Ratings:** G2 **4.7/5** (~900–1,120 reviews), Trustpilot **4.6/5** (~3,670 reviews),
Capterra **4.2/5** ([G2](https://www.g2.com/products/cloudways), [Trustpilot](https://www.trustpilot.com/review/cloudways.com), [Capterra](https://www.capterra.com/p/151414/Cloudways/reviews/)).

**Praise:** intuitive UI, choice of cloud provider, seamless no-downtime vertical scaling,
24/7 live chat with ~90s average first response ([G2 summary](https://www.g2.com/products/cloudways)).

**Complaints — support is the #1 churn driver post-acquisition:**
- > "The most-cited complaint by a wide margin is support, specifically slow first responses, escalation loops, and a sense that ticket quality depends on which agent you happen to draw." — [checkthat.ai review aggregation](https://checkthat.ai/brands/cloudways/reviews)
- One ticket reportedly "bounced through more than 10 different agents in 8 days" (same source).
- **Post-DigitalOcean-acquisition decline:** "Since Cloudways was acquired by DigitalOcean, they've increased prices"; complaints about "AI chat support… issues with billing and server shut-offs" ([onlinemediamasters](https://onlinemediamasters.com/cloudways-review/)).
- > "Cloudways' performance/support aren't great with half-baked integrations, high CPU usage from bloat, and expensive markups by DigitalOcean." — [onlinemediamasters](https://onlinemediamasters.com/cloudways-review/)
- Billing complexity is a recurring Capterra theme.

### 2.5 Agency-specific features

Cloudways is the **most agency-complete** vendor in this group on the business side:
- **Client Billing** (white-label invoices, Stripe, recurring, multi-currency) — priced separately, $0/$4.99/$13.99.
- **Client Reporting** (hosting metrics → client-readable performance/security/update reports) — **gated by billing tier** (1 report/mo free → unlimited at $13.99).
- **Role-based team permissions** per client project, and "give clients the right level of access to their own sites" ([reseller-hosting.php](https://www.cloudways.com/en/reseller-hosting.php)).
- **Site Manager** for portfolio-wide updates/monitoring/access control.
- **Pay-per-server model enabling client resale** with unlimited sites per server — the margin engine.

---

## 3. Enhance (enhance.com)

### 3.1 Positioning & buyer

> "the next-gen hosting control panel"
> — [enhance.com](https://enhance.com/)

Self-hosted, clustered control panel. Buyer = **hosting companies and resellers**, not end
users. This is a **cPanel/Plesk replacement**, not an agency tool per se — but its reseller
model makes it agency-capable.

### 3.2 Pricing — **PURE PER-WEBSITE LICENCE, ZERO PER-SERVER FEE**

([enhance.com/pricing](https://enhance.com/pricing))

| Tier | Price | Volume |
|---|---|---|
| Tier 1 | **$0.15 per website per month** | 1–5,000 websites |
| Tier 2 | **$0.10 per website per month** | 5,001–25,000 websites |
| Tier 3 | **$0.075 per website per month** | 25,001–100,000 websites |

- **Minimum: $10/month.**
- Blended/tiered calculation — sites "billed at the tier in which they fall."
- Billed monthly on active websites at month-end. "No long-term contracts."
- **NOT charged:** addon/alias domains, staging sites, soft-deleted websites, control panel
  services, **server count**, subdomain aliases.
- **Free tier / trial: none stated on the pricing page.**

> **This is the single most instructive pricing model in Group B for ServerAlly:** Enhance
> deliberately charges **nothing per server** — servers are free to add, you pay only for
> the billable unit the customer resells (a website). It is the exact inverse of the
> per-server model.

*Note: a LowEndTalk comment claims "Enhance [white-labels] on their $6 a month plan"
([lowendtalk](https://lowendtalk.com/discussion/189843/enhance-and-upmind-a-marriage-made-in-heaven)) —
**UNVERIFIED / contradicts** the official pricing page, which lists only per-site tiers and a
$10 minimum. Treat the $6 figure as unreliable.*

### 3.3 Feature checklist

Enhance has by far the **broadest raw feature surface** in this group (it is a full hosting panel):

| Feature | Enhance | Evidence |
|---|---|---|
| Server provisioning | **PARTIAL** — "Add servers with a single command"; it **joins** existing servers to a cluster, it does not create cloud VMs | [enhance.com/features](https://enhance.com/features) |
| Cloud provider integrations | **NO** — not listed anywhere | [product/features](https://enhance.com/product/features) |
| One-click app installs | **YES** — WordPress, WooCommerce, Joomla | [product/features](https://enhance.com/product/features) |
| Git deploy | **NO** — not listed | [product/features](https://enhance.com/product/features) |
| Staging + clone/push-to-live | **YES** — "Staging websites with one-click deployment to live"; website cloning w/ DB duplication | [product/features](https://enhance.com/product/features) |
| PHP version mgmt | **YES** — 5.6, 7.0–7.4, 8.0–8.5 default (5.2–5.6 optional); php.ini directives; max processes; IonCube | [product/features](https://enhance.com/product/features) |
| SSL | **YES** — auto Let's Encrypt + custom certs + force HTTPS | [product/features](https://enhance.com/product/features) |
| DNS | **YES (strong)** — PowerDNS, unlimited decentralised DNS servers, zone editor, **DNS templating**, DNSSEC per-domain, **custom nameservers**, Cloudflare sync | [product/features](https://enhance.com/product/features) |
| Databases | **YES** — add/edit/delete, DB users w/ permissions, import/export SQL, phpMyAdmin | [product/features](https://enhance.com/product/features) |
| **Email hosting** | **YES (full)** — Roundcube webmail + SSO, mailboxes/aliases/forwarders, autoresponders, catch-all, **Rspamd spam filtering**, SPF + DKIM, allow/block lists, Gmail auto-config | [product/features](https://enhance.com/product/features) |
| Cron | **YES** | [product/features](https://enhance.com/product/features) |
| Firewall / WAF | **YES** — ModSecurity (OWASP) across Apache/Nginx/LiteSpeed, per-domain toggle; IP allow/block | [product/features](https://enhance.com/product/features) |
| Malware scanning | **NO** — not listed (third-party e.g. cPFence/Imunify used by operators) | [product/features](https://enhance.com/product/features) (absent) |
| Brute-force protection | **YES** — rate limits + block/allow lists + 2FA | [product/features](https://enhance.com/product/features) |
| Backups | **YES (strong)** — **incremental/differential ("saving up to 80% on storage")**, S3-compatible, scheduled cluster-wide, on-demand, **granular restore (sites / individual files / databases / mailboxes)**, restore archived + deleted websites, download/upload between clusters, **disaster recovery from lost server "in minutes"** | [features](https://enhance.com/features), [product/features](https://enhance.com/product/features) |
| Monitoring + alerts | **PARTIAL** — server stats (disk/memory/network/load) in dashboard + Slack notifications; **no uptime monitoring or alert rules listed** | [product/features](https://enhance.com/product/features) |
| Log viewer | **UNVERIFIED** | — |
| File manager | **YES** — drag-drop, mass operations, responsive | [product/features](https://enhance.com/product/features) |
| SSH / SFTP user mgmt | **YES** — FTP account management, SSH key + password auth | [product/features](https://enhance.com/product/features) |
| Teams + roles | **YES** — users-and-roles, permission-based access control, access tokens, device/session tracking | [product/features](https://enhance.com/product/features), [docs](https://enhance.com/docs/) |
| **White-label / branding** | **YES (full)** — logos, colours, fonts, **custom panel domain**, plus **custom phpMyAdmin and staging domains**, **branded nameservers**; SSL cert issuer can be changed to reseller name | [product/features](https://enhance.com/product/features), [community thread](https://community.enhance.com/d/267-brandingwhite-label-change-certificate-issuer-to-reseller-name-released) |
| **Client billing / reselling** | **YES (best-in-group)** — **multi-tiered, unlimited reselling levels**, each reseller with own branding + packages + panel domain; **customer impersonation ("see exactly what they see")**; billing modules for **WHMCS, Blesta, HostBill, Upmind** | [product/features](https://enhance.com/product/features), [docs/billing-integrations](https://enhance.com/docs/billing-integrations/) |
| Marketplace / templates | **PARTIAL** — custom packages w/ quotas, DNS templates | [product/features](https://enhance.com/product/features) |
| WP: plugin/theme updates | **YES** — autoupdate scheduler for core + plugins, plugin management | [product/features](https://enhance.com/product/features) |
| WP: visual regression testing | **NO** | [product/features](https://enhance.com/product/features) (absent) |
| WP: WP-CLI | **UNVERIFIED** (SSH available) | — |
| WP: other | WP user mgmt from panel, **wp-admin lockdown by IP**, debug mode, **WordPress SSO**, multi-installation mgmt | [product/features](https://enhance.com/product/features) |
| WP: multisite | **UNVERIFIED** | — |
| Migration tools | **YES** — **cPanel importer** (UI or as root, from backups or SCP), **Plesk importer**, website upload/download between clusters | [product/features](https://enhance.com/product/features) |
| API | **YES** — "Every feature available in the Enhance UI is accessible via our robust API"; RESTful | [features](https://enhance.com/features) |
| CLI | **PARTIAL** — single-command server install; a general-purpose CLI is **not listed** | [product/features](https://enhance.com/product/features) |
| Mobile app | **NO** — responsive web UI only (desktop/tablet/mobile) | [product/features](https://enhance.com/product/features) |
| **AI features** | **NO** — none listed | [product/features](https://enhance.com/product/features) |

**Notable architecture:** every website runs in **its own lightweight Linux container**;
clusters scale to **10,000+ servers**; roles (Application, Database, Backup, Email, DNS)
can be split across servers or monolithic; **web server kind is switchable (Apache /
LiteSpeed / OpenLiteSpeed / NGINX) "without any reconfiguration"**; Node.js hosting with
auto-startup + monitoring; per-website resource limits (CPU, I/O, IOPS, memory, swap).

### 3.4 Praise & complaints

**Praise:**
- Cost: "Per-account pricing is much lower than cPanel at $0.15 per account per month with no per-server cost" ([webhosting.de](https://webhosting.de/en/cpanel-enhance-compare-hosting-innovation/)).
- Architecture: "cloud-cluster architecture and Btrfs snapshots that shorten backup and restore times" (same source).
- Some operators: "tried every control panel as alternatives to cPanel and Plesk, and found Enhance fit their needs best and proved to be production ready" ([Trustpilot](https://www.trustpilot.com/review/enhance.com), via search).

**Complaints — polarised, with real production-readiness doubts:**
- > "A total Disaster" — most advertised features "not working as advertised" with "critical bugs," recommending "not to trust it in production" — [Trustpilot](https://www.trustpilot.com/review/enhance.com) (via search)
- > "The numerous bugs, limitations, and lack of essential features make it an unreliable choice for production environments" — [Enhance community thread](https://community.enhance.com/d/973-enhance-panel-a-disappointing-experience?page=2)
- **Missing basics reported:** "brute force protection, proper spam management, mail rate limiting, email piping, and a better backup system that can exclude sites/files" ([community](https://community.enhance.com/)).
- **Backup reliability threads** are numerous: [backup issues](https://community.enhance.com/d/1562-backup-a-few-issues), [auto backup failure](https://community.enhance.com/d/2321-auto-backup-failure).
- **WordPress toolkit "needs some improvement"** ([lowendtalk](https://lowendtalk.com/discussion/217622/enhance-control-panel-experience)).
- **Weak market adoption:** one provider offering all three found "cPanel beat DirectAdmin by 25% margin while Enhance was nowhere near both of them in terms of customer preference" (April 2025) ([lowendtalk](https://lowendtalk.com/discussion/208079/anyone-using-enhance-control-panel-in-production)).
- Migrating cPanel customers "didn't like Enhance and experienced slower website benchmarks and general client feel" (same).

### 3.5 Agency-specific features

Enhance is the **reseller/white-label reference implementation** in this group:
- **Unlimited multi-tier reselling** — resellers can have resellers, each with own branding/packages/panel domain.
- **Customer impersonation** — critical support feature, absent from most competitors.
- **Branded nameservers + branded phpMyAdmin + branded staging domains** — few competitors go this deep.
- **4 billing-platform integrations** (WHMCS, Upmind, HostBill, Blesta) — but **no native billing**.

---

## 4. Rocket.net

### 4.1 Positioning & buyer

> "the fastest and most secure AI Hosting for WordPress with native ChatGPT, Claude, &
> Gemini support, plus a full MCP server for AI-native sites and agents"
> — [rocket.net/solutions/ai-hosting-for-wordpress](https://rocket.net/solutions/ai-hosting-for-wordpress/)

Cloudflare-Enterprise-fronted managed WordPress. Buyer = **performance-sensitive site
owners and agencies who want to resell white-labelled WordPress hosting**.

### 4.2 Pricing — **BUNDLED**, gates on **sites + storage + bandwidth**

([rocket.net/pricing](https://rocket.net/pricing/))

**Managed plans** (all: unlimited visitors, 99.99% uptime SLA, free SSL, Enterprise CDN, WAF, malware protection, free migrations, daily backups 30-day retention, PHP 5.6–8.4):

| Plan | Monthly | (intro) | Annual | Sites | Storage | Bandwidth |
|---|---|---|---|---|---|---|
| Starter | $30 | $25 | $300/yr | 1 | 10 GB | 50 GB |
| Pro | $60 | $50 | $600/yr | 3 | 20 GB | 100 GB |
| Business | $100 | $83 | $1,000/yr | 10 | 40 GB | 300 GB |
| Expert | $200 | $166 | $2,000/yr | 25 | 50 GB | 500 GB |

**Agency plans** (Managed features **+ Agency Toolkit**):

| Tier | Monthly | Annual | Sites | Storage | Bandwidth |
|---|---|---|---|---|---|
| Tier 1 | **$100** ($83 intro) | $1,000/yr | 10 | 50 GB | 200 GB |
| Tier 2 | **$200** ($166 intro) | $2,000/yr | 20 | 75 GB | 500 GB |
| Tier 3–10 | **$300 – $1,600/mo** | varies | 30–200 | 100–375 GB | 600 GB – 3.5 TB |

*Secondary source gives the full reseller ladder as Tier 1 (10) $83/mo → Tier 10 (200 installs) $1,333/mo on annual billing ([startupplugs](https://startupplugs.com/rocket-net-pricing/)).*

**Enterprise plans** (dedicated resources):

| Plan | Price | CPU | RAM | Storage | Bandwidth |
|---|---|---|---|---|---|
| Enterprise 1 | $649/mo | 8 cores | 64 GB | 1 TB | 1 TB |
| Enterprise 2 | $1,299/mo | 32 cores | 128 GB | 1 TB | 1 TB |
| Enterprise 3 | $1,949/mo | 64 cores | 256 GB | 2 TB | 2 TB |
| Enterprise 4 | $2,599/mo | 96 cores | 256 GB | 2 TB | 2 TB |

**Trial:** "$1 first month" on all plans; annual = "two months free"; 30-day money-back
guarantee except Enterprise ([rocket.net/pricing](https://rocket.net/pricing/)). **No free tier.**

### 4.3 Feature checklist

| Feature | Rocket.net | Evidence |
|---|---|---|
| Server provisioning | **NO** — platform, not servers | — |
| Cloud provider integrations | **NO** | — |
| One-click app installs | **PARTIAL** — WordPress only; sites provisioned "in under 30 seconds" | [ai-hosting](https://rocket.net/solutions/ai-hosting-for-wordpress/) |
| Git deploy | **NO / PARTIAL** — SSH + git *access* exist, but a reviewer states automated git deployment "is not possible with Rocket.net" | [wpkube](https://www.wpkube.com/rocket-net-review/) |
| Staging + clone/push-to-live | **YES** — staging on all plans | [wpbeginner](https://www.wpbeginner.com/hosting/onrocket/) |
| PHP version mgmt | **YES** — PHP 5.6–8.4 | [rocket.net/pricing](https://rocket.net/pricing/) |
| SSL | **YES** — free SSL; SSL issuance exposed as an MCP tool | [rocket.net](https://rocket.net/) |
| DNS | **YES** — DNS management, **white-labelable on agency plans** | [wordpress-reseller-hosting](https://rocket.net/solutions/wordpress-reseller-hosting/) |
| Databases | **YES** — phpMyAdmin with one-click SSO | [designbombs](https://www.designbombs.com/rocketnet-review/) |
| **Email hosting** | **NO** — "No email hosting – You'll need Google Workspace"; can't register domains either | [bloggingx](https://bloggingx.com/rocket-net-review/) |
| Cron | **YES** — cron job management | [designbombs](https://www.designbombs.com/rocketnet-review/) |
| Firewall / WAF | **YES** — Cloudflare Enterprise WAF + DDoS, "Enterprise-level WordPress security configurations" | [rocket.net](https://rocket.net/) |
| Malware scanning | **YES** — "Real-time malware scanning & removal", free | [rocket.net](https://rocket.net/) |
| Brute-force protection | **YES** (via Cloudflare Enterprise WAF) | [rocket.net](https://rocket.net/) |
| Backups | **YES** — automated daily, **30-day retention**; exposed as MCP tools | [rocket.net/pricing](https://rocket.net/pricing/) |
| Monitoring + alerts | **PARTIAL** — "Usage & performance analytics"; **streaming logs and activity events** via MCP; dedicated uptime alerting UNVERIFIED | [ai-hosting](https://rocket.net/solutions/ai-hosting-for-wordpress/) |
| Log viewer | **YES** — streaming logs | [ai-hosting](https://rocket.net/solutions/ai-hosting-for-wordpress/) |
| File manager | **UNVERIFIED** (SFTP confirmed) | — |
| SSH / SFTP user mgmt | **YES** — "All users get SSH access and SFTP" | [wpkube](https://www.wpkube.com/rocket-net-review/) |
| Teams + roles | **YES** — "Collaborations"; user management exposed via MCP | [rocket.net](https://rocket.net/) |
| **White-label** | **YES — AGENCY PLANS ONLY.** "Completely White-labeled" **control panel + DNS + CDN Cache plugin**, own logo + colours | [wordpress-reseller-hosting](https://rocket.net/solutions/wordpress-reseller-hosting/) |
| **Client billing / reselling** | **YES — AGENCY PLANS ONLY.** "Set your own pricing" in the panel; API "supports multiple payment gateways without additional coding"; **WHMCS integration**; **automated provisioning** — "as soon as an order is approved, your customer is in WP admin within seconds"; panel **embeddable anywhere with HTML** | [wordpress-reseller-hosting](https://rocket.net/solutions/wordpress-reseller-hosting/) |
| Marketplace / templates | **UNVERIFIED** — MCP can "install themes, plugins, and seed content programmatically" | [ai-hosting](https://rocket.net/solutions/ai-hosting-for-wordpress/) |
| WP: plugin/theme updates | **YES** — manageable "from plugins and themes to running WP-CLI commands" (incl. via AI) | [ai-hosting](https://rocket.net/solutions/ai-hosting-for-wordpress/) |
| WP: visual regression testing | **UNVERIFIED** | — |
| WP: WP-CLI | **YES** — WP-CLI runnable, including through MCP | [ai-hosting](https://rocket.net/solutions/ai-hosting-for-wordpress/) |
| WP: multisite | **UNVERIFIED** | — |
| Migration tools | **YES** — "Unlimited free migrations", done-for-you by their team | [rocket.net](https://rocket.net/) |
| API | **YES** — "built API-first, with the same API powering the Rocket.net control panel available to customers"; public API | [wordpress-reseller-hosting](https://rocket.net/solutions/wordpress-reseller-hosting/) |
| CLI | **PARTIAL** — WP-CLI yes; a Rocket.net platform CLI UNVERIFIED | — |
| Mobile app | **UNVERIFIED** | — |
| **AI features** | **YES — THE STANDOUT IN THIS GROUP.** See §4.4 | [ai-hosting](https://rocket.net/solutions/ai-hosting-for-wordpress/) |

Also notable: **unlimited PHP workers**, free Redis, Object Cache Pro + Relay included
([rocket.net](https://rocket.net/)) — a direct jab at Kinsta's PHP-worker gating.

### 4.4 ⚠️ Rocket.net's AI/MCP offering — closest competitor to ServerAlly's MCP strategy

From [rocket.net/solutions/ai-hosting-for-wordpress](https://rocket.net/solutions/ai-hosting-for-wordpress/) and the [launch announcement](https://rocket.net/blog/rocket-net-launches-a-new-developer-hub-with-full-mcp-integration/):

- **Native model integrations inside WP Admin**: Claude (Anthropic), Gemini (Google), ChatGPT (OpenAI). Recommended split: Claude for "long-form drafting, editorial review, code generation"; Gemini for multimodal/SEO; ChatGPT for quick edits and structured data.
- **BYO API keys OR Rocket-managed model access** — *the same two-layer choice as ServerAlly's Pricing v3.*
- **Official MCP server** exposing "every Rocket.net capability as MCP tools": site creation/management, domain registration/attachment, SSL issuance, backups, staging, **user management and billing**, streaming logs and activity events.
- Works with **Claude Desktop, Cursor, VS Code, Windsurf, and n8n**.
- > "The Rocket.net MCP integration is immediately available to all customers **at no additional cost**." — [wpnews.io](https://www.wpnews.io/rocket-net-launches-a-new-developer-hub-with-full-mcp-integration/)

**Assessment:** this validates ServerAlly's MCP thesis, but Rocket.net's MCP is bounded to
**its own hosting platform** (their sites, their API). It cannot manage a customer's
arbitrary Linux/Windows servers, and it has **no agentic safety layer** (no mission
runbooks, no verification gate, no approval flow) — it is a thin API surface for the
customer's AI. ServerAlly's differentiation is **any server, any provider, plus the
guarded agent**, not the MCP transport itself.

### 4.5 Praise & complaints

**Ratings:** Trustpilot **4.9/5** from 106+ reviews ([Trustpilot](https://www.trustpilot.com/review/rocket.net));
G2 5.0/5 but only 4 reviews and "the profile hasn't been actively managed for over a year"
([G2](https://www.g2.com/products/rocket-net/reviews)).

**Praise:** speed (Cloudflare Enterprise at every POP), fast + effective support, unlimited
free migrations, unlimited PHP workers ([wpbeginner](https://www.wpbeginner.com/hosting/onrocket/), [theblogmetrics](https://theblogmetrics.com/rocket-net-review/)).

**Complaints:**
- **Ownership / private-equity concerns** (a sustained critique):
  > "Ben will say just about anything if it means another acquisition check while leaving you for private equity." — [onlinemediamasters](https://onlinemediamasters.com/rocket-net-review/) (claims Rocket.net is integrated with hosting.com under World Host Group, backed by Oakley Capital)
- **Hardware age:** same review alleges Intel Xeon E5-2667 v2 CPUs "from 2013… discontinued and rank 400th+ in performance benchmarks," DDR3 RAM and PCIe 3.0 NVMe.
- **Bandwidth markup:** alleged "charging ~3-6x more for Cloudflare Enterprise bandwidth compared to competitors like FlyingCDN" (same).
- **Arbitrary limits:** "Rocket.net and hosting.com charge absurd amounts for arbitrary limits like bandwidth, visits, and websites" (Reddit, via [wpkube](https://www.wpkube.com/rocket-net-review/)).
- **Tight storage:** "only 20 GB on their Pro plan might feel tight" ([wpkube](https://www.wpkube.com/rocket-net-review/)).
- **No git deploy, limited control-panel customisation** — "developers wanting granular server control may find it restrictive" (same).
- **No email, no domain registration** ([bloggingx](https://bloggingx.com/rocket-net-review/)).
- **2026 reliability incidents:** one customer reported sites "down for almost a whole day on the Dutch node and a five-hour repair time on the Frankfurt node" ([hostadvice](https://ca.hostadvice.com/hosting-company/rocket-net-reviews/)).

### 4.6 Agency-specific features

**Agency plans start at $100/mo (Tier 1, 10 installs)** and add the **Agency Toolkit**:
1. **Fully white-labelled control panel, DNS, and CDN Cache plugin** (own logo + colours).
2. **Panel embeddable anywhere with HTML** — put the whole hosting UI inside your own site.
3. **Automated provisioning via API** — order approved → client in WP Admin "within seconds."
4. **Set your own pricing / packages** inside the Rocket.net panel.
5. **Multiple payment gateways** supported by the API without extra coding.
6. **WHMCS integration.**
7. **Public API** to build a fully custom control panel.

Separately, an **Agency Partner Program** (referral, not hosting) pays **15% lifetime
recurring**, free to join, no minimums, 60-day cookie, 60-day hold, PayPal (wire for
$1,000+) — vs a one-time $150 for the standard affiliate program
([rocket.net/agency-partner-program](https://rocket.net/agency-partner-program/)).

---

## 5. Kinsta (server-management / agency features only, per brief)

### 5.1 Positioning & buyer

Premium managed WordPress on Google Cloud. Buyer = **agencies and businesses who will pay a
premium for support + performance** and don't want to touch infrastructure.

### 5.2 Pricing — **BUNDLED**, gates on **WP installs + visits + storage + CDN bandwidth**

([kinsta.com/plans](https://kinsta.com/plans/))

**Single-site plans** (1 install each; annual = ~2 months free):

| Plan | Monthly | Annual | Storage | CDN bandwidth |
|---|---|---|---|---|
| Single 20GB / 35k | $35 | $30/mo ($350/yr) | 10 GB | 125 GB |
| Single 40GB / 65k | $50 | $42/mo ($500/yr) | 10 GB | 250 GB |
| Single 65GB / 125k | $90 | $75/mo ($900/yr) | 10 GB | 500 GB |
| Single 125GB / 315k | $170 | $142/mo ($1,700/yr) | 10 GB | 750 GB |
| Single 250GB / 500k | $290 | $242/mo ($2,900/yr) | 15 GB | 1,000 GB |
| Single 500GB / 750k | $375 | $313/mo ($3,750/yr) | 15 GB | 1,500 GB |

**Multi-site plans:**

| Plan | Monthly | Annual | Installs | Storage | CDN bandwidth |
|---|---|---|---|---|---|
| WP 2 | $70 | $59/mo ($700/yr) | 2 | 20 GB | 250 GB |
| WP 5 | $115 | $96/mo ($1,150/yr) | 5 | 30 GB | 500 GB |
| WP 10 | $225 | $188/mo ($2,250/yr) | 10 | 40 GB | 750 GB |
| WP 20 | $340 | $284/mo ($3,400/yr) | 20 | 50 GB | 1,000 GB |
| WP 40 | $450 | $375/mo ($4,500/yr) | 40 | 60 GB | 1,500 GB |

**Agency plans** (same install counts as WP tiers but **more storage/bandwidth** + agency perks):

| Plan | Monthly | Annual | Installs | Storage | CDN bandwidth |
|---|---|---|---|---|---|
| Agency 20 | $340 | $284/mo ($3,400/yr) | 20 | 50 GB | 1,000 GB |
| Agency 40 | $450 | $375/mo ($4,500/yr) | 40 | **100 GB** | 1,500 GB |
| Agency 60 | $675 | $563/mo ($6,750/yr) | 60 | **150 GB** | 2,500 GB |

**Trial:** "First month free on entry-level plans (Single 20GB, Single 35k, WP 2)"
([kinsta.com/plans](https://kinsta.com/plans/)). No permanent free tier.

**Expensive add-ons** (a major complaint driver, secondary source [onlinemediamasters](https://onlinemediamasters.com/kinsta-review/)):
- Redis caching: **$100 per site per month**
- Hourly backups: **$100 per site per month**
- PHP memory limit stuck at 256 MB "unless you're dropping $625/month for Single 1.25M visits"

### 5.3 Feature checklist

| Feature | Kinsta | Evidence |
|---|---|---|
| Server provisioning | **NO** — GCP-backed, not user-provisioned | — |
| Cloud provider integrations | **NO** — GCP only, not selectable | — |
| One-click app installs | **PARTIAL** — WordPress only *(Application/Database/Static-Site hosting was **removed from MyKinsta and the API on 2026-02-02**, moved to Sevalla)* | [apitracker/Kinsta](https://apitracker.io/a/kinsta) |
| Git deploy | **PARTIAL** — git available over SSH; **no built-in git-deploy UI** — you "create a deployment script that will access your site's container via SSH and pull the latest version of your repo" | [kinsta docs — git](https://kinsta.com/docs/wordpress-hosting/site-management/git/), [anchor.host](https://anchor.host/automatic-git-deploy-with-kinsta-via-ssh/) |
| Staging + clone/push-to-live | **YES** — "One-click staging environment"; "push live with confidence"; site/environment cloning | [mykinsta](https://kinsta.com/mykinsta/), [wordpress-hosting](https://kinsta.com/wordpress-hosting/) |
| PHP version mgmt | **YES** | [wordpress-hosting](https://kinsta.com/wordpress-hosting/) |
| SSL | **YES** — included | [wordpress-hosting](https://kinsta.com/wordpress-hosting/) |
| DNS | **YES** — Kinsta DNS *(Amazon Route 53-powered — exact current backing **UNVERIFIED**)* | [agency-hosting](https://kinsta.com/agency-hosting/) |
| Databases | **YES** — one-click phpMyAdmin; **search-and-replace database content** in the dashboard | [mykinsta](https://kinsta.com/mykinsta/) |
| Email hosting | **NO** | — |
| Cron | **UNVERIFIED** (WP cron control likely) | — |
| Firewall / WAF | **YES** — "Firewall, DDoS protection, and proactive monitoring are included"; enterprise DDoS | [wordpress-hosting](https://kinsta.com/wordpress-hosting/) |
| Malware scanning | **PARTIAL** — Kinsta has a hack-fix pledge; automated scanning specifics **UNVERIFIED** | — |
| Backups | **YES** — daily automatic, **14-day retention**; hourly available as a **$100/site/mo** add-on | [mykinsta](https://kinsta.com/mykinsta/); add-on price via [onlinemediamasters](https://onlinemediamasters.com/kinsta-review/) |
| Monitoring + alerts | **YES (strong)** — **APM** ("identify slow queries, plugins, and performance bottlenecks"), uptime monitoring, site health monitoring, resource usage analytics | [mykinsta](https://kinsta.com/mykinsta/) |
| Log viewer | **YES** | [mykinsta](https://kinsta.com/mykinsta/) |
| File manager | **YES** — "File manager for direct site file access" | [mykinsta](https://kinsta.com/mykinsta/) |
| SSH / SFTP user mgmt | **YES (strong)** — SSH on **all** plans; granular SFTP/SSH controls: **disable access, auto-expire passwords, enable/disable password auth, download config for third-party apps**; manageable **via the API** | [kinsta docs — SSH](https://kinsta.com/docs/wordpress-hosting/connect-to-ssh/), [community](https://community.kinsta.com/t/manage-ssh-and-sftp-access-with-the-kinsta-api/5582) |
| **Teams + roles** | **YES (strongest in group)** — **unlimited users**, **company-level AND site-level roles**, SAML SSO, 2FA, activity tracking, per-site/per-staging grants | [mykinsta](https://kinsta.com/mykinsta/), [kinsta docs — user management](https://kinsta.com/docs/company-settings/user-management/) |
| **White-label** | **PARTIAL — the notable weakness.** WP admin only: disable the "Kinsta Cache" menu item + remove the "hosting with Kinsta" footer, via wp-config.php. **"Kinsta doesn't currently support white-labeling the MyKinsta hosting dashboard."** | [kinsta.com/blog/white-label-hosting](https://kinsta.com/blog/white-label-hosting/) |
| **Client billing / reselling** | **NO built-in.** Kinsta's own white-label article does not address client sub-accounts or separate billing; the model is "agencies resell hosting to clients directly," using granular access controls instead | [kinsta.com/blog/white-label-hosting](https://kinsta.com/blog/white-label-hosting/) |
| Marketplace / templates | **UNVERIFIED** | — |
| WP: plugin/theme updates | **YES** — automatic plugin + theme updates **with rollback** | [mykinsta](https://kinsta.com/mykinsta/) |
| WP: visual regression testing | **UNVERIFIED** | — |
| WP: WP-CLI | **YES** — "pre-installed on every Kinsta server, ready the moment you connect via SSH" | [kinsta docs — WP-CLI](https://kinsta.com/docs/wordpress-hosting/site-management/wordpress-wp-cli/) |
| WP: multisite | **YES** — multisite hosting option | [wordpress-hosting](https://kinsta.com/wordpress-hosting/) |
| Migration tools | **YES** — **unlimited free migrations** on all paid plans | [agency-hosting](https://kinsta.com/agency-hosting/) |
| API | **YES** — Kinsta REST API: list sites, **add new WordPress sites automatically**, scheduled tasks, retrieve data, manage SSH/SFTP access | [kinsta docs — API](https://kinsta.com/docs/kinsta-api/), [api-docs.kinsta.com](https://api-docs.kinsta.com/) |
| CLI | **PARTIAL** — WP-CLI yes; a **community** `kinsta-cli` exists on GitHub, not official | [github.com/calljacob/kinsta-cli](https://github.com/calljacob/kinsta-cli) |
| Mobile app | **NO** | — |
| **AI features** | **UNVERIFIED / minimal** — no AI features surfaced on Kinsta's own hosting or MyKinsta pages | — |

**Bulk actions across multiple sites**, site transfer tool, site renaming, site labelling,
Redirects Manager, image optimisation, edge caching, and an 8-language dashboard are all
confirmed ([mykinsta](https://kinsta.com/mykinsta/), [agency-hosting](https://kinsta.com/agency-hosting/)).

### 5.4 Praise & complaints

**Ratings:** Trustpilot **4.8/5**, 1,000+ reviews (one mid-2025 source says 4.4)
([Trustpilot](https://www.trustpilot.com/review/kinsta.com), [checkthat.ai](https://checkthat.ai/brands/kinsta/reviews)).

**Praise:** support quality ("top-notch… agents always being super helpful"), performance,
the MyKinsta dashboard UX.

**Complaints — price and metered limits dominate:**
- > "What makes Kinsta expensive are limits on PHP workers and visit counts" — [onlinemediamasters](https://onlinemediamasters.com/kinsta-review/)
- > "Quite a few additional charges for services that would otherwise be free or standard elsewhere" and "True costs per site cleverly disguised in their pricing structure" — Reddit, via [wpressblog](https://www.wpressblog.com/kinsta-hosting-review/)
- "Sudden price hikes on custom plans show why some long term customers are losing trust in Kinsta's pricing model" ([wpressblog](https://www.wpressblog.com/kinsta-hosting-review/)).
- "Power users are frustrated with aggressive pricing changes and **resource cuts that directly impact site stability**" (same).
- Billing team "IMPOSSIBLE to reach," email responses taking "a day or more" ([checkthat.ai](https://checkthat.ai/brands/kinsta/reviews)).
- Support capacity concerns as they grow (same).

### 5.5 Agency-specific features

From [kinsta.com/plans](https://kinsta.com/plans/) and [kinsta.com/agency-hosting](https://kinsta.com/agency-hosting/):
1. **Higher storage/bandwidth at the same install count** vs the equivalent WP tier (Agency 40 = 100 GB vs WP 40 = 60 GB).
2. **"Up to $10,000 in hosting credits."**
3. **Listing in the Kinsta Agency Directory** (lead generation).
4. **Unbranded WordPress admin experience** (partial white-label — see above).
5. **Free hosting for the agency's own site.**
6. **Dedicated account management.**
7. **Unlimited team members** with company-level + site-level roles.
8. Site transfer / rename / label tooling for ownership handover.
9. **Agency Partner Program** (separate): lifetime commissions on referrals, co-marketing, lead referrals from Kinsta sales.

**Gap:** no client billing, no client sub-accounts, no dashboard white-label. Kinsta
competes on quality + credits + directory leads, not on reseller infrastructure.

---

## 6. Nexcess / Liquid Web

> **Sourcing caveat:** `shop.nexcess.net`, `www.nexcess.net/*` and `liquidweb.com/pricing`
> all blocked direct fetches (403 / SSL handshake failure / truncated). **Every price below
> is from a secondary source and should be re-verified on the vendor site before being used
> in a public comparison.**

### 6.1 Positioning & buyer

Premium managed WordPress / WooCommerce / Magento. Buyer = **SMB and agencies, with the
real differentiation in ecommerce operations** ([webhostwatch](https://www.webhostwatch.com/review_nexcess_2026)).
**Branding note:** "In late 2025, Nexcess hosting was fully integrated into the Liquid Web
branding, with Nexcess becoming the parent brand while Liquid Web now operates as a focused
sub-brand for SMBs and agencies" ([googiehost](https://googiehost.com/blog/nexcess-review/)) — treat the
two names as one product line.

### 6.2 Pricing — **BUNDLED**, gates on **sites + storage + bandwidth** (SECONDARY SOURCES)

| Plan | Monthly | Sites | Storage | Bandwidth |
|---|---|---|---|---|
| Spark | **$19–$21/mo** (sources differ) | 1 | 15 GB | 2 TB |
| Maker | **$79/mo** | 5 | 40 GB | 3 TB |
| Designer | **$109/mo** | 10 | 60 GB | UNVERIFIED |
| Builder | **$149/mo** | 25 *(some sources say 10)* | 100 GB | UNVERIFIED |
| Producer | **$299/mo** | 50 *(some sources say 20)* | 300 GB | UNVERIFIED |
| Executive | **$549/mo** | 100 | 500 GB | UNVERIFIED |
| Enterprise | **$999/mo** *(one source says $602 or $1,095)* | 250 | 800 GB | UNVERIFIED |

Sources: [keevee](https://www.keevee.com/liquid-web-pricing), [cybernews](https://cybernews.com/best-web-hosting/liquid-web-review/pricing/), [propicked](https://propicked.com/hosting/nexcess/pricing), [ecommerceparadise](https://ecommerceparadise.com/liquid-web-pricing/).

**Site-count conflicts between sources are real and unresolved** — do not quote a site limit
without checking the live page.

Liquid Web's own announcement confirms only the entry point:
> "**Entry-level price: $19**" for both Managed WordPress and Managed WooCommerce, with new
> features including "basic email, powerful auto-scaling, more storage, and more bandwidth."
> — [liquidweb.com/blog/new-managed-wordpress-and-managed-woocommerce-plans](https://www.liquidweb.com/blog/new-managed-wordpress-and-managed-woocommerce-plans/)

**Trial:** no free tier; promotional first-term discounts (e.g. "$5.25 for the first three
months" annual, "three months of premium hosting" — [keevee](https://www.keevee.com/liquid-web-pricing)).
Notably a **99.999% uptime guarantee** is advertised ([liquidweb](https://www.liquidweb.com/wordpress/hosting/best-managed-wordpress-hosting/)).

### 6.3 Feature checklist

| Feature | Nexcess/Liquid Web | Evidence |
|---|---|---|
| Server provisioning | **NO** for managed WP (Liquid Web sells VPS/dedicated as separate products) | — |
| Cloud provider integrations | **NO** | — |
| One-click app installs | **YES** — WordPress, WooCommerce, Magento | [webhostwatch](https://www.webhostwatch.com/review_nexcess_2026) |
| Git deploy | **PARTIAL** — git access included on every tier; automated deploy pipeline UNVERIFIED | [pluginbeginner](https://pluginbeginner.com/deals-reviews/nexcess-managed-wordpress-hosting-2025-benchmarks-features-use-cases-developers-trust/) |
| Staging + clone/push-to-live | **YES** — dev/staging environments on all plans | [nexcess help](https://www.nexcess.net/help/nexcess-managing-dev-staging-environments/) |
| PHP version mgmt | **YES** | [pluginbeginner](https://pluginbeginner.com/deals-reviews/nexcess-managed-wordpress-hosting-2025-benchmarks-features-use-cases-developers-trust/) |
| SSL | **YES** — free SSL all tiers | [propicked](https://propicked.com/hosting/nexcess/pricing) |
| DNS | **UNVERIFIED** | — |
| Databases | **YES** — "full database access… even on the lowest-tier plan" | [pluginbeginner](https://pluginbeginner.com/deals-reviews/nexcess-managed-wordpress-hosting-2025-benchmarks-features-use-cases-developers-trust/) |
| **Email hosting** | **YES** — "basic email" added to plans; one review claims "unlimited email accounts" **(UNVERIFIED)** | [liquidweb blog](https://www.liquidweb.com/blog/new-managed-wordpress-and-managed-woocommerce-plans/) |
| Cron | **UNVERIFIED** | — |
| Firewall / WAF | **PARTIAL** — **iThemes/Solid Security Pro bundled** (a plugin-level, not server-level, WAF) | [propicked](https://propicked.com/hosting/nexcess/pricing) |
| Malware scanning | **PARTIAL** — via Solid Security Pro | same |
| Backups | **YES** — daily backups; retention **UNVERIFIED** | [speckyboy](https://speckyboy.com/managed-wordpress-hosting/) |
| Monitoring + alerts | **PARTIAL** — "plugin performance monitoring"; uptime alerting UNVERIFIED | [speckyboy](https://speckyboy.com/managed-wordpress-hosting/) |
| Log viewer | **UNVERIFIED** | — |
| File manager | **UNVERIFIED** (SFTP confirmed) | — |
| SSH / SFTP | **YES** — "Git, SSH, SFTP, and full database access… no 'developer upgrade' needed" | [pluginbeginner](https://pluginbeginner.com/deals-reviews/nexcess-managed-wordpress-hosting-2025-benchmarks-features-use-cases-developers-trust/) |
| Teams + roles | **UNVERIFIED** | — |
| **White-label** | **UNVERIFIED** — a Liquid Web partner/reseller program exists but was not confirmable | — |
| **Client billing / reselling** | **UNVERIFIED** | — |
| Marketplace / templates | **UNVERIFIED** | — |
| **WP: plugin updates + VISUAL COMPARISON** | **YES — standout feature.** "Visual comparison testing when applying updates… a unique feature that most other hosts don't offer" | [designbombs](https://www.designbombs.com/nexcess-review/), [pluginbeginner](https://pluginbeginner.com/deals-reviews/nexcess-managed-wordpress-hosting-2025-benchmarks-features-use-cases-developers-trust/) |
| WP: WP-CLI | **YES** | [pluginbeginner](https://pluginbeginner.com/deals-reviews/nexcess-managed-wordpress-hosting-2025-benchmarks-features-use-cases-developers-trust/) |
| WP: multisite | **UNVERIFIED** | — |
| Migration tools | **YES** — free migrations | [websiteplanet](https://www.websiteplanet.com/web-hosting/nexcess/) |
| API | **UNVERIFIED** | — |
| CLI | **PARTIAL** — WP-CLI only | — |
| Mobile app | **NO** | — |
| **AI features** | **UNVERIFIED** — none surfaced | — |

Other confirmed features: **free auto-scaling for the first 24 hours** (traffic-spike
protection), **250 GB free CDN**, **automatic image compression**
([websiteplanet](https://www.websiteplanet.com/web-hosting/nexcess/), [propicked](https://propicked.com/hosting/nexcess/pricing)).

### 6.4 Praise & complaints

**Praise:** long-time customers call it "the best managed hosting for WordPress, with no
downtime or issues"; ecommerce operations tooling is the real value
([techwithaisha](https://techwithaisha.com/liquid-web-nexcess-review/), [webhostwatch](https://www.webhostwatch.com/review_nexcess_2026)).

**Complaints — support degradation and billing surprises:**
- > "with their migration to Nexcess, they decided to drop their heroic support and michigan based support staff in favour of AI and chat support, with the chat support seeming to be more interested in closing the case quickly rather than fixing the issue" — [Trustpilot](https://www.trustpilot.com/review/liquidweb.com?page=3)
- **Billing shock:** a customer "signed up for a Nexcess plan at $9.60 a month in June 2025, but got hit with a $141.60 charge, including a $132 fee they didn't agree to or see coming, with no heads-up or explanation" ([Trustpilot](https://www.trustpilot.com/review/liquidweb.com?page=3)).
- Long-term decline: "the service has progressively worsened over 9+ years, with the cost of hosting increasing at the same time" (same).
- "Slow support, excessive verification checks, average CDN performance, and lack of Indian servers" ([diggitymarketing](https://diggitymarketing.com/web-hosting/nexcess-review/)).

### 6.5 Agency-specific features

**Weakest agency story in the group.** No confirmed white-label, client billing, or client
dashboards. Positioning is "Liquid Web now operates as a focused sub-brand for SMBs and
agencies" ([googiehost](https://googiehost.com/blog/nexcess-review/)) but the productised agency
tooling could not be verified. Agencies buy the larger site-count tiers and the visual-
comparison update testing.

---

## 7. Adjacent agency-oriented platforms (found during research)

These are not hosts but compete for the same agency budget and are useful pricing precedents.

### 7.1 WPMU DEV — the fullest white-label/reseller stack found

([wpmudev.com/pricing](https://wpmudev.com/pricing/), [wpmudev.com/reseller](https://wpmudev.com/reseller/))

| Plan | Monthly | Annual | Sites | CDN | Backup | White-label / reseller |
|---|---|---|---|---|---|---|
| Pro Basic | $5 → **$3/mo** (40% off) | $60 → $36/yr | 1 | 50 GB | 5 GB | ✗ |
| Pro Standard | $10 → **$5/mo** | $100 → $60/yr | 3 | 100 GB | 10 GB | ✓ (white-label client billing) |
| Pro Plus | $20 → **$10/mo** | $200 → $120/yr | 10 | 250 GB | 20 GB | ✓ |
| **Premium** | $200 → **$100/mo** | $2,000 → $1,200/yr (first year) | **Unlimited** | 500 GB | 50 GB | **✓ "Fully White Label"**, automated + manual reseller, integrated CRM, VIP support, team management, **$200/yr hosting credit** |

- **0% platform commission** on white-label client billing ([wpmudev.com/blog/wpmu-dev-white-label-reseller-hosting](https://wpmudev.com/blog/wpmu-dev-white-label-reseller-hosting/)).
- **The Hub Client** plugin rebrands the hosting dashboard as the agency's own.
- Stripe connect, import existing clients/products/plans, recurring + one-off billing plans.
- Domain reselling across **270+ TLDs**.
- **No free tier.**

> **Key precedent:** white-label unlocks at **$5/mo (Pro Standard)** — cheap. *Full* white
> label + reseller automation is the **$100/mo Premium** wall. This is the clearest example
> in the research of "white-label as the pro-tier hook."

### 7.2 WP Umbrella — the anti-tiering precedent

([wp-umbrella.com/pricing](https://wp-umbrella.com/pricing/))

- **One tier: €1.99 / $2.19 per site per month.** "No site minimums. Add or remove sites anytime."
- Add-ons: Security **€2/site/mo**, Hourly Backups **€2.49/site/mo**.
- **14-day free trial, full feature access, no credit card.**
- Includes: daily/weekly/monthly backups, vulnerability monitoring every 6h with one-click fixing, security hardening toggles, Site Health, uptime + PHP error + performance monitoring, **safe updates with visual regression testing**, **white-label client reports**.
- Explicit anti-tiering positioning:
  > "We don't lock features behind tiers, charge per team member, or add hidden limits."

### 7.3 ManageWP (GoDaddy)

Free tier for basic updates; **per-site paid add-ons**: backups **$2/site/mo**, **white
label $1/site/mo**, uptime monitoring **$1/site/mo**
([oddjar](https://oddjar.com/wordpress-site-management-plugins-2026-comparison/)).
White-label is priced as a **$1/site à-la-carte item** — the cheapest white-label in the market.

### 7.4 Others noted (not deeply researched)

- **InstaWP** — "managed hosting layer, management dashboard, migration tools, WaaS platform, and AI capability… from one place," with an **Agency Program** offering pricing, cashback, support ([instawp.com](https://instawp.com/wordpress-hosting-models-for-agencies/)).
- **MainWP** — self-hosted, open-source, **unlimited sites**.
- **InfiniteWP** — free self-hosted base + tiered premium licensing.
- **Atarim** — collaboration layer; Rocket.net partnered with them for "all-in-one agency management and collaboration" ([rocket.net blog](https://rocket.net/blog/agency-management-and-collaboration/)).

---

## 8. Cross-vendor: what is gated behind "agency/pro" tiers

This is the answer to the pro-tier design question. Ranked by how consistently each is
agency-gated across Group B:

| Gated capability | GridPane | Cloudways | Enhance | Rocket.net | Kinsta | Nexcess | WPMU DEV |
|---|---|---|---|---|---|---|---|
| **White-label control panel** | unclear | partial (invoices) | ✓ all tiers | **✓ Agency only** | ✗ (never) | ? | **✓ Premium ($100/mo)** |
| **Client billing / invoicing** | ✗ | **✓ separate SKU** ($0/4.99/13.99) | ✗ native (4 integrations) | **✓ Agency only** | ✗ | ? | **✓ Standard ($5/mo)+** |
| **Client sub-accounts / dashboards** | ✗ | ✓ (role scoping) | **✓ multi-tier resellers** | **✓ Agency only** | partial (role scoping) | ? | ✓ |
| **Client reporting** | ✗ | **✓ metered by billing tier** | ✗ | ? | ✗ | ? | ✓ |
| **Team roles / permissions** | partial | ✓ all tiers | ✓ all tiers | ✓ | **✓ unlimited users, all tiers** | ? | ✓ Premium |
| **Automated provisioning API** | ✓ | ✓ | ✓ | **✓ Agency (order → WP admin in seconds)** | ✓ | ? | ✓ |
| **Higher storage/bandwidth at same site count** | n/a | n/a | n/a | ✓ Agency | **✓ Agency 40/60** | n/a | n/a |
| **Directory listing / lead-gen** | ✗ | ✗ | ✗ | ✗ | **✓ Agency Directory** | ? | ✓ Agency Partners |
| **Hosting credits** | ✗ | ✗ | ✗ | ✗ | **✓ up to $10,000** | ? | ✓ $200/yr |
| **Dedicated account manager / higher SLA** | ✓ Bespoke ($2k/yr) | ✓ ($25/mo add-on) | ✗ | ✓ Enterprise (Slack + phone) | ✓ Agency | ? | ✓ VIP |
| **Customer impersonation** | ✗ | ✗ | **✓ (unique)** | ✗ | ✗ | ? | ? |
| **Referral/partner commission** | ✓ (partnerships) | ✗ | ✗ | **✓ 15% lifetime** | ✓ lifetime | ? | ✓ |

**The five things that are ALWAYS agency-gated, never in a base tier:**
1. **White-label branding of the control panel** (Rocket.net, WPMU DEV Premium — and Kinsta's refusal to offer it at any price is a live complaint).
2. **Client billing / invoicing** (Cloudways sells it as a separate SKU; Rocket.net gates it to Agency plans).
3. **Client-facing dashboards / sub-accounts.**
4. **Automated provisioning from an order** (order approved → client live).
5. **Directory listing / lead referral / hosting credits** — pure commercial perks, zero engineering cost, high perceived value.

**The three things that are NEVER gated** (present on the cheapest tier at every vendor):
- SSL, backups, staging.
- SSH/SFTP + WP-CLI (Nexcess explicitly markets "no developer upgrade needed").
- Free migrations.

> Gating a safety feature (backup, SSL, staging) is **not done by anyone in this group.**
> This corroborates ServerAlly's existing "never gate safety features" rule
> (Pricing v2 decision, 2026-07-03).

---

## 9. Implications for ServerAlly

**On pricing metric.** Group B strongly confirms the Group-A finding: **nobody meters usage
of the management product.** They gate on servers, sites, storage, or bandwidth. The two
management-only vendors have both moved *away* from per-server subscriptions:
- Enhance: **$0.15 per website, zero per-server fee**, $10/mo minimum.
- GridPane: **free for 25 sites**, monetise via managed servers.

This is a real pressure on a naive "$X per server" plan: at $19/mo GridPane sells a whole
*managed server*, and Enhance's panel for a 30-site agency costs **$10/mo** (the minimum).
A per-server management fee has to justify itself against those anchors.

**On the free tier.** GridPane's **free-forever 25 sites (no support)** and Cloudways'
free Client Billing tier show the pattern: give away the *product*, charge for *support*,
*managed infrastructure*, and *the commercial layer*. ServerAlly's Free plan (2 servers)
is stingier than GridPane's free tier by this measure.

**On agency/pro-tier design.** The five always-gated items in §8 are the pro-tier menu.
ServerAlly today has **none** of white-label, client billing, client dashboards, or
automated provisioning-from-order. Team roles it already has (and those are *not* gated
anywhere in this group — Kinsta gives unlimited users on every plan, so gating teams would
be off-market).

**On the AI moat — narrower than it looks, but real.**
- **Rocket.net already ships an MCP server + native Claude/ChatGPT/Gemini, free to all customers**, covering "every Rocket.net capability" including billing and user management. The MCP transport is **not** a differentiator on its own any more.
- **Cloudways ships AI Copilot** (detect issue → 1-click SmartFix) but **meters it in credits** — $9.99/mo for 12 credits, free above a $100 invoice. That is precisely the credit model ServerAlly's Pricing v3 declared **forbidden**, and it is worth watching whether Cloudways customers complain about it.
- **GridPane, Enhance, Kinsta, and Nexcess have no AI features at all** — four of seven vendors are completely absent from this space.

The defensible ground is what Rocket.net's MCP structurally *cannot* do: it manages
**only Rocket.net-hosted sites via their own API**. It has no cross-provider reach (no
arbitrary VPS, no Windows, no other panels), and no agentic safety layer — no mission
runbooks, no read-only verification gate, no approval flow, no injection defence. ServerAlly's
claim should be **"any server you own, with a guarded agent,"** not "we have MCP."

**On the loudest complaints across all seven vendors** — these are the churn levers:
1. **Support degradation after acquisition/growth** (Cloudways→DigitalOcean, Nexcess→Liquid Web, Kinsta, Rocket.net→World Host Group). Every single bundled host in this group has this complaint.
2. **Pricing instability and surprise charges** (GridPane "2-3 times per year," Kinsta "sudden price hikes," Nexcess "$132 fee they didn't agree to").
3. **Metered limits that feel arbitrary** (Kinsta PHP workers + visits; Rocket.net bandwidth/visits/sites; Cloudways bandwidth overages).
4. **Too technical for non-technical users** (GridPane specifically) — the one complaint ServerAlly's whole product thesis is built to answer.

---

## Sources

All URLs cited inline above. Primary vendor pages successfully retrieved:
[gridpane.com/pricing](https://gridpane.com/pricing/) ·
[gridpane.com/plans](https://gridpane.com/plans/) ·
[gridpane.com/plans/core](https://gridpane.com/plans/core/) ·
[gridpane.com/peakfreq/pricing](https://gridpane.com/peakfreq/pricing/) ·
[gridpane.com/kb/peakfreq-managed-hosting](https://gridpane.com/kb/peakfreq-managed-hosting/) ·
[gridpane.com/kb/core-plan-questions-and-answers](https://gridpane.com/kb/core-plan-questions-and-answers/) ·
[gridpane.com/features](https://gridpane.com/features/) ·
[cloudways.com/en/pricing.php](https://www.cloudways.com/en/pricing.php) ·
[cloudways.com/en/autonomous.php](https://www.cloudways.com/en/autonomous.php) ·
[cloudways.com/en/client-billing.php](https://www.cloudways.com/en/client-billing.php) ·
[cloudways.com/en/reseller-hosting.php](https://www.cloudways.com/en/reseller-hosting.php) ·
[cloudways.com/en/hosting-for-agencies.php](https://www.cloudways.com/en/hosting-for-agencies.php) ·
[enhance.com](https://enhance.com/) ·
[enhance.com/pricing](https://enhance.com/pricing) ·
[enhance.com/features](https://enhance.com/features) ·
[enhance.com/product/features](https://enhance.com/product/features) ·
[enhance.com/docs](https://enhance.com/docs/) ·
[enhance.com/docs/billing-integrations](https://enhance.com/docs/billing-integrations/) ·
[rocket.net](https://rocket.net/) ·
[rocket.net/pricing](https://rocket.net/pricing/) ·
[rocket.net/solutions/ai-hosting-for-wordpress](https://rocket.net/solutions/ai-hosting-for-wordpress/) ·
[rocket.net/solutions/wordpress-reseller-hosting](https://rocket.net/solutions/wordpress-reseller-hosting/) ·
[rocket.net/agency-partner-program](https://rocket.net/agency-partner-program/) ·
[kinsta.com/plans](https://kinsta.com/plans/) ·
[kinsta.com/mykinsta](https://kinsta.com/mykinsta/) ·
[kinsta.com/wordpress-hosting](https://kinsta.com/wordpress-hosting/) ·
[kinsta.com/agency-hosting](https://kinsta.com/agency-hosting/) ·
[kinsta.com/blog/white-label-hosting](https://kinsta.com/blog/white-label-hosting/) ·
[kinsta.com/docs/kinsta-api](https://kinsta.com/docs/kinsta-api/) ·
[liquidweb.com/blog/new-managed-wordpress-and-managed-woocommerce-plans](https://www.liquidweb.com/blog/new-managed-wordpress-and-managed-woocommerce-plans/) ·
[wpmudev.com/pricing](https://wpmudev.com/pricing/) ·
[wp-umbrella.com/pricing](https://wp-umbrella.com/pricing/)

**Blocked to direct fetch (secondary sources used, flagged inline):**
shop.nexcess.net, www.nexcess.net/*, liquidweb.com/pricing, trustpilot.com/*, g2.com/*,
reddit.com/*, support.cloudways.com/*.

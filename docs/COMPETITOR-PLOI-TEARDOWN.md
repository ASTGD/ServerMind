# Ploi teardown — a walk through the real product

> **Captured 2026-07-17** from a live Ploi trial account (`ceo@astgd.com`, 5-day trial,
> onboarding 0/5, no servers created). **Read-only walkthrough** — no onboarding step was
> executed: every one is side-effectful (provisions paid infra, grants OAuth to the user's
> GitHub, takes payment, or changes account 2FA).
>
> **Purpose:** a feature-borrow shortlist for the PM discussion. Ploi is our closest
> per-server competitor and the one whose MCP model we're copying
> ([MCP-SERVER-PLAN.md](MCP-SERVER-PLAN.md)). Pricing evidence lives in
> [PRICING-METRIC-RESEARCH.md](PRICING-METRIC-RESEARCH.md).
>
> **Caveat:** an empty trial account. Server/site detail UIs, the real deploy flow and the
> team-management screens were not observable without provisioning a paid server.

---

## 1. Information architecture

**Main nav:** Dashboard · **Team switcher** · Servers · Sites · Status pages · Projects ·
Scripts · Backups · Marketplace — then Profile · Subscription · Documentation · Support.

**Profile sub-nav (15 items):** Profile · Source control · Server providers · SSH keys ·
API keys · Integrations · Notification channels · Backup configurations · Webserver
templates · Security · Settings · Invoices (`/orders`) · Subscription · Referrals ·
**Wrapped** (`/panel/wrapped`).

**Everything is team-scoped.** Empty states read *"**Sharwat's Team** doesn't have any
servers yet"* — the **team**, not the user, owns servers and sites. A team switcher sits
at the top of the nav. (We model servers as user-owned with team *access* layered on —
a real architectural difference worth discussing.)

## 2. Onboarding — "Finish up your account (0/5)"

A checklist card on the dashboard, with a **`Skip »`** and a **progress counter**:

| # | Step | Label |
|---|---|---|
| 1 | Add a Git provider | *Optional but recommended* |
| 2 | Add a server provider | *Optional but recommended* |
| 3 | **Create your first server** | — |
| 4 | Upgrade your plan | — |
| 5 | Enable 2FA | *Optional but recommended* |

**Why it works:** 3 of 5 are explicitly optional, so only **one** step feels mandatory.
Progress is visible, and the whole thing is skippable. Low pressure, one obvious path.
A persistent yellow banner runs sitewide: *"You are currently on a trial with 5 days
left…"*

## 3. Create server — one opinionated form

- **Providers:** DigitalOcean · Hetzner · Vultr · Linode · Amazon EC2 · UpCloud · Krystal ·
  Hostinger — **greyed out until linked**, but **"Custom server" is enabled by default**,
  so a user with no cloud account is *never blocked*.
- **Details:** Credentials · Name (placeholder is an auto-generated friendly name, e.g.
  `iridescent-grove`) · Server OS (Ubuntu 24.04) · IP version (IPv4 default, with an
  inline note that IPv4 may cost extra at some providers) · Server type (+ *"Tell me more
  about the available server types"*).
- **Stack, all pre-selected:** NGINX · PHP 8.5 · MySQL 8.4 (LTS) · Redis cache.
- Optional **"Install Ploi Monitoring"** checkbox.

The whole stack is chosen on **one page** with sensible defaults. The user really only
picks plan + region.

## 4. Area-by-area

| Area | What it is |
|---|---|
| **Marketplace** | A **community script marketplace** with **★ ratings** and **comment counts**. Filter by 4 types: *Scripts · Webserver templates · Deployment scripts · 1-click installation*. Plus "My scripts" and "Create". Real listings seen: *WHMCS deployment*, *Paperclip*, *Quick security scan*, *Nuxt 4 + Laravel 13 SSR (PM2)*, *Laravel Multi-Tenant 1-Click Deploy*, *Upgrade node to v.24* (★5.0), *NGINX fix CVE-2026-1642*. |
| **Scripts** | *"Create a script you can run, **schedule**, or **wire up to server events**."* — event-triggered automation. |
| **Projects** | *"Create a project here and separate sites & servers easily"* — a grouping layer above both. |
| **Backups** | A **global** view across servers, split **Databases / Sites**. |
| **Status pages** | Public status pages. **Unlimited-tier only** — clicking it silently **redirects to the Subscription page**. |
| **Source control** | GitHub · Bitbucket · GitLab **+ self-hosted GitLab**. Warns up front: *"make sure you're logged in to the correct GIT account."* |
| **Server providers** | Radio list, each with a **"Guide"** link. A **Label** field ("if you have more than one account per provider") + API key. Notes: *"If you need to specify a IP that is whitelisted you can view our used IP **here**."* |
| **API keys** | Scopes: **Full access / Read only / Custom** ("pick exactly which permissions this key gets") + Advanced options. |
| **Connected applications** | ⭐ **Where MCP lives** — see §5. |
| **Integrations** | Dropbox · Google Drive (backup targets) · Telegram (notifications) · DNS providers. Each notes *"only usable for users with paid plans."* |
| **Notification channels** | Type (Slack, …) + Label + Webhook URL, plus a **"Bulk assign notifications"** action. |
| **Webserver templates** | Custom nginx configs with variables **`{DOMAIN}` `{SYSTEM_USER}` `{DIRECTORY}` `{SOCKET}`**, pre-filled with a hardened TLS 1.2/1.3 config. |
| **Security** | ⭐ **Sudo mode** — see §5. |
| **Settings** | Newsletter · keyboard shortcuts · redirect-to-panel · invoice emails · **Theme (Light/Dark/System)** · **Nav layout (Sidebar/Top)** · Notification position. Tabs: Profile / Servers & Sites. |
| **Referrals** | A personal referral URL → **15 days extra on your plan** per signup that purchases. |
| **Wrapped** | *"Your 2025 Wrapped is ready to be unwrapped! See your year in review with deployments, servers, and achievements."* + a year selector + "Generate my Wrapped". |
| **404 page** | A joke terminal: `$ ssh into.reality` → *"Connection failed: Page not found in production, staging, or developer's imagination."* |

## 5. The two findings that change our plans

### 5.1 MCP lives under API keys — not as a feature of its own

**Profile → API keys → "Connected applications"**, verbatim:

> *"Applications you have authorized through OAuth, **such as MCP clients like Claude or
> Cursor**. Revoking an application immediately blocks its access to your account."*

**MCP has no nav entry at all**, and — notably — **does not appear in their in-app plan
comparison**, despite their marketing page claiming it's *"included in the Pro plan and
up"*. They don't lead with it.

**→ Change to [MCP-SERVER-PLAN.md](MCP-SERVER-PLAN.md) Phase 4.** We specced a dedicated
*"Connect your AI"* settings page. Ploi's model is better: OAuth-connected apps sit
**beside API keys**, because they are the same concept — *programmatic access to your
account*. One surface, two tabs. Adopt it.

**→ And adopt the scope model.** *Full access / Read only / Custom* is exactly the shape
our MCP tool catalogue needs. A "Read only" MCP connection is a genuinely good default for
a customer wiring an AI to their production servers for the first time.

### 5.2 Sudo mode on sensitive pages

Opening **Security** demands the password again:

> *"Enter your password to access this protected page. After successful validation we will
> not ask you for these details for another **2 hours**."*

We hold **root credentials for other people's production servers** and have **no such
gate**. This is cheap, standard, and it belongs on our Security/2FA screens and anywhere
credentials or plan overrides are touched.

## 6. Borrow shortlist — ranked for tomorrow

**Tier 1 — do these**

1. **Connected applications tab** beside API keys (§5.1) — redesigns MCP Phase 4, *reduces* work.
2. **API/MCP scopes: Full / Read-only / Custom** (§5.1) — read-only is the right first-connection default.
3. **Sudo mode** (§5.2) — we're a credential vault with no re-auth gate.
4. **Publish our egress IP** in the UI ("view our used IP here"). We already know this bites: our own `150.228.135.29` gets flagged as an attacker in scans (`memory/serverally-egress-ip-self-footprint.md`), and customers with firewalls need it.
5. **Onboarding checklist** — 0/N counter, `Skip »`, "Optional but recommended" on all but one step.

**Tier 2 — strong, already on our backlog**

6. **Marketplace** with ratings + comments — our backlog has *"Command marketplace (community scripts)"* and *"Script rating + comments"*. Ploi proves the shape, incl. the 4 content types.
7. **Webserver templates** with `{DOMAIN}`-style variables — our backlog has *"NGINX config builder"*. Note their template variables ≈ our playbook `{{HOST}}` placeholders; same idea, one layer lower.
8. **Scripts wired to server events** — we have scheduled + manual, not event-triggered.
9. **Per-provider "Guide" links** on the provider picker — tiny, removes the biggest add-a-provider stumble.

**Tier 3 — worth discussing**

10. **Projects** — a grouping layer over servers + sites. We have tags/categories; this is heavier and clearer for agencies.
11. **Wrapped** — a year-in-review. For us it could be genuinely strong: *"Ally ran 240 missions, quarantined 13 webshells, caught 2 miners, saved you N hours."* We have the mission/ledger data already.
12. **Referrals paying in plan-time** (15 days) rather than cash — no payout plumbing.
13. **Bulk assign notifications.**
14. **Settings: nav layout + theme + notification position** as user prefs.
15. **Auto-generated friendly names** (`iridescent-grove`) as the add-asset placeholder.
16. **"Custom server" always enabled** so an unlinked provider never blocks onboarding — we already do this well; confirm it stays true.
17. **Personality in the 404** — cheap brand warmth.

## 7. Do NOT borrow

- **Gating backups behind Pro.** Ploi's Basic (€8) has **no automatic backups**. Our rule —
  *never gate safety* — is now a differentiator against a named competitor, not just a
  principle ([PRICING-V3](PRICING-V3.md) §4).
- **Gating support behind Pro.** €8 buys you no human.
- **The gate-as-redirect** (Status pages → Subscription with no explanation). Silently
  bouncing someone to a pricing page is a poor moment; say what's gated and why.

## 8. Where we already beat them

- **Every feature on every plan** vs their 11-features-struck-through Basic.
- **Ally**: missions, the verification gate, incident response, memory, threat scans —
  Ploi has none of this. Their AI story *is* MCP, i.e. someone else's AI.
- **Windows + RDP + hosting panels.** Ploi is Linux/PHP-centric (NGINX/PHP/MySQL).
- **Multi-cloud import** (5 providers incl. GCP/Azure) vs their 8 VPS providers, no GCP/Azure.

## 9. Not explored (needs a provisioned server or would change the account)

SSH keys · Backup configurations · Invoices · Documentation · Support · Team management
detail · **any server/site detail UI** (the real product surface — deploys, logs, the file
explorer, monitoring) · the deploy flow · what "Server insights" actually shows.

**To go deeper we'd need a real server on the account** (paid) — worth it only if we want
the deploy/monitoring UX, which is the part we most differ on anyway.

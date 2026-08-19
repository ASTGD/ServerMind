# Continue Here — build status, pending work & testing plans (2026-08-18)

The single living "where are we, what's left, what needs a decision" doc for ServerAlly.
Full dated history is in **CLAUDE.md's Decisions Log**; this doc is the *current snapshot*.

> **Read this warning before trusting the rest.** The previous snapshot was dated 2026-07-16
> and had gone **319 commits and 30 migrations** stale by the time it was refreshed. It was
> actively wrong about six things, including claiming the bug log's Open section was empty
> when it held a confirmed live incident. Every item below was checked against the current
> code and against production, not against what a doc claimed. **If you are reading this more
> than a couple of weeks after the date above, verify before believing.**

## Where we are

**Production:** `serverally.firevps.net`, running commit `b1201bd`. Migrations at **063**.
Backend suite green (**3,601 tests**), frontend `npm run build` + **191 vitest**, CI-gated
including the Ally eval gate.

The product is in **live-validation and Ploi-replication** phase, not a build phase.

Shipped and working:
- **Ally** — chat, agentic missions (durable, resumable, detached, verification gate),
  memory + its own work record, skills, recipes, Smart Model Ladder, scout/live-look,
  autonomy modes, Autopilot (scheduled work within a policy you set).
- **MCP connector** — a customer's own AI (Claude Desktop, Claude Code, ChatGPT) manages
  their fleet over OAuth. **27 tools.** Three consent tiers: Read-only / Full access /
  Full power. Both Claude and ChatGPT verified connecting to production.
- **Any OS/host** — Linux (SSH), **Windows (WinRM — now live-validated)**, RDP,
  hosting panels (CyberPanel proven live), AWS **Systems Manager** (no WinRM, no open port).
- **Sites** — the Ploi replication: create (4 installers), redirects, aliases, password
  protection, suspend, page cache, clone, staging (create + promote), permissions, `.env` and
  `wp-config` editors, PHP version, cron, databases, daemons, queue workers, WP security
  switches, WP-CLI + artisan consoles, notes/tags, HTTPS (Let's Encrypt, ZeroSSL, CSR,
  bring-your-own certificate, HTTP/3), deploy notifications.
- **Operate** — deploy pipeline (atomic switch, push-to-deploy, rollback), offsite backups,
  uptime + certificate-expiry + service monitoring, notification channels (Slack/Email/
  Telegram/SMS), server log viewer, firewall + SSH key managers, cloud lifecycle
  (DigitalOcean, Hetzner), public status pages, white-label + client reports.
- **Proactive** — fleet intelligence, threat monitoring (**5-minute** malware scans) with
  guided incident response, fleet-health email digest. **Email genuinely delivers** — our own
  Postfix relay with DKIM; Gmail returns `250 OK`.
- **Dev Door** (`/dev`, admin-only) — prompt inspector, eval runner + capture flywheel, LLM
  judge, AI cost ledger, operator console (read-only support/ops view).

---

## 1. Open bugs

**None.** `docs/ISSUES-FOUND.md` has no genuinely open entry.

BUG-015 — the hardening runbook that locked ServerAlly out of a live server — was **fixed on
2026-08-18**. The command is now refused by the safety layer at the one choke point every
AI-planned command passes through, the `harden-server` skill no longer calls closing root
password login "safe always", and the server profile tells Ally how ServerAlly itself
connects. Proven against real stored credentials: **12 of 13** Linux servers would have been
locked out by that exact command, and every one is now refused.

> **Bug-log hygiene, still outstanding:** the Open section of `docs/ISSUES-FOUND.md` still
> lists 10 entries that are all marked `Fixed` and were simply never moved to the Fixed
> section. Nothing is broken, but the section cannot be read at a glance until they are moved.

---

## 2. Blocked on the user (ordered by effort)

| # | Item | Exact next action |
|---|---|---|
| 1 | **Prove the 4 remaining Ploi installers** | Statamic, Craft CMS, Matomo, phpMyAdmin are **written but have never been run**. Each needs a throwaway server. This codebase's own history is emphatic that an unrun installer is not a shipped installer. |
| 2 | **cPanel adapter happy-path** | Mock-tested only. **Correction to the old snapshot:** it claimed cPanel/WHM was live on "TestServer2 (192.3.193.50)" — that address is the ServerAlly production VPS, and the account holds **no cPanel server at all** today (checked 2026-08-18: 14 assets, panels are CyberPanel ×5 and CloudPanel ×1). Validating it needs a real WHM, and a license — see `memory/cpanel-live-validation-needs-license.md`. |
| 3 | **Cloud import happy-path (5 providers)** | Connect + discover + error paths are live-verified; importing a real instance needs one read-only API key per provider. **AWS also unlocks SSM**, which has only ever been proven against a stand-in. |
| 4 | **RHEL/multi-distro playbook smoke test** | The WordPress/LAMP/LEMP `_DISTRO` layer's AlmaLinux/RHEL path was written against documented practice, never run end to end. Needs a *fresh* AlmaLinux/Rocky/CentOS box. |
| 5 | **DirectAdmin adapter** | Mock-tested against the documented API only. CyberPanel is still the only hosting adapter proven live. |
| 6 | **WHMCS PHP module** | Needs one pass on a **staging WHMCS** — runbook ready at [`docs/WHMCS-PHASE1-TEST.md`](WHMCS-PHASE1-TEST.md). The ServerAlly side is already validated (26/26 against the real backend + Postgres) and `hooks.php` has been executed against the real endpoint via a stubbed-WHMCS harness. What remains is WHMCS-only: the lifecycle hooks, client area, and a real order→pay→claim flow. Two known bugs to expect, not be surprised by: BUG-W1 and BUG-W2. |
| 7 | **panel2.firevps.net remediation** | The root-compromised production box: rotate **all** credentials from a clean device and rebuild on fresh infrastructure. Per-site cleanup is done; this is the root fix and only the user can do it. See `memory/panel2-root-gsocket-backdoor.md`. |
| 8 | **Business/pricing decisions** | See §5 — PM calls, not code. |

---

## 3. Remaining engineering gaps

Checked against the current code on 2026-08-18. These are genuine, not doc staleness.

**Ploi replication — what is left:**
- The **4 installers** above (written, unproven).
- **DNS-based SSL validation** (for wildcard certificates). Deliberately designed differently
  from Ploi: they put the customer's DNS token on the managed server; we already hold those
  credentials, and the offsite-backup precedent says the server must never receive them — so
  ours will run the DNS-01 exchange from the backend and install through the certificate path
  that already exists. Its own piece of work, not a paragraph.

**Never driven end to end on real hardware** (built and unit-proven, but the button-to-result
chain has not been run):
- **Staging site creation through the app** — the copy engine is proven against real nginx,
  PHP-FPM and MariaDB; the full create-through-the-UI path has not run, because the account
  has no site on a non-panel server.
- **`.env` over MCP** — proven by parsing and mutation, never exercised against a real Laravel
  site.
- **RDP desktop** — the whole pipeline (browser ↔ `/ws/rdp` ↔ guacd ↔ RDP) is proven; an
  actual Windows desktop rendering has never been seen.
- **Certificate paste form** — every site on the account is on a CyberPanel server, where
  HTTPS is deliberately refused (a panel owns its own certificates).

**Security residuals** (full detail in `SECURITY.md`):
- `GET /api/audit` is self-service only — no team-wide view, no retention/pruning policy.
- TOTP replay window (~30–90s) — no single-use timestep cache; accepted risk.
- `token_version` isn't bumped specifically when 2FA is toggled (logout still bumps it).
- Panel/WinRM connections use `verify=False` (self-signed panels are common). An opt-in
  "strict TLS" per-asset toggle would close it; by design not yet offered.
- `REQUIRE_EMAIL_VERIFICATION` is unset in production — set it before public signups.
- `ENFORCE_PLAN_LIMITS=false` — **every user currently has unlimited servers and AI.**

**Feature residuals** (deferred in their own design docs, not overlooked):
- **Mission engine Phase 5** — Redis pub/sub fan-out for horizontal scale (still
  single-process); webhook-triggered redeploys; community mission templates.
- **Mission cancel** doesn't force-kill the remote process — streaming stops and the run is
  marked cancelled (documented limit, not a bug).
- **CyberPanel email** — the `cyberpanel` CLI exposes no email function, so it falls through
  to "not supported for this panel". Databases and SSL *are* wired.
- **Fleet-install** — per-server unique variables in a batch; fleet runs for saved user
  scripts; "retry failed only".
- **Recipes** can't target an API-only hosting connection (no SSH).
- **Dev Door stretch** — A/B prompt variants; auto-drafting eval cases from ledger failures.
- **Docker-based servers** — the log viewer reads `/var/log`, so an app logging inside a
  container shows nothing. `docker logs` support is a follow-up.
- **Digest is English-only** while the product ships 8 languages.
- **RDP viewer** — no clipboard, file transfer or recording; an existing WinRM asset can't be
  re-typed to RDP in Edit (delete + re-add).

**Known-imperfect behaviours:**
- **Whole-server report repeats a self-footprint mislabel** — it can read ServerAlly's own
  egress IP as the attacker, because it synthesises persisted *missions* only and the
  self-footprint rule lives in the incident-response mission skill.
  See `memory/serverally-egress-ip-self-footprint.md`.
- **Reports only see missions** — findings from chat or direct forensics never enter the
  record, so an aggregate report can omit real findings.
- **Outgoing mail reverse DNS** is `192-3-193-50-host.colocrossing.com`, which Gmail and
  Microsoft penalise. Only the hosting provider can fix it; some mail may land in spam.

---

## 4. Testing status

- **Backend** — 3,601 tests, green. **Frontend** — `npm run build` + 191 vitest. Both
  CI-gated on every push, including the Ally eval gate.
  *(CI had been silently red for a week in early August and the eval gate had never run —
  fixed 2026-08-11. Worth re-checking after any dependency bump.)*
- **`docs/QA-CHECKLIST.md`** — ⏳ not run. Manual dogfooding script; worth one pass before a
  public launch.
- **`DEPLOY.md` §8 smoke tests** — ⏳ not run against a real deployed stack.
- **Ally live evals** — opt-in (`RUN_ALLY_EVALS=1` + API key). CI never pays for them, so
  someone must run them by hand, especially before/after a model or prompt change.
- **Mutation testing is the house standard** for anything with a guard in it. It has caught a
  weak test roughly as often as a weak fix.

---

## 5. Business/pricing open decisions (PM calls, not build items)

Pricing **v3** is locked in principle — *two layers: platform priced per server, plus your
choice of AI (bring your own via MCP/own key, or an Ally subscription)*. See
[`docs/PRICING-V3.md`](PRICING-V3.md). **Credits, tokens and per-request billing are
forbidden** by that decision.

Still to decide:
- The actual numbers — deliberately unset, to come from a beta cohort measured through the
  operator console's per-user cost data, then grandfathered.
- Overage UX at the plan wall (top-up vs hard stop vs BYO-key escape valve).
- Self-hosted licensing: platform, installs-per-licence, on-expiry behaviour, offline
  activation — see `docs/SELF-HOSTED-LICENSING.md` ("strategy agreed, not yet built").
- Whether the hosted AI gateway should route by model tier (chat/missions do; it doesn't).
- **Watch item:** the operator console's first real reading showed **$0.096 per AI action** —
  about 2× the $0.05 the Pro margin case assumes. That was our own mission-heavy dev usage,
  so it is a signal not a verdict, but it must be re-read on customer-shaped usage before
  `ENFORCE_PLAN_LIMITS` is switched on.

---

## 6. What shipped since the last snapshot (2026-07-16 → 2026-08-18)

319 commits. The headlines, by theme — full detail in CLAUDE.md's Decisions Log:

- **MCP connector** (07-23 → 08-13) — remote Streamable-HTTP server, our own OAuth 2.1
  authorization server, 27 bounded tools, three consent tiers, `.env` and DNS tools. First
  real Claude connect exposed 3 deploy bugs a mock cannot; ChatGPT exposed a 4th (08-18).
- **The Ploi replication** (07-30 → 08-10) — the whole per-site surface, one screen at a
  time, each proven against real nginx/PHP-FPM/systemd/MariaDB in containers.
- **Operate features** (07-25 → 07-28) — offsite backups, uptime, log viewer, Autopilot,
  status pages, certificate expiry, white-label, service monitoring, deploy pipeline,
  firewall + SSH keys, cloud lifecycle.
- **Assets rework** (07-29, 08-11) — capability-driven menus, three add-tiles instead of six,
  derived groups, provider zones, AWS SSM as a transport, cross-account roles.
- **Alerting became real** (07-30) — production had **no email configuration at all**; every
  alert this product generates went nowhere while appearing to work. Own Postfix relay with
  DKIM; malware detection went from 12 hours to 5 minutes.
- **Server setup hardening** (08-01, 08-03) — seven separate faults in the first thing a
  customer ever asks us to do, none visible to any offline test.
- **Staging sites** (08-06 → 08-12) — create a copy, then promote it live by commit or file.
- **UI redesign** (07-22) — 6 phases, design system, and the light/dark/system theme toggle.
- **Operator console** (07-17) — admin support/ops view WHMCS structurally cannot provide.
- **Bugs found by real use** — BUG-018 through BUG-025, including three Windows bugs that all
  came from one gap: Phase 2B was tested entirely against mocked `pywinrm`.

**Now fixed, contradicting the old snapshot:** the dark/light toggle exists; SMTP delivers for
real; rate limiting and the audit log both use a proxy-aware client IP (`client_ip.py`);
WinRM is live-validated.

---

## How to resume locally

- Dev: **backend :8888**, **frontend :5190** (see `OPS.md`). Migrations at **063**.
- Tests: backend `./venv/bin/python -m pytest tests/ -q`, frontend `npm run build` +
  `npx vitest run`. **Never read a pass/fail off a piped tail** — check the exit code.
- The local dev database is Docker (`servermind_postgres`). If ~21 database-dependent tests
  fail at once, check Docker Desktop is actually running before debugging the code.
- Push: `git push origin main` (the remote is already HTTPS). `memory/` is never committed.
- Deploy: on the VPS, `docker compose -f docker-compose.prod.yml --env-file .env.prod` —
  **that file alone**, never merged with the dev compose file. Rebuild `frontend` too when
  frontend files or `nginx.conf` changed. Back the database up first when a migration is in
  the batch.
- **Shared checkout warning:** the owner often edits and commits in this same working tree.
  Check `git status` before staging, stage explicit paths (never a blind `git add -A`).
- If `git` fails with an Xcode licence error, use
  `/Library/Developer/CommandLineTools/usr/bin/git` (permanent fix:
  `sudo xcode-select -s /Library/Developer/CommandLineTools`).

## Marketing

- `marketing-brief/` — a self-contained brief + real screenshots for the landing page.
- `marketing-visuals/` — a full-session GIF + hero stills captured from a real live session.
- `demo.serverally.org` is a **real WordPress site still running on TestServer4** from a live
  demo. It serves HTTP 200 via a Host header but its DNS was never pointed. Point the A record
  at 91.109.20.155 to enable SSL, or delete it.

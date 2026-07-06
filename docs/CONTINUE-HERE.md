# Continue Here — build status, pending work & testing plans (2026-07-06)

The single living "where are we, what's left, what needs a decision" doc for ServerAlly.
Full dated history is in **CLAUDE.md's Decisions Log**; this doc is the *current snapshot*
distilled from it plus a full audit of every doc in the repo (see "Docs reorganization"
below) — every item here was checked against the current code, not just against what a
doc *claims*.

## Where we are

All core phases (0–13) **and** the whole Assets premium plan are **build-complete** and
CI-green:
- **Ally** — AI chat, agentic missions (durable/resumable/detached, verification gate,
  concurrent cards), memory, skills, recipes, Smart Model Ladder.
- **Any OS/host** — Linux (SSH, live-proven), Windows (WinRM, built, not yet live-validated),
  hosting panels (CyberPanel live-proven; cPanel/Plesk/DirectAdmin adapters built).
- **Assets & categories** — Bare Metal · VPS · Hosting · Windows · Cloud, all 5 phases (A–E
  foundation) shipped.
- **Cloud Accounts — all 5 providers** (AWS, DigitalOcean, Hetzner, Google Cloud, Azure):
  connect → discover → import. Reject/error paths live-verified; import happy-path needs a
  real key per provider.
- **Proactive** — Fleet Intelligence (health scores), threat monitoring + guided incident
  response, fleet-health email digest.
- **Ops** — playbooks, script generator, scheduler, file manager, monitoring/alerts,
  security audit, backups, team roles, terminal.
- **RDP (Phase E) foundation** — Windows "Open Desktop" toggle + secure, access-gated,
  credential-free session token. Live pixel streaming (guacd) is the one remaining Assets build.

The product is essentially in a **polish + live-validation** phase, not a build phase.
Nearly everything left below is either (a) blocked on something only the user can provide,
or (b) a small, known, deliberately-deferred residual — not a surprise gap.

---

## 1. Blocked on the user (ordered by effort)

| # | Item | Exact next action |
|---|---|---|
| 1 | **Windows/WinRM + RDP streaming** | User is providing a test Windows box. Add it via **Assets → Add Asset → Windows Server** (encrypted; we never see the raw password). Needs WinRM 5985 (`Enable-PSRemoting -Force`, run once via RDP/console) and/or RDP 3389 reachable. Unblocks: WinRM live validation, RDP session flow, and building Phase E part 2 (guacd streaming). |
| 2 | **cPanel adapter happy-path** | cPanel/WHM installed live on **TestServer2** (192.3.193.50; was an AlmaLinux LEMP box, now dedicated to cPanel). Adapter reaches real cpsrvd — blocked only on a license: log into WHM (:2087) and (a) accept the legal agreements, (b) sign into/create a free cPanel Store account to activate the 15-day trial. ~2 clicks. See `memory/cpanel-live-validation-needs-license.md`. |
| 3 | **Cloud import happy-path (5 providers)** | Each cloud adapter (AWS/DigitalOcean/Hetzner/GCP/Azure) has connect+discover+error paths live-verified, but the actual **import** of a real instance needs one read-only API key per provider from the user to test against real infrastructure. |
| 4 | **RHEL/multi-distro playbook smoke test** | The WordPress/LAMP/LEMP `_DISTRO` layer's AlmaLinux/RHEL path was written against documented practice but never run end-to-end (SELinux/firewalld/php-fpm-pool are exactly where untested scripts break). **The original test candidate (TestServer2) is now the dedicated cPanel box** — this needs a *different*, fresh AlmaLinux/Rocky/CentOS box. |
| 5 | **DirectAdmin adapter** | Mock-tested (11 cases) against the documented API only — needs one live pass against a real DirectAdmin panel (same caveat cPanel/Plesk started with; CyberPanel is the only hosting adapter proven live so far). |
| 6 | **Business/pricing decisions** | See §5 below — these are PM calls, not code. |

---

## 2. Needs live infrastructure to finish (build done, proof pending)

- **Phase E part 2 — RDP pixel streaming.** The Apache Guacamole (`guacd`) Docker service +
  `guacamole-common-js` viewer that actually streams a desktop. The security core (opt-in
  toggle, access-gated credential-free session token) is done and tested; needs a live
  Windows/RDP host to build the streaming leg against (see item 1 above).
- **Windows/WinRM.** Fully built (connect/execute/metrics/OS-detect), only ever mock-tested.

---

## 3. Real remaining engineering gaps (small, known, deprioritized)

Verified against the current code during this pass — these are genuine, not doc staleness.

**Security residuals** (full detail in `SECURITY.md`, which was itself stale and has been
corrected this pass — most of its old "known gaps" turned out to be already fixed):
- Rate-limit key source reads the raw connecting IP; needs a trusted `X-Forwarded-For`
  config once ServerAlly sits behind a reverse proxy in production.
- `GET /api/audit` is self-service only — no admin/team-wide audit view, no retention/pruning
  policy for the `audit_logs` table.
- TOTP replay window (~30–90s reuse) — no single-use timestep cache; accepted risk.
- `token_version` isn't bumped specifically when 2FA is toggled on/off (logout still bumps it).
- Panel/WinRM connections use `verify=False` (self-signed panels are common) — an opt-in
  "strict TLS" per-asset toggle would close this, by design not yet offered.
- Cosmetic: a harmless passlib/bcrypt "error reading bcrypt version" log line persists.
- `REQUIRE_EMAIL_VERIFICATION` exists and works but isn't flipped on (config decision, not
  a missing feature) — flip it before opening public signups.

**Feature residuals** (all explicitly deferred in their own design docs, not overlooked):
- **Dark/light mode toggle** — verified: dark-mode CSS variables exist in `index.css` but
  there's no UI control to switch into it. Genuinely not built.
- **Mission engine Phase 5** — Redis pub/sub fan-out for horizontal scaling (missions are
  currently single-process); webhook-triggered redeploys; community mission templates;
  missions-in-parallel across servers via the batch pattern.
- **Fleet-install** — per-server unique variables in a batch run (same values apply to all
  today); fleet runs for saved user scripts (official playbooks only today); "retry failed
  only" from a batch view.
- **Guided remediation Tier 3** — AI-assisted fix suggestions for fleet-install failures
  (Tiers 1–2, recommend-only + readiness check, are shipped).
- **Recipes** — can't yet target an API-only hosting connection (cPanel/Plesk/DirectAdmin
  without SSH); needs its own SSH/WP-CLI path first. Multi-mission chaining past the
  40-step budget ceiling is deferred ("later, only if needed").
- **Ally Evals "dream" item** — mining successful mission transcripts to auto-propose new
  skills/eval cases (human-reviewed) — aspirational, not built.
- **Hosting H2** — the original UPDATE-era plan to apply CyberPanel's "CLI-over-SSH" pattern
  to cPanel/Plesk turned out to be superseded by what was actually built: cPanel/Plesk/
  DirectAdmin use their own panel API adapters directly (`hosting_service.py`), not a
  CLI-over-SSH bridge. Only the Databases/Email/SSL buttons in the Hosting UI aren't wired
  to CyberPanel's already-existing service methods yet.
- **Mission cancel** doesn't force-kill the remote process — streaming just stops and the
  run is marked cancelled (a documented limit, not a bug).
- **Interactive terminal** (`/ws/terminal`) was never moved onto the durable Celery execution
  model — likely fine as-is (a terminal is inherently live/interactive, not a batch job), but
  flagging since a design doc listed it as "remaining."

---

## 4. Testing-plan status (what's actually been run vs. just planned)

- **Shakedown cruise** — ✅ **executed.** Full results in `docs/ALLY-CAPABILITIES-TESTED.md`
  (the original mandate is archived at `docs/archive/SHAKEDOWN-TESTPLAN.md`). Explicitly
  documents its own honest gaps: Windows/WinRM and cPanel/Plesk hosting were NOT exercised
  live in that round (CyberPanel-over-SSH was); the adversarial red-team is "a sample, not a
  proof of universal safety."
- **`docs/QA-CHECKLIST.md`** — ⏳ **not run.** A manual, human-driven dogfooding script; no
  completed pass is recorded. Worth one run before a public launch.
- **`DEPLOY.md` §8 smoke tests** — ⏳ **not run.** All boxes unchecked; this is a single
  end-to-end pass against a real *deployed* stack (distinct from the dev-environment
  shakedown above, which already covers most of the same ground individually).
- **Ally Evals harness** — CI-gated deterministic suite runs automatically on every push.
  The **opt-in live evals** (`RUN_ALLY_EVALS=1` + API key) are a standing manual-trigger gap
  — CI never pays for them, so they need someone to run them by hand periodically.

---

## 5. Business/pricing open decisions (PM calls, not build items)

- Final Pro price point and exact action allowance (1,000/mo is a placeholder pending real
  ledger cost data).
- Overage UX at the plan wall (top-up packs vs. hard stop vs. BYO-key-only escape valve).
- Self-hosted licensing: platform choice, installs-per-license policy, on-expiry behavior,
  offline/air-gapped activation — see `docs/SELF-HOSTED-LICENSING.md` ("strategy agreed,
  not yet built").
- Whether the hosted AI gateway should route by model tier too (currently chat/missions do,
  the gateway doesn't).

Note: the "billing provider TBD (Stripe/Paddle/Lemon Squeezy)" question that several older
docs still posed has been **resolved** — WHMCS (via FireVPS) was chosen and is shipped; see
`docs/WHMCS-INTEGRATION.md`. The WHMCS **PHP module** itself still needs one validation pass
on a staging WHMCS instance (no PHP locally to test it).

---

## 6. Recently closed loops (this session)

- Console "setState during render" warning in `ChatWindow`/`AssistantDrawer` — fixed, merged.
- Backlog checkboxes for AWS/DigitalOcean/Hetzner cloud import — were stale (shown unchecked
  after shipping); corrected in `CLAUDE.md`.
- `CLAUDE.md`'s "CURRENT STATUS" section was frozen at 2026-06-23 (pre-dating nearly
  everything) — rewritten to point here, old note kept as a labeled historical record.
- `marketing-brief/` shipped — Claude Design is now building the landing page from it.
- Full docs reorganization (this pass) — see below.

## Docs reorganization (this pass)

13 docs whose content was either fully superseded by later work or a closed historical
record were moved to **`docs/archive/`** (their still-open items, if any, were folded into
this doc first — nothing was lost): all of `UPDATE-14` through `UPDATE-23`,
`SERVER-CATEGORIES.md` (superseded by `ASSETS-CATEGORIES-PLAN.md`), `SHAKEDOWN-TESTPLAN.md`
(executed — see §4), and `RISK-3-SERVER-IDENTITY.md` (its fix is now a permanent line in
CLAUDE.md's Security Rules + schema, not a standalone tracked item). Every cross-reference
to a moved file was updated. `AI-METERING.md`, `PRICING-FREE-VS-PRO.md`, and root
`SECURITY.md` got small in-place status-correction notes rather than a full rewrite (their
core content is still accurate; only specific lines had gone stale). See `docs/README.md`
for the full current index.

---

## How to resume locally

- Dev: **backend :8888**, **frontend :5190** (see `OPS.md`). Migrations at **028**.
- Tests: backend `pytest` (458 pass), frontend `npm run build` + `npx vitest run` (32).
- Push: swap origin to `https://github.com/ASTGD/ServerMind.git`, push, restore the SSH
  remote (`git@github.com:ASTGD/ServerMind.git`). `memory/` is never committed.

## Marketing

- `marketing-brief/` holds a self-contained brief + real screenshots for the design tool
  building the landing page (see `marketing-brief/README.md`). Claude Design is actively
  building the landing page from it as of 2026-07-06.

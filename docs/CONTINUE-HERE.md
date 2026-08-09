# Continue Here — build status, pending work & testing plans (2026-07-16)

The single living "where are we, what's left, what needs a decision" doc for ServerAlly.
Full dated history is in **CLAUDE.md's Decisions Log**; this doc is the *current snapshot*.
Every item here was checked against the current code, not just against what a doc *claims*
(the 2026-07-16 pass found the previous snapshot had gone 10 days / 76 commits stale and was
actively wrong about RDP streaming — see §6).

## Where we are

All core phases (0–13), the whole Assets premium plan, and the Ally intelligence stack are
**build-complete** and CI-green:
- **Ally** — AI chat, agentic missions (durable/resumable/detached, verification gate,
  concurrent workspace cards), memory + its own work record, skills, recipes, Smart Model
  Ladder, scout/live-look, autonomy modes.
- **One Ally** — a single dockable Ally window: chat left, live Workspace right (missions,
  streamed command output, table/chart artifacts).
- **Any OS/host** — Linux (SSH, live-proven), Windows (WinRM, built, **not** live-validated),
  hosting panels (CyberPanel live-proven; cPanel/Plesk/DirectAdmin adapters built).
- **Assets & categories** — Bare Metal · VPS · Hosting · Windows · Windows (RDP) · Cloud.
  **All phases A–E shipped, including live in-browser Remote Desktop** (guacd tunnel +
  guacamole-common-js viewer, pipeline proven end-to-end).
- **Cloud Accounts — all 5 providers** (AWS, DigitalOcean, Hetzner, Google Cloud, Azure):
  connect → discover → import. Reject/error paths live-verified; import happy-path needs a
  real key per provider.
- **Proactive** — Fleet Intelligence (health scores), threat monitoring + guided incident
  response, fleet-health email digest.
- **Reports** — "Explain this incident" (per-mission narrative from the durable transcript)
  and the whole-server aggregate report, with PDF/Markdown export.
- **Dev Door** (`/dev`, admin-only) — prompt inspector (dry-run the exact chat prompt),
  eval runner + capture-as-eval flywheel, LLM judge, AI usage/cost ledger, Cost A/B.
- **Ops** — playbooks, script generator, scheduler, file manager, monitoring/alerts,
  security audit, backups, team roles, terminal.

The product is in a **polish + live-validation** phase, not a build phase. Nearly everything
below is either (a) blocked on something only the user can provide, or (b) a small, known,
deliberately-deferred residual — not a surprise gap.

**Bug log:** `docs/ISSUES-FOUND.md` — **Open section is empty** (BUG-001 and BUG-002 both
fixed 2026-07-15; both standing tasks closed).

**Next build, approved and planned:** **staging sites** —
[`docs/STAGING-SITES-PLAN.md`](STAGING-SITES-PLAN.md), written 2026-08-02 after reading
Ploi's own staging feature live on the owner's trial account. Two features, built separately:
*create a staging copy* (safe, and most of the value) and *copy staging over the live site*
(the dangerous one, built last). Build order **P0 → P1 → P2 → P5 → P3 → P4**.

**P0, P1 and P2 are DONE** (2026-08-06 and 2026-08-08). A staging copy can be created from
the site's **Manage** screen: it gets its own site and vhost, the files, its own database
holding the live data, a repointed configuration, and robots blocked — and anything that
fails after the files land takes the whole copy away rather than leaving one pointed at live
data. **Next is P5** (what a staging site must not inherit), then P3, then P4.

Two things left from P1/P2, both small: the *Advanced settings* checkbox on the New site
card, and — the honest gap — **the full create-through-the-app path has never run on a real
machine**, because the account has no site on a non-panel server. The copy engine itself is
proven against real nginx + PHP-FPM and a real MariaDB; what has not been driven end to end
is the button → site created → files copied → data imported chain on live hardware.

---

## 1. Blocked on the user (ordered by effort)

| # | Item | Exact next action |
|---|---|---|
| 1 | **Live Windows box (WinRM + RDP)** | Add via **Assets → Add Asset → Windows Server** (WinRM 5985; `Enable-PSRemoting -Force` once via RDP/console) and/or **Windows (RDP)** (port 3389). Both paths are fully **built**; this unblocks *validation only* — WinRM has only ever been mock-tested, and the RDP viewer has been proven end-to-end through guacd but never against a real desktop. |
| 2 | **cPanel adapter happy-path** | cPanel/WHM is live on **TestServer2** (192.3.193.50). Adapter reaches real cpsrvd — blocked only on a license: log into WHM (:2087), (a) accept the legal agreements, (b) sign into/create a free cPanel Store account for the 15-day trial. ~2 clicks. See `memory/cpanel-live-validation-needs-license.md`. |
| 3 | **Cloud import happy-path (5 providers)** | Connect + discover + error paths are live-verified; the actual **import** of a real instance needs one read-only API key per provider. |
| 4 | **RHEL/multi-distro playbook smoke test** | The WordPress/LAMP/LEMP `_DISTRO` layer's AlmaLinux/RHEL path was written against documented practice, never run end-to-end (SELinux/firewalld/php-fpm-pool are where untested scripts break). Needs a *fresh* AlmaLinux/Rocky/CentOS box — TestServer2 is now the dedicated cPanel box. |
| 5 | **DirectAdmin adapter** | Mock-tested (11 cases) against the documented API only — needs one live pass against a real DirectAdmin panel. CyberPanel is still the only hosting adapter proven live. |
| 6 | **WHMCS PHP module** | Needs one pass on a **staging WHMCS** — the runbook is written and ready: [`docs/WHMCS-PHASE1-TEST.md`](WHMCS-PHASE1-TEST.md) (12 tests + the reconcile check). The ServerAlly side is **already validated** (`./whmcs/test-entitlements.sh` → 26/26 against the real backend + Postgres), and both PHP files lint clean — **PHP 8.4 IS available locally** (the old "no PHP locally" note was wrong), and `hooks.php` has been executed against the real endpoint via a stubbed-WHMCS harness. What remains is genuinely WHMCS-only: the module's own hooks (Create/Suspend/Unsuspend/Terminate), the client area, and the real order→pay→claim flow. **Two known bugs to confirm, not be surprised by:** BUG-W1 (email change orphans the paying account) and BUG-W2 (the claim button never clears). |
| 7 | **panel2.firevps.net remediation** | The root-compromised production box: rotate **all** credentials from a clean device and rebuild on fresh infrastructure. Cleanup of individual sites is done; this is the root fix and only the user can do it. See `memory/panel2-root-gsocket-backdoor.md`. |
| 8 | **Business/pricing decisions** | See §5 — PM calls, not code. |

---

## 2. Needs live infrastructure to finish (build done, proof pending)

- **Windows/WinRM** — fully built (connect/execute/metrics/OS-detect), only ever mock-tested.
- **RDP desktop** — the full pipeline (browser ↔ `/ws/rdp` ↔ guacd ↔ RDP) is proven: guacd
  performs a real RDP negotiation and renders its result in the browser canvas. What's never
  been seen is an actual Windows desktop rendering, which needs item 1 above.
- **cPanel / DirectAdmin adapters, cloud import** — see §1 items 2, 3, 5.

---

## 3. Real remaining engineering gaps (small, known, deprioritized)

Verified against the current code during the 2026-07-16 pass — these are genuine, not doc
staleness.

**Security residuals** (full detail in `SECURITY.md`; auth/rate-limit/audit code is untouched
since the last audit, so these all still hold):
- Rate-limit key source reads the raw connecting IP; needs a trusted `X-Forwarded-For` config
  once ServerAlly sits behind a reverse proxy in production. (`rate_limit_service.py` carries
  a NOTE about this but does not implement it. `audit_service` *does* honour the first hop.)
- `GET /api/audit` is self-service only — no admin/team-wide audit view, no retention/pruning
  policy for the `audit_logs` table.
- TOTP replay window (~30–90s reuse) — no single-use timestep cache; accepted risk.
- `token_version` isn't bumped specifically when 2FA is toggled on/off (logout still bumps it).
- Panel/WinRM connections use `verify=False` (self-signed panels are common) — an opt-in
  "strict TLS" per-asset toggle would close this; by design not yet offered.
- Cosmetic: a harmless passlib/bcrypt "error reading bcrypt version" log line persists.
- `REQUIRE_EMAIL_VERIFICATION` exists and works but is `False` — flip it before public signups.

**Feature residuals** (all explicitly deferred in their own design docs, not overlooked):
- **Dark/light mode toggle** — re-verified 2026-07-16: dark-mode CSS exists and components
  style both themes, but there is **no UI control** to switch. Genuinely not built.
- **Mission engine Phase 5** — Redis pub/sub fan-out for horizontal scaling (re-verified:
  missions are still single-process/in-memory); webhook-triggered redeploys; community
  mission templates.
- **Mission cancel** doesn't force-kill the remote process — streaming stops and the run is
  marked cancelled (a documented limit, not a bug).
- **CyberPanel email** — re-verified 2026-07-16: **Databases and SSL *are* wired** for
  CyberPanel (CLI → `hosting_service` → routes → Hosting UI). Only **Email** is not: the
  `cyberpanel` CLI exposes no email function, so it falls through to the base adapter's
  "not supported for this panel". (Supersedes the old "Hosting H2 / DB+Email+SSL unwired"
  note, which was stale.)
- **Fleet-install** — per-server unique variables in a batch run (same values apply to all
  today); fleet runs for saved user scripts (official playbooks only today); "retry failed
  only" from a batch view.
- **Guided remediation Tier 3** — AI-assisted fix suggestions for fleet-install failures
  (Tiers 1–2, recommend-only + readiness check, are shipped).
- **Recipes** — can't yet target an API-only hosting connection (cPanel/Plesk/DirectAdmin
  without SSH); needs its own SSH/WP-CLI path first. Multi-mission chaining past the 40-step
  budget ceiling is deferred.
- **Dev Door stretch** — A/B prompt variants, and auto-drafting eval cases from ledger failure
  patterns (the "mine mission transcripts to propose skills/evals" dream item). Not built.
- **Interactive terminal** (`/ws/terminal`) was never moved onto the durable Celery execution
  model — likely fine as-is (a terminal is inherently live), flagged only because a design doc
  listed it.

**Known-imperfect behaviours (honest limitations, tracked here so they aren't rediscovered):**
- **Whole-server report repeats a self-footprint mislabel** — it can read ServerAlly's own
  egress IP (`150.228.135.29`) as the attacker, because it only synthesises persisted
  *missions* and the self-footprint rule lives in the incident-response **mission skill**, not
  in the aggregator or the plain plan/advisory path. See `memory/serverally-egress-ip-self-footprint.md`.
- **Reports only see missions** — findings from chat/direct forensics never enter the record,
  so an aggregate report can omit real findings. Server reports also regenerate per session
  (no server-side cache).
- **Digest is English-only** — `digest_service` strings are hardcoded English while the product
  ships 8 languages.
- **SMTP never validated live** — dev SMTP is unconfigured, so `send_email` safely no-ops. The
  alert/digest email path has never actually delivered a message.
- **RDP viewer residuals** — no clipboard, no file transfer, no session recording; ServerDetail's
  tabs aren't tuned for a command-less RDP asset. An existing WinRM asset can't be re-typed to
  RDP in Edit (delete + re-add).

---

## 4. Testing-plan status (what's actually been run vs. just planned)

- **Backend suite** — 629 pass / 24 skipped. **Frontend** — `npm run build` + 45 vitest.
  Both CI-gated on every push, including the Ally eval gate.
- **Shakedown cruise** — ✅ executed. Results in `docs/ALLY-CAPABILITIES-TESTED.md` (mandate
  archived at `docs/archive/SHAKEDOWN-TESTPLAN.md`). Documents its own gaps: Windows/WinRM and
  cPanel/Plesk hosting were not exercised live; the adversarial red-team is "a sample, not a
  proof of universal safety."
- **`docs/QA-CHECKLIST.md`** — ⏳ not run. Manual dogfooding script; worth one pass before a
  public launch.
- **`DEPLOY.md` §8 smoke tests** — ⏳ not run. All boxes unchecked; a single end-to-end pass
  against a real *deployed* stack.
- **Ally live evals** — the opt-in behavioural evals (`RUN_ALLY_EVALS=1` + API key) are a
  standing manual-trigger gap: CI never pays for them, so someone must run them by hand
  periodically (especially before/after a model or prompt change).

---

## 5. Business/pricing open decisions (PM calls, not build items)

- Final Pro price point and exact action allowance (1,000/mo is a placeholder pending real
  ledger cost data — the Dev Door's Activity tab now has real cost history to base this on).
- Overage UX at the plan wall (top-up packs vs. hard stop vs. BYO-key-only escape valve).
- Self-hosted licensing: platform choice, installs-per-license policy, on-expiry behaviour,
  offline/air-gapped activation — see `docs/SELF-HOSTED-LICENSING.md` ("strategy agreed, not
  yet built").
- Whether the hosted AI gateway should route by model tier too (chat/missions do; the gateway
  doesn't).
- **Resolved:** the billing provider question — WHMCS (via FireVPS) was chosen and is shipped
  (`docs/WHMCS-INTEGRATION.md`). Only the PHP module's staging validation is outstanding (§1.6).

---

## 6. Recently closed loops (2026-07-07 → 2026-07-16)

The previous snapshot was written 2026-07-06 and went **76 commits** stale. What shipped since:

- **Eval-driven Dev Door** (07-12) — admin-only `/dev`: prompt inspector (dry-run the exact
  chat prompt, never executes), eval runner + capture-as-eval flywheel, LLM judge, AI
  usage/cost ledger + trend, CI eval gate. `users.is_admin` (migration 030), `dev_eval_cases`
  (031).
- **Assets Phase E COMPLETE — live in-browser Remote Desktop** (07-13) — guacd service, a
  hand-rolled Python Guacamole tunnel (`/ws/rdp`, credentials decrypted server-side and never
  sent to the browser), `RdpCanvas` viewer. Plus **RDP as a first-class asset**
  (`connection_type='rdp'`, port 3389, reachability probe) after a live report showed the only
  Windows path assumed WinRM. **This supersedes the old snapshot's "one remaining Assets
  build".**
- **Mission result card** (07-13, migration 032) — every mission ends with a plain-language
  Found/Did/Left outcome instead of a one-line technical banner.
- **Reports** (07-14) — "Explain this incident" (migration 033) synthesises a mission's durable
  transcript into a plain-language story (built precisely *because* chat memory is capped and
  couldn't do it); plus the whole-server aggregate report. PDF/Markdown/Copy export.
- **One Ally** (07-08) — one dockable Ally window growing out of the sidebar: chat left,
  Workspace right; markdown replies; one brain (fleet always in memory); per-message server
  attribution.
- **Ally proactivity** (07-08, Tracks A–D) — capability contract (killed the "I don't have SSH
  access / use scp" hallucination), pre-mission scout, ask-with-option-chips, autonomy modes
  (`users.ally_mode`, migration 029).
- **Ally is a doer** (07-11) — killed the advisory "run this and paste the output back"
  pattern; live command output + table/chart artifacts render in the Workspace; LLM retry
  reliability so a transient empty response never surfaces as "AI error".
- **AI cost** — 1h prompt-cache TTL + an Opus pricing-table bug fix + a Dev Door **Cost A/B**
  tool (Claude vs OpenAI on real ledger usage).
- **Live-testing bug protocol** (`docs/ISSUES-FOUND.md`) and its first four closures:
  - **BUG-002** (Critical, 07-15) — malware cleanup quarantined 128 legitimate `vendor/`
    library files and took a live government site offline. Fixed: signature grep excludes
    dependency trees, one token ≠ proof, never sweep a directory.
  - **BUG-001** (High, 07-15) — Ally forgot its own cleanup and nearly restored a 10-month-old
    backup. Fixed at prompt level, then **closed properly in code** (below).
  - **Task #1** (07-15) — the verify gate now checks page **content**, not just HTTP status
    (a 200 can be a blank/error page).
  - **Task #2** (07-15) — the threat scan now walks the **whole account home**; the old
    `*/public_html` glob silently missed CyberPanel child-domain sites (the exact live gap).
- **Ally's work record** (07-16) — the code-level floor under BUG-001: the server profile now
  shows what Ally **changed** (filtered by the read-only classifier), and a high-risk
  successful change auto-writes a memory note with **no model cooperation**. Narrow by design
  so it can't flood the capped memory store.

---

## How to resume locally

- Dev: **backend :8888**, **frontend :5190** (see `OPS.md`). Migrations at **033**.
- Tests: backend `pytest` (629 pass / 24 skipped), frontend `npm run build` + `npx vitest run` (45).
- Push: swap origin to `https://github.com/ASTGD/ServerMind.git`, push, restore the SSH remote
  (`git@github.com:ASTGD/ServerMind.git`). `memory/` is never committed.
- **Shared checkout warning:** the owner often edits/commits in this same working tree.
  Check `git status` before staging, stage explicit paths (never a blind `git add -A`), and
  prefer a PR over committing straight through — an agent commit reached `main` unreviewed on
  2026-07-16 by riding along with an owner push.

## Marketing

- `marketing-brief/` holds a self-contained brief + real screenshots for the design tool
  building the landing page (see `marketing-brief/README.md`).
- `marketing-visuals/` holds a full-session GIF + hero stills (mission offer, workspace
  approval, workspace verified, security sweep) captured from a real live session.
- Note: `demo.serverally.org` is a **real WordPress site still running on TestServer4** from a
  live demo — re-verified 2026-07-16: it serves HTTP 200 with `<title>ServerAlly Demo</title>`
  via a Host header against 91.109.20.155, but **its DNS was never pointed** (no A record), so
  it does not resolve publicly. Point the A record at 91.109.20.155 to enable SSL, or delete it.

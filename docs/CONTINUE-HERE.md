# Continue Here — build status & next steps (2026-07-06)

Quick resume point for the ServerAlly build. Full history is in the CLAUDE.md Decisions Log
and `docs/ASSETS-CATEGORIES-PLAN.md`.

## Where we are — everything is shipped & CI-green

All core phases (0–13) **and** the whole Assets premium plan are **build-complete**:

- **Ally** — AI chat, agentic missions (durable/resumable/detached, verification gate,
  concurrent cards), memory, skills, recipes, Smart Model Ladder.
- **Any OS/host** — Linux (SSH, live-proven), Windows (WinRM, built), hosting panels
  (CyberPanel live-proven; cPanel/Plesk/DirectAdmin adapters).
- **Assets & categories** — Bare Metal · VPS · Hosting · Windows · Cloud.
- **Cloud Accounts — 5 providers** (AWS, DigitalOcean, Hetzner, Google Cloud, Azure):
  connect → discover → import. Reject/error paths live-verified; import happy-path needs a
  real key per provider.
- **Proactive** — Fleet Intelligence (health scores), threat monitoring + guided incident
  response, fleet-health email digest.
- **Ops** — playbooks, script generator, scheduler, file manager, monitoring/alerts,
  security audit, backups, team roles, terminal.
- **RDP (Phase E) foundation** — Windows "Open Desktop" toggle + secure, access-gated,
  credential-free session token. Live pixel streaming (guacd) is the one remaining build.

Latest commits (all green): Phase C/D/E, cPanel 403 fix, `ServerOut.rdp_enabled`,
Phase D part 2 (GCP + Azure).

## What's left (each needs something from the user)

1. **Phase E part 2 — live RDP streaming (guacd).** The only remaining Assets build.
   *Needs a real Windows server* (RDP 3389 reachable) to build + test.
2. **Windows/WinRM live validation** — WinRM code is built but only mock-tested. Same
   Windows box unblocks this (WinRM 5985 + `Enable-PSRemoting`). **← user is providing a
   test Windows box; they will ADD it via Assets → Add Asset → Windows Server (encrypted;
   we never see the raw password). Then: validate WinRM live, test RDP session flow, build
   guacd streaming.**
3. **cPanel adapter happy-path** — cPanel/WHM installed live on **TestServer2**
   (192.3.193.50; was an AlmaLinux LEMP box). Adapter reaches real cpsrvd; the happy-path
   test is blocked on a license — user must click "I agree" in WHM + sign into a free
   cPanel Store account (2 clicks). See `memory/cpanel-live-validation-needs-license.md`.
4. **Cloud import happy-path** — needs one real read-only key per provider to validate
   discover/import against real machines (adapters are mock-tested + reject-path live).

## Open background task

- `task_4913c114` — fix a pre-existing React "setState during render" warning in
  `ChatWindow`/`AssistantDrawer` (running in a separate session; not from recent work).

## How to resume locally

- Dev: **backend :8888**, **frontend :5190** (see `OPS.md`). Migrations at **028**.
- Tests: backend `pytest` (458 pass), frontend `npm run build` + `npx vitest run` (32).
- Push: swap origin to `https://github.com/ASTGD/ServerMind.git`, push, restore the SSH
  remote (`git@github.com:ASTGD/ServerMind.git`). `memory/` is never committed.

## Marketing

- `marketing-brief/` holds a self-contained brief + real screenshots for the design tool
  building the landing page (see `marketing-brief/README.md`).

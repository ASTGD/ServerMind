# ServerAlly docs — index

**Start here:** [`CONTINUE-HERE.md`](CONTINUE-HERE.md) — the current build status, everything
pending, and testing-plan status. `CLAUDE.md` (repo root) is the master file: product spec,
full dated Decisions Log, and coding standards — read it first for any new work.

## Feature design & reference docs (current)

| Doc | What it covers |
|---|---|
| [ALLY-MISSIONS.md](ALLY-MISSIONS.md) | The agentic mission engine: plan→run→observe loop, verification gate, budgets, durability, detached execution, cross-server transfer. |
| [ALLY-EVALS.md](ALLY-EVALS.md) | The automated regression harness for Ally's behavior (skill routing, safety invariants, live behavioral + injection-resistance evals). |
| [ALLY-RECIPES.md](ALLY-RECIPES.md) | Recipes — a browsable gallery of one-click missions built on top of mission-mode skills. |
| [ALLY-CAPABILITIES-TESTED.md](ALLY-CAPABILITIES-TESTED.md) | Evidence-based report of what's been proven live via the "shakedown cruise" — what to trust, what's still a claim. |
| [ASSETS-CATEGORIES-PLAN.md](ASSETS-CATEGORIES-PLAN.md) | The Assets/Categories model: Bare Metal/VPS/Hosting/Windows/Cloud, the Category Registry, Cloud Account import (5 providers), RDP. Kept current every phase. |
| [HOSTING-CYBERPANEL.md](HOSTING-CYBERPANEL.md) | Live-findings record from validating the CyberPanel hosting adapter against a real panel; the CLI-over-SSH pattern it landed on. |
| [AI-MODEL-LADDER.md](AI-MODEL-LADDER.md) | The Smart Model Ladder: routing chat/mission calls to different model tiers (high/default/low), reactive + proactive escalation. |
| [AI-METERING.md](AI-METERING.md) | The `ai_usage` ledger + per-customer monthly action allowance model, enforcement flow, safety rails. |
| [PRICING-FREE-VS-PRO.md](PRICING-FREE-VS-PRO.md) | Pricing v2: "open features, two meters" — every feature on every plan, plans differ only by server/action limits. |
| [WHMCS-INTEGRATION.md](WHMCS-INTEGRATION.md) | The WHMCS billing/provisioning integration (entitlement API + WHMCS module) that lets FireVPS sell Pro. |
| [SELF-HOSTED-LICENSING.md](SELF-HOSTED-LICENSING.md) | Strategy for a self-hosted, licensed edition (agencies/MSPs) — agreed, not yet built. |

## Testing & QA

| Doc | Status |
|---|---|
| [QA-CHECKLIST.md](QA-CHECKLIST.md) | A manual human-driven dogfooding script. **Not yet run** — see `CONTINUE-HERE.md` §4. |
| `../DEPLOY.md` §8 | Production smoke-test checklist. **Not yet run** against a real deploy. |
| [ALLY-CAPABILITIES-TESTED.md](ALLY-CAPABILITIES-TESTED.md) | What HAS actually been proven (the shakedown results). |

## Ops & deploy (repo root)

| Doc | What it covers |
|---|---|
| `../OPS.md` | Local dev: ports, start order, migrations, troubleshooting. |
| `../DEPLOY.md` | Production deploy runbook: Docker Compose behind CyberPanel/OLS, datastores, Sentry. |
| `../SECURITY.md` | Security review — verified-strong items, hardening history, and the current residual gap list (kept current as of 2026-07-06). |

## Archive (`archive/`)

Superseded or closed-out design docs, kept for history — not active references. Each was
folded into `CONTINUE-HERE.md` or `CLAUDE.md`'s Decisions Log before archiving, so nothing
useful was lost:

- `UPDATE-14-HARDENING.md` through `UPDATE-23-INSTALLED.md` — the original numbered
  build-spec docs (Jun 26–29), superseded by CLAUDE.md's Decisions Log once that became the
  living record.
- `SERVER-CATEGORIES.md` — superseded by `ASSETS-CATEGORIES-PLAN.md`.
- `SHAKEDOWN-TESTPLAN.md` — the shakedown mandate; executed, see `ALLY-CAPABILITIES-TESTED.md`.
- `RISK-3-SERVER-IDENTITY.md` — SSH fingerprint verification; now a permanent line in
  CLAUDE.md's Security Rules + schema rather than a tracked feature.

## Marketing

- `../marketing-brief/` — a self-contained brief (positioning, ranked features, finished
  copy, brand colors, logo, screenshot descriptions) handed to the design tool building the
  landing page.

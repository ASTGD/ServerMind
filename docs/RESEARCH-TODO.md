# Research TODO — standing tasks

> Captured 2026-07-23. Open research items to work through (not urgent; deliberate deep dives).
>
> ## ✅ DONE 2026-07-25 — items 1, 2 and 3 are answered by [MARKET-RESEARCH-2026-07.md](MARKET-RESEARCH-2026-07.md)
>
> That doc covers the deep competitor teardown (24 vendors across 4 segments, primary
> sources), re-verifies servermind.dev (**4 stars, 0 forks, solo side project — not a
> threat**), and sets out the feature + pricing conclusions. Raw per-vendor reports are in
> [research/](research/). **What remains open is the PM decision list in that doc's §9.**

---

## 1. Deep competitor research — and correct the "just like Ploi" framing

**Correction to record:** earlier in the MCP work, Ploi was described as "like ours." On a
closer look that is **not accurate** — and the user noticed. Ploi (and RunCloud, Forge,
SpinupWP, GridPane, Cloudways) are **Linux server *control panels*** — you configure
sites/PHP/databases through a web UI. **ServerAlly is different in kind:** AI-native (you
manage in plain language), any OS (Linux + Windows + hosting panels), an agentic assistant
(Ally) that plans/executes/verifies, and now an MCP connector. The overlap is only "manage
servers"; the *how* is fundamentally different.

**To do — a deep, honest teardown of each, answering:**
- What they actually are (panel vs. AI assistant vs. PaaS), who they target, pricing model.
- Where ServerAlly genuinely wins, and where these tools are stronger/more mature.
- What we should learn from them (UX, onboarding, reliability), NOT copy.
- Reconcile with the existing `docs/COMPETITOR-LANDSCAPE.md` +
  `docs/COMPETITOR-PLOI-TEARDOWN.md` (update if those overstate similarity).

Sites to research deeply: **ploi.io**, runcloud.io, forge.laravel.com, spinupwp.com,
gridpane.com, cloudways.com, plus the AI-native newcomers (any "AI VPS assistant" tools).

## 2. Check the "ServerMind" app found in Google search

The project was renamed **ServerMind → ServerAlly** (Decisions Log, 2026-06-29) because
"ServerMind" was already taken by ≥2 same-category products. The user found a **ServerMind**
app in Google search — **verify what it is:**
- Is it one of the ones the rename already flagged (servermind.io control plane /
  servermind.dev AI VPS assistant), or a new/different product?
- Same category? Trademark / SEO / brand-collision risk for us?
- Confirm the rebrand to ServerAlly still holds and there's no new conflict on
  `serverallyhq.com` / `serverally.ai`.

> Note: infra identifiers (DB name/user `servermind`, container names, repo folder
> `ServerMind`) were deliberately kept on rename to avoid breakage — that is expected, not
> a leftover to "fix".

## 3. Pricing & positioning rework — "the product is bigger than Ally"

**Direction the user set (2026-07-24):** ServerAlly is no longer positioned as *the Ally
product* — Ally is **one capability among many** (missions, MCP connector, terminal,
playbooks, monitoring, backups, hosting, RDP…). The UI already reflects this first step:
Ask Ally was demoted from a gradient hero button to a plain sidebar link, sitting as a peer
with Terminal under a "Tools" group (this change).

**To design after the Ploi + competitor research (item 1):**
- **Re-tier pricing on server quantity** (the market's actual value metric — see the
  verified research in [docs/PRICING-METRIC-RESEARCH.md] and [docs/PRICING-V3.md]: Ploi/
  RunCloud/Forge all price per server, not per AI-usage). Revisit the "two meters / actions"
  model against this.
- **Define the Pro feature set** independent of Ally (which features gate on plan vs. are
  open to all) — the current stance is "open features, two meters" (Decisions Log 2026-07-03);
  reconsider given the broader-product framing.
- **Reposition the marketing/onboarding** so Ally is a headline *feature*, not the whole
  pitch. Reconcile with the "Ally companion" tagline + [docs/PRICING-V3.md] Layer 1/Layer 2
  split (platform priced per server; AI is a separate, chosen layer).

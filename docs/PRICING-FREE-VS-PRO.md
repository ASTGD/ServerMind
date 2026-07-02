# ServerAlly — Pricing: Free vs Pro (+ AI packaging)

> **Status:** decisions locked (2026-07-02). **No billing/entitlement code written yet** —
> this doc is the spec to build against. Allowance numbers are starting points to tune once
> real AI token cost is known.

---

## 1. Summary

Two SaaS plans: **Free** and **Pro**.

- **Free** = *feel the magic on one box.* Enough to experience the AI (Ally) doing something
  real on 1–2 servers, so a new user hits the "whoa, it fixed my server" moment. Genuinely
  useful for a hobbyist; hits natural walls the moment you get serious.
- **Pro** = *run everything, automated, at scale.* Unlimited servers, the full Ally
  (fleet · batch · memory · proactive), automation (scheduler · backups · alerts), team, and a
  generous AI allowance.

A separate **Agency / self-hosted** edition exists (licensed, bring-your-own-key) — out of
scope here; see [SELF-HOSTED-LICENSING.md](SELF-HOSTED-LICENSING.md).

---

## 2. The AI is named "Ally"

The assistant persona is **Ally** — the ServerAlly brand as a companion ("someone on your
side"). User-facing copy: "Ask Ally", "Ally is thinking…", "Ally ran it on 3 servers", "Hand
to Ally". (Shipped in the UI already; commit `08cde87`.)

---

## 3. AI packaging — one subscription, two fuel options

The key decision that resolves the "do users pay twice for AI?" question: **No.** We were
conflating two different purchases:

1. **The software / features** — this is what Pro is.
2. **The AI fuel (tokens)** — who pays for inference.

**Model: AI is included in the plan (hosted "ServerAlly AI", powered by Ally), up to a
monthly quota. Bring-your-own-key is an *optional escape valve*, never a second bill.**

- **Included ServerAlly AI (default):** works out of the box, no key. Fair-use quota
  (measured in "actions" — see §9). This is what nearly all users use, especially the
  non-technical target audience.
- **Your own API key (optional):** unlimited — the user pays their own provider. Escapes the
  quota. Same plan price either way. The key is a *toggle*, not a purchase.
- **Overage:** when the included quota runs out → buy more credits (pay-as-you-go) **or** add
  your own key. Neither is a separate base subscription.

**Consequences already applied:**
- The bring-your-own-key UI is **demoted / hidden from Settings** for cloud users (gated
  behind `SHOW_AI_PROVIDER_SETTINGS = false` in `frontend/src/routes/Settings.tsx`, commit
  `88365dc`). The self-hosted edition flips it back on (that operator must configure a
  provider).
- Do **not** sell "ServerAlly AI" as a standalone SKU next to Pro — that's the double-bill
  trap. It's the bundled default fuel inside the plan.
- Keep **one Pro price** regardless of fuel choice (BYO users are not discounted — the value
  is the software, not the tokens).

---

## 4. The 4 gates (mental model)

Only four lines separate Free from Pro:

| Gate | Free | Pro |
|---|---|---|
| **Scale** | 1–2 servers | Unlimited servers & hosts |
| **Automation** | Manual, on-demand only | Scheduled backups, alerts, recurring tasks |
| **Full Ally** | A taste — per-server chat, ~30 actions/mo | Fleet, batch, memory, proactive + generous tokens |
| **Collaboration** | Solo | Team members + per-server roles |

---

## 5. Feature matrix

| Feature | Free | Pro |
|---|---|---|
| Servers connected | 1–2 | Unlimited |
| Connection types (Linux / Windows / hosting) | ✅ any, within limit | ✅ |
| Terminal (SSH) | ✅ | ✅ |
| File manager | ✅ | ✅ |
| Live metrics (CPU/RAM/disk now) | ✅ | ✅ |
| Installed / server insight | ✅ | ✅ |
| **Ally — per-server chat** | ✅ taste (~30 actions/mo) | ✅ generous quota |
| Ally — fleet mode (ask across all) | — | ✅ |
| Ally — cross-server batch | — | ✅ |
| Ally — saved thread history (Assistant page) | — (drawer only, ephemeral) | ✅ |
| Ally — AI script generator | — | ✅ |
| Ally — proactive monitoring / auto-heal / health score | — | ✅ (flagship, future) |
| Playbooks (one-click library) | ✅ standard | ✅ all + control-panel installers |
| Save / fork custom scripts (My Scripts) | — | ✅ |
| Scheduler (recurring tasks) | — | ✅ |
| Metrics history charts | — | ✅ |
| Alerts (email/webhook/Slack) | — | ✅ |
| Security audit | ✅ on-demand (limited) | ✅ unlimited + scheduled + history |
| Backups (auto + restore) | — | ✅ |
| Team members + roles | — (solo) | ✅ |
| Activity / command history | ✅ recent | ✅ full retention |
| Multi-language, notifications | ✅ | ✅ |

---

## 6. Reasoning on the decisions that matter

- **Ally on Free is deliberate — and limited.** The whole pitch is "AI runs your server." If
  Free can't *feel* that, nobody converts. Free gets real per-server Ally (it can install,
  fix, actually *do* things), capped at a small monthly action count. That cap is the best
  salesperson — users hit it right after the "wow".
- **Automation is the cleanest Pro line.** Scheduler, backups, alerts = "set it and forget
  it" — the definition of a paid capability. Backups especially: people pay to not lose sleep.
- **The powerful Ally is the Pro engine.** Fleet, batch, saved memory, proactive only make
  sense with more than 2 servers — so they align with the scale gate and let Ally drive
  upgrades, not just hook.
- **Don't gate by platform.** Free can connect Windows/hosting within the 1–2 limit. Gate by
  *count and capability*, not OS — gating by OS just annoys a buyer we want.
- **Security audit is a Free hook.** On-demand scan → "Grade D, here's what's wrong" is a
  great activation moment. Scheduled/continuous scanning is the Pro version.
- **Don't over-cripple Free.** Thin Free never activates. The 1–2 server limit + AI action cap
  already do the heavy lifting; keep terminal, files, and basic playbooks in Free.

---

## 7. Upgrade triggers (the walls that convert)

1. "I need a 3rd server." → scale wall
2. "I'm out of Ally actions this month." → AI wall (hit right after they fall in love)
3. "I want Ally to watch all my servers / do it automatically." → fleet + automation
4. "I need my teammate in here." → collaboration
5. "I want my backups to just happen." → peace-of-mind wall

---

## 8. Pricing shape

| Tier | Servers | AI fuel | For |
|---|---|---|---|
| **Free** | 1–2 | Included, small quota (no key) | Try it, feel the "aha" |
| **Pro** | Unlimited | Included generous quota + advanced Ally; add own key → unlimited | Founders, SMBs — mass market |
| **Agency / self-hosted** | Unlimited | Bring your own key (they host); optional hosted add-on | Agencies, MSPs, privacy/cost-sensitive |

---

## 9. AI allowance (tune later)

- Unit = **"actions"** (user-friendly), not tokens. One action = one Ally request → plan →
  execute.
- **Free:** ~25–40 actions / month.
- **Pro:** ~500–1,000 / month or soft fair-use, plus overage credits and the BYO-key escape.
- Numbers are placeholders — set them against real per-action token cost before launch.

---

## 10. Implementation notes (for when billing is built)

- **Entitlement map first, billing second.** Define a single config that declares, per
  feature, whether it's Free or Pro, plus the numeric limits (server count, AI actions/month).
  Expose `canUse(feature)` and `withinLimit(kind)` checks that **both the UI and the API**
  read, so gating is enforced server-side, not just hidden client-side.
- **AI fuel decision at each call:** if the user has their own key → run on it, unmetered;
  else → draw from the included quota; if exhausted → prompt to add a key or buy credits.
  The hosted gateway already meters usage — wire that meter to the plan quota.
- **Billing provider:** Lemon Squeezy / Stripe / Paddle (TBD). Wire the Upgrade modal
  (`frontend/src/components/layout/UpgradeModal.tsx`) to real checkout.
- **Right now (pre-billing):** the instance's AI is configured via `.env`
  (`ANTHROPIC_API_KEY` / `AI_PROVIDER`); no per-user limits are enforced yet.
- **Cloud vs self-hosted:** `SHOW_AI_PROVIDER_SETTINGS` hides BYO-key UI for cloud; self-hosted
  turns it on.

---

## 11. Open questions to settle before launch

- Exact Free action cap + Pro allowance (needs token-cost data).
- Pro price point(s) — monthly/annual.
- Overage: pay-as-you-go credits vs hard stop vs BYO-key prompt.
- Free saved-history: truly none, or a small retained amount?
- Trial: does Pro get a time-limited trial, or is Free the trial?

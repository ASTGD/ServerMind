# Pro features plan — what we charge more for, and why

> **Created 2026-07-25.** Direction set by the owner:
> *"ServerAlly is not a replacement of these control panels. I want to add some more
> features so we can separate plans based on features."*
>
> Companion to [MARKET-RESEARCH-2026-07.md](MARKET-RESEARCH-2026-07.md) (what the market
> has) and [PRICING-V3.md](PRICING-V3.md) (how we price). This doc answers a narrower
> question: **which features go behind Pro, and which never do.**

---

## 1. Positioning — settled

**ServerAlly is not a control panel and will not become one.** We sit *on top of* servers
and panels: we operate, diagnose, repair, and prove the repair worked.

This matches the market research (§8.1 *"Do NOT become a control panel"*): building the
Tier-1 panel baseline means a mail stack, a nameserver, phpMyAdmin, FTP and a WordPress
installer — years of work, against **five free products**, in a category whose own users
rate it NPS 28.

### ⚠️ Correction to the Wave 1 list

Two items in [MARKET-RESEARCH-2026-07.md](MARKET-RESEARCH-2026-07.md) §8.2 Wave 1 were
**panel features and should not have been there**:

| Item | Verdict |
|---|---|
| ~~Sites model for plain servers~~ | **Dropped** — that is a panel's job |
| ~~PHP version management~~ | **Dropped** — that is a panel's job |
| ~~SSH key + firewall managers~~ | **Deferred** — borderline; revisit only if customers ask |

The three already shipped are correct and stay: **offsite backups**, **uptime monitoring**,
**log viewer** — all operator features, not panel features.

---

## 2. The competitive floor: we compete with free

**servermind.dev — re-checked 2026-07-25 against the product site**, not just its GitHub
repo. An earlier note called it "a solo side project, not a threat". **That was too
dismissive** and is corrected here.

What it actually ships: fleet management (agents dial out to a controller), a live
dashboard, user-defined custom commands, alerts for disk/memory/downed services **and
expiring TLS certificates**, daily health emails, a desktop app, and an optional WireGuard
mesh.

Three facts that shape our pricing:

1. **Completely free, MIT, no paid tier at all.**
2. **The AI is free too** — Google Gemini by default, ~1,500 requests/day, no card.
3. Its headline claim is **"Nothing leaves your box."**

> **Therefore the lens for every Pro feature:**
> ### A good Pro feature is one that a free, self-hosted, single-box tool cannot copy.

That rules in: an **outside vantage point**, a service that runs **while you sleep**,
**multi-tenancy**, **accumulated history**, and anything **client-facing**.

It also means we should never try to win on "we have AI" or "we have a dashboard" —
those are free elsewhere.

---

## 3. The tier story, in one line each

- **Free** — *"You ask, Ally does."* One or two servers, on demand.
- **Pro** — *"Ally works while you sleep, across your fleet, and you can show clients."*

---

## 4. The Pro feature set

Ranked. Each row states the feature, why someone pays, and why a free self-hosted tool
cannot match it.

| # | Feature | Why it's worth paying for | Why free tools can't copy it |
|---|---|---|---|
| **1** | **Ally on autopilot** — scheduled missions (*"every night, check X, fix Y, report"*) | Turns Ally from a tool you use into staff you employ. **No product in the 15+ AI tools researched has this** | Needs an always-on hosted service |
| **2** | **Auto-fix policy** — you choose which problems Ally may fix *without asking* (restart a dead service, clear a full disk), inside guardrails | The biggest value jump in the product. Our verification gate is what makes it safe to offer at all | Requires the safety architecture nobody else has |
| **3** | **Client reports & white-label** | We already generate incident/server reports — this is packaging. Agencies **resell** it | Multi-tenant + branding |
| **4** | **Public status pages** | Market-standard Pro feature; we now have the uptime data | Needs a public hosted endpoint |
| **5** | **On-call escalation** — SMS / Slack / Telegram, repeat until acknowledged (Free = email only) | The difference between "an email you missed" and "you woke up" | Needs our infrastructure + paid SMS |
| **6** | **History retention** — 7 days free vs 12 months Pro (metrics, uptime, logs, scans) | Trend, evidence, and proof over time | Honest: storage genuinely costs us |
| **7** | **Custom runbooks** — teach Ally *your* procedures | Deep moat; very sticky for agencies | Needs our skill engine |
| **8** | **API keys + webhooks** | The market gates this (RunCloud puts API behind $49) | — (parity feature) |
| **9** | **SSL expiry monitoring** | A real gap — servermind.dev has it, we do not. Cheap | — (parity feature) |

### Never gate these

**Backups · security scans · threat detection · incident response · the verification gate.**

Ploi hides backups and monitoring on its €8 plan and it is their loudest complaint. Keeping
safety open on every plan is a differentiator we can **say out loud** in a comparison, and
it is the right thing to do besides. See [MARKET-RESEARCH-2026-07.md](MARKET-RESEARCH-2026-07.md) §7.3.

---

## 5. Build order

**Flagship first: #1 + #2 together as one product — "Ally on autopilot".**

They are one coherent idea (*Ally works on its own, within limits you set*), they are the
clearest answer to *why pay*, and they are mostly **wiring rather than invention**: the
mission engine already has durable execution, resumability, per-step approval, a budget,
and the adversarial verification gate.

Then, in order: **#4 status pages** (uptime data already exists) → **#9 SSL expiry** (cheap,
closes a named gap) → **#5 escalation** → **#3 client reports & white-label** →
**#6 retention** → **#8 API keys** → **#7 custom runbooks**.

---

## 6. Status

| # | Feature | Status |
|---|---|---|
| 1 | Ally on autopilot (scheduled missions) | ✅ **Shipped 2026-07-25** |
| 2 | Auto-fix policy | ✅ **Shipped 2026-07-25** (same feature) |
| 3 | Client reports & white-label | ⬜ Not started |
| 4 | Public status pages | ✅ **Shipped 2026-07-25** |
| 5 | On-call escalation | ⬜ Not started |
| 6 | History retention tiers | ⬜ Not started |
| 7 | Custom runbooks | ⬜ Not started |
| 8 | API keys + webhooks | ⬜ Not started |
| 9 | SSL expiry monitoring | ✅ **Shipped 2026-07-25** |
| — | *Offsite backups* | ✅ Shipped 2026-07-25 (stays free — safety) |
| — | *Uptime monitoring* | ✅ Shipped 2026-07-25 (free tier; depth is Pro) |
| — | *Server log viewer* | ✅ Shipped 2026-07-25 (stays free) |

## 7. Open question for the PM

**Enforcement is still off** — `ENFORCE_PLAN_LIMITS=false`, so every user currently has
everything. These features can be *built* and *marked* Pro without arming the wall; the
numbers (and the switch) come from the beta cohort per [PRICING-V3.md](PRICING-V3.md) §6.

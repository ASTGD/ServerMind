# ServerAlly — Self-hosted, licensed edition (strategy + how it works)

> Plain-English product doc. Two ways to sell ServerAlly:
> 1. **Hosted (SaaS)** — we run it, customers pay a subscription, use it on our
>    website. Setup: see [DEPLOY.md](../DEPLOY.md).
> 2. **Self-hosted (this doc)** — customers buy a package, install it on *their own*
>    VPS, activate a license, and use it. We never touch their servers or data.
>
> This doc covers option 2: why it fits, the trade-offs, and exactly how the license
> system and the customer's buy→install→activate journey work.

---

## 1. The idea

Sell ServerAlly as a downloadable package. A customer buys it, installs it on their
own VPS with one command, enters a license key to activate it, and uses it. We provide
updates and support; we don't host anything for them.

## 2. Why this fits ServerAlly unusually well

- **Privacy is the killer pitch.** ServerAlly holds people's server passwords and SSH
  keys. The biggest objection to *any* hosted tool is "you have my server logins."
  Self-hosted turns that into your strongest line: **"Your credentials never leave your
  own box — we never see them."** For a credentials-handling tool, that removes the #1
  reason to say no, and most competitors are hosted-only.
- **Near-zero cost and risk for us.** No servers to rent, scale, or keep up; and we're
  not sitting on a giant pile of everyone's server passwords (which would make *us* the
  target). Each customer runs their own copy.
- **It's mostly already built.** The app already runs on a single VPS via Docker Compose
  (incl. a bundled database + cache — the `selfhost` profile). The main *new* piece is
  the license system.
- **Recurring revenue still works** — an annual license that includes updates + support.

## 3. The honest trade-offs

- **Self-hosting is technical**, but ServerAlly's end users are non-technical. So this
  model skews the *buyer* more technical. The upside: that points at **agencies and
  hosting/IT providers** — who buy one license and manage all their clients' servers
  with it. Often a *better-paying* customer than a lone blogger.
- **Support is harder** — it's running on *their* server, with their quirks.
- **Updates become the customer's job** — we need a dead-simple "update" command.
- **Some piracy is unavoidable** — a license check deters casual copying, not a
  determined cracker. We manage it; we don't eliminate it.

## 4. Who we sell to

Primary: **agencies, MSPs, hosting resellers, developers** — technical enough to
self-host, and they'll pay for a tool that runs their business. We are *not* locked in:
the same codebase can later offer the hosted (SaaS) version for non-technical users, so
we can start self-hosted and add SaaS down the road.

## 5. How the license system works (plain English)

Think of it like activating any paid app (Windows, a game, design software):

1. **Buy → get a key.** On purchase, the customer receives a license key (a code).
2. **Install → app asks for the key.** On first run, ServerAlly's setup wizard asks for
   the key.
3. **Activate → app checks the key** with our small license service: "is this key valid,
   paid, and not expired?" If yes, the app unlocks and remembers it.
4. **Ongoing → a quiet re-check** every so often (e.g. daily) confirms the license is
   still valid (paid, not refunded, not expired).
5. **Grace period.** If our license service is briefly unreachable, the app keeps working
   for a grace window (e.g. 7–14 days) so a blip on our side never locks out a paying
   customer. Only a *confirmed* invalid/expired key disables the paid features.
6. **Renewal/expiry.** When the license lapses, the app shows a friendly "renew to keep
   updates + support" message. (Decide: does it keep working read-only, or stop? — see §10.)

**Privacy guarantee (critical):** the license check sends **only the license key** and a
random install id — *never* server passwords, customer data, or AI prompts. This is what
keeps the "we never see your data" promise honest, and we should say so plainly in the
product and the marketing.

**One key = how many installs?** A policy decision (§10). Common: 1 key = 1 active
install; agency/reseller tiers allow N installs.

## 6. The customer's journey (buy → download → install → activate → use)

1. **Buy** on our store page → receives the license key + a download/install link by email.
2. **Get a VPS** (any provider — DigitalOcean, Hetzner, Vultr…). A small box is enough.
3. **Install** — paste **one command** into the VPS. It pulls ServerAlly, sets up the
   bundled database + cache, and starts everything. (Goal: under five minutes, no
   technical knowledge beyond copy-paste.)
4. **Open the app** at their server's address → a **setup wizard**:
   - enter the **license key** → activate;
   - create the **admin account**;
   - **choose AI** — paste your own key (any provider) *or* subscribe to ServerAlly AI (§7);
   - done.
5. **Use it** — add servers, chat, run playbooks — exactly as today.

## 7. The AI brain — two ways, the customer's choice

ServerAlly needs an AI model to power chat + script generation. We offer **both**
options in the setup wizard, so each customer picks their own privacy/convenience
trade-off:

**A. Bring your own key (any provider) — maximum privacy.**
The customer connects their own AI account and pastes their key. We support **multiple
providers** — Anthropic (Claude), OpenAI (GPT), Google (Gemini), and others — so they
use whatever they already have or trust. Their prompts go straight from their server to
the provider; nothing passes through us; the AI cost is theirs. Best for
privacy-conscious buyers, agencies, and the technical crowd.
*Build:* a small provider-abstraction layer so the app can talk to any provider, plus a
"pick provider + paste key" step in setup.

**B. ServerAlly AI subscription — no key needed, just works.**
For customers who don't want to get an API key (the hardest setup step), we offer our
own AI as a paid add-on. They pay us a monthly subscription (or usage credits); their
requests go through a small **AI gateway** we run, which uses our keys and meters usage.
Removes all AI setup friction and adds a recurring revenue stream. **Status: built** —
the gateway lives in `gateway/` (validate token → forward with our key → meter monthly
usage); the billing-platform webhook to auto-issue tokens is the remaining piece.

> **Privacy note to state plainly:** with **A**, nothing reaches us. With **B**, the AI
> *conversation* (the request, server details, command output) passes through our
> gateway — but **server passwords/keys never go to the AI in either case** (they're only
> used to connect). So: own key = maximum privacy; our subscription = maximum
> convenience. The customer decides.

What we'd run for **B**: one small cloud service (the AI gateway), which can live
alongside the license server. It needs usage caps/credits + abuse monitoring (so a
runaway customer can't rack up huge AI bills) and pricing that covers the AI cost with a
margin.

## 8. Updates

A simple **"update" command** (or an in-app "Update available → click to update" button)
that pulls the new version and restarts. Keeps customers off old, buggy/insecure
versions and keeps the support burden down.

## 9. What we build vs. buy off-the-shelf

We **don't** build payments or key-issuing ourselves. A licensing/payment platform —
**Lemon Squeezy, Gumroad, or Paddle** — already sells software, takes payment, and
**issues + validates license keys** via an API. So:

- **Off-the-shelf (the platform):** store page, checkout, tax/VAT, key issuing, key
  validation API.
- **We build:** the in-app license check (calls the platform's validate API + grace
  period), the one-command installer, the setup wizard, and the update command.

That shrinks "build a license system" down to a small, well-scoped piece.

## 10. Open decisions (to settle before building)

- **Licensing platform:** Lemon Squeezy vs Gumroad vs Paddle (all handle keys + payment).
- **AI:** bring-your-own-key (multi-provider) is decided; whether to *also* run the
  ServerAlly AI subscription (option B) — recommended for reach + revenue, but adds a
  small gateway service + AI-cost/abuse management to operate.
- **Installs per license:** 1 active install for solo, N for agency/reseller tiers.
- **On expiry:** keep working read-only, or disable paid features? (Lean: stays usable,
  but updates + support stop — least punishing to a paying customer.)
- **Pricing shape:** one-off + paid upgrades, or annual subscription (updates + support).
- **Offline/air-gapped customers:** offer a manual/offline activation path for buyers
  whose servers can't phone home at all.

## 11. Status

Strategy agreed (2026-06-28). Not yet built. The app is already Docker-packaged for
self-hosting (`docker-compose.prod.yml` + `selfhost` profile); the new work is the
license check, the one-command installer/wizard, and the updater. Tracked in CLAUDE.md
(Decisions Log + Future Features Backlog).

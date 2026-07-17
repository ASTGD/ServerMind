# ServerAlly — Marketing Brief

Everything a designer needs to build the ServerAlly marketing landing page. **Self-contained** and
**factual to the actual product** — features are tagged **LIVE / PARTIAL / ROADMAP**; nothing here
is invented. (Prepared 2026-07-06 from the live product + `CLAUDE.md`.)

## Files

| File | What it is |
|---|---|
| [`00-overview.md`](00-overview.md) | Positioning, the problem, target audience, competitors, tone of voice. |
| [`01-features.md`](01-features.md) | Every real feature, **ranked** (the hero + supporting order), each tagged LIVE/PARTIAL/ROADMAP. |
| [`02-copy.md`](02-copy.md) | Finished, ready-to-publish copy: 3 hero headline options, CTAs, how-it-works, feature sections, proof points, closing CTA, FAQ. |
| [`03-brand.md`](03-brand.md) | Name, tagline, exact brand colors (HEX + HSL), logo, typography, personality keywords. |
| [`assets/logo/`](assets/logo/) | Real logo — `serverally-mark.svg` + `.png` (the badge) and `serverally-logo.svg` + `.png` (mark + wordmark). SVG is source of truth. |
| [`assets/screenshots/screenshots.md`](assets/screenshots/screenshots.md) | Exact descriptions of 7 real, shipped product screens + the route to capture each. |

## Design intent — the ONE thing

**Make a non-technical visitor feel: "Oh — I can finally run my server myself, safely, just by
asking."**

The single action we want: **Start free** (add a server + ask Ally something). Everything on the
page should reduce the fear of managing a server and build trust that Ally is competent and safe.

Lead with the **hero feature — Ally, the AI companion that manages any server in plain English**
(`01-features.md`). The strongest proof visual is the **Ally chat** (a real plain-English answer)
and the **fleet report** (Ally noticing problems for you) — see `assets/screenshots/`.

## Guardrails for the design/copy
- **Truthful only.** Present PARTIAL/ROADMAP items honestly (e.g. Windows & cPanel work but aren't
  fully live-validated; live RDP streaming is "coming soon"). Don't imply usage stats — ServerAlly
  is **pre-launch**, so there are no "10,000 servers managed"-type numbers yet.
- **Tone:** calm, reassuring, plain-spoken, human — *not* hacker/terminal-dark by default.
- **Confirm before publishing:** final pricing numbers and the production domain.

## 04 — Landing site v2 (build brief)

**[04-landing-site-v2.md](04-landing-site-v2.md)** — the spec for the 5-page marketing site
(Claude Design / Fable 5). Hero pattern, brand tokens, page-by-page, and the hard rules:
no screenshots on the page (redraw everything), no invented metrics, exactly one GIF.

# 03 — Brand

## Name & tagline
- **Product name:** **ServerAlly** (one word, capital S, capital A — "Server" + "Ally").
  - The wordmark styles it **Server** in the foreground/text color and **Ally** in the brand
    gradient (indigo → violet).
- **AI persona name:** **Ally** (the companion the user talks to).
- **Tagline:** *Your AI companion to manage, automate, and secure any server — without the expertise.*
  - Short form: *Manage any server in plain English.*
- **Domains (targets):** serverallyhq.com · serverally.ai (bare `serverally.com` is taken).

## Logo
Real, in-repo assets (copied into `assets/logo/`):
- **The mark** — a rounded "squircle" badge with an indigo→violet→purple gradient, holding a
  **white shield** ("Ally" = protector) with an **AI spark** (four-point sparkle) inside it.
  Meaning: *an AI companion that guards your server.*
- **The lockup** — the mark + the "ServerAlly" wordmark ("Ally" in the gradient).
- Source of truth is **SVG** (`serverally-mark.svg`, `serverally-logo.svg`). The mark is also the
  app favicon.

## Brand colors (exact, pulled from the live app's theme)
The palette is an **indigo→violet→purple** family on clean slate neutrals (light + dark modes both
exist). HEX values are the app's real tokens.

**Brand gradient (the signature — used in the logo, avatar, and accents):**
| Stop | HEX | Note |
|---|---|---|
| Indigo | `#6366F1` | gradient start (Tailwind indigo-500) |
| Violet | `#8B5CF6` | gradient middle (violet-500) |
| Purple | `#A855F7` | gradient end (purple-500) |
| Spark violet | `#7C3AED` | the AI spark inside the mark (violet-600) |

**Core UI colors:**
| Role | HEX (approx) | HSL (exact, from `:root`) |
|---|---|---|
| Primary (buttons, links, focus) | `#5048E5` | `243 75% 59%` |
| Primary hover / deep accent | `#3B32B0` | `244 55% 45%` |
| Text / near-black | `#020817` | `222 84% 5%` |
| Muted text | `#64748B` | `215 16% 47%` |
| Border | `#E2E8F0` | `214 32% 91%` |
| Muted surface | `#F1F5F9` | `210 40% 96%` |
| Background | `#FFFFFF` | `0 0% 100%` |
| Success (used for "online"/verified) | `#22C55E` | green-500 |
| Danger / destructive | `#EF4444` | `0 84% 60%` |

**Dark mode** (also live): background near-black navy `#020817`, primary lightens to a periwinkle
`#8B9CF9` (`234 89% 74%`).

## Typography
- The app uses the **default system / sans-serif UI stack** (no custom brand font is committed).
- **Recommendation for the marketing site** (ROADMAP — designer's choice): a clean, modern
  geometric sans — e.g. **Inter**, **Geist**, or **Satoshi** for body/UI, optionally a slightly
  warmer display face for the hero. Keep it friendly and highly legible (non-technical audience).

## Personality / mood keywords for visual design
`calm` · `trustworthy` · `modern` · `approachable` · `smart` · `clean` · `reassuring` ·
`human` (not "hacker/terminal-dark by default").

**Visual direction:** friendly and premium, not intimidating. Lean on the indigo→violet gradient
for warmth and "intelligence," lots of whitespace, soft rounded corners (the app uses ~0.5rem
radius; the logo badge is a squircle). Show **real product UI** (calm light dashboards, the chat
with plain-English answers) rather than green-on-black terminal clichés — the point is that
ServerAlly is *not* scary. A subtle terminal/command accent is fine as a supporting motif, never
the hero aesthetic.

## Existing brand references
- The running app is the primary reference — see the real screenshots in `assets/screenshots/`.
- Logo + gradient live in `frontend/src/components/brand/Logo.tsx` and `frontend/public/favicon.svg`.
- Full product facts: repo `CLAUDE.md` (identity section) and `docs/ASSETS-CATEGORIES-PLAN.md`.

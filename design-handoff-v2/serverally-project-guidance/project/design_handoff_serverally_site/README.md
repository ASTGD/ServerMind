# Handoff: ServerAlly Marketing Site (Home · Pricing · Trust & Security · How It Works stub)

## Overview
A 4-page marketing site for **ServerAlly** — an AI companion that manages, automates, and secures any server in plain English. Built from the `marketing-brief/` in the ServerMind repo. Three pages are complete (Home, Pricing, Trust & Security); **How It Works** is a placeholder stub whose content arrives in a follow-up build (it will absorb the animated scroll-journey design, included here as `ServerAlly Journey.dc.html` for reference).

## About the Design Files
The files in this bundle are **design references created in HTML** — prototypes showing intended look and behavior, **not production code to copy directly**. The task is to recreate these designs in the target codebase's environment (Next.js/React/Vue/etc.) using its established patterns, or to pick an appropriate framework if none exists yet.

**Previewing locally:** the pages share a runtime (`support.js`) and a shared nav component (`SiteNav.dc.html`) fetched at load — so open them through a local static server (`python3 -m http.server`), not `file://`.

## Fidelity
**High-fidelity.** Colors, type, spacing, copy, and interactions are final design intent. Recreate pixel-perfectly. The only intentionally unfinished parts are marked in-page: `$[TBD]/mo` prices, the testimonials (HTML comment `PLACEHOLDER — replace with real testimonials`), the "Your data" policy box, and the `security@serverally.ai` address.

## Site map & shared nav
1. Home (`Home.dc.html`)
2. How It Works (`How It Works.dc.html` — stub; keep the working nav link + `#shakedown` anchor)
3. Pricing (`Pricing.dc.html`)
4. Trust & Security (`Trust and Security.dc.html` — nav label uses "&")

Shared sticky header on every page (`SiteNav.dc.html`): white 88% + `backdrop-filter: blur(14px)`, bottom border `#E2E8F0`, logo left, center links (flex — **do not hard-code 4 slots**, a 5th item is planned), gradient "Start free" pill right (→ Pricing). Active page = 16×3px gradient underline dot. Below 920px: links collapse into a menu button + dropdown. Footer on every page: logo · 4 links · "© 2026 ServerAlly · Pre-launch".

## ⚠ Critical rule: persistent frames
Wherever an animated device frame appears (a mockup window with Ally's icon in its header — chat panels, terminals, file managers, report cards): **the outer frame and its header mount once and stay at `opacity: 1` for their entire scroll range. Only inner content animates/crossfades.** Never put a looping opacity animation on the frame container. This bug shipped twice before; `ServerAlly Journey.dc.html` in this bundle is the corrected reference.

## Screens (summary — full detail is in the files themselves)
### Home — 10 sections
1. **Hero**: badge (mark + "Meet Ally — your AI server companion"), H1 "Manage your servers by just *talking to Ally*." (gradient span), tagline sub, CTAs (gradient "Start free" → Pricing; outline "See how it works" → How It Works), reassurance line, floating browser frame with `01-assets.png` (slow float 9s + slight scroll parallax −0.07·scrollY, aurora blobs behind).
2. **What is ServerAlly**: kicker + H2 "An expert teammate for people who'd rather not be sysadmins." + 3 cards (AI-native / Any server, any hosting / Your language — 8 languages).
3. **Top moves**: 2 portrait product frames (`30-…`, `32-…`, aspect 3/3.6, object-fit cover, object-position 50% 10% and 50% 72%) + full-width `05-fleet-report.png` frame. Scroll-revealed once (no loops).
4. **Safety strip**: H2 "Built to be trusted with root." + link → Trust & Security + 4 cards (Encrypted credentials · Asks before risky steps · Reversible by design · Role-based access).
5. **Pricing teaser**: "Every feature. Every plan." + Free/Pro mini cards (2 servers·30 actions / 15 servers·1,000 actions, `$[TBD]/mo`) + link → Pricing.
6. **Use cases**: 4 cards, each a user chat bubble ("My WordPress site is broken — fix it." etc.) + outcome chip (green ✓ pulse; 4th is amber "Heads-up sent before the disk filled").
7. **Shakedown teaser** (dark `#0F172A`): H2 "We tried to make Ally destroy a live server. It refused." + 2 beat cards (`rm -rf /` → BLOCKED; `uploads/x9.php` → QUARANTINED) + "See the full story" → `How It Works.dc.html#shakedown`. Tease only — full story lives on How It Works.
8. **Testimonials**: 3 fictional placeholder cards (Dana M. / Rafael O. / Priya K.) — marked with HTML comment.
9. **CTA**: gradient panel, floating white mark, "Manage your servers like a pro — without being one.", white "Start free" pill.
10. **FAQ**: 8-item single-open accordion (Linux knowledge, mistakes/reversibility, supported servers, credential safety, approval model, pricing model, team roles, languages).

### Pricing
Hero ("Every feature. *Every plan.*", loud differentiator, `$[TBD]` disclaimer) → **dials panel**: Free|Pro segmented control (sliding white thumb, 340ms `cubic-bezier(0.22,1,0.36,1)`), two SVG ring dials (r=56, dasharray 351.86, gradient stroke) whose numbers tween 750ms cubic-out — servers 2↔15, actions 30↔1,000 — with green bar "These two dials are the *only* difference." Auto-demos once on load (Free→Pro at 1.6s, back at 3.4s unless touched). → "On both plans. All of it." 10 feature chips → plan cards (Free / Pro "More scale", `$[TBD]/mo`) → action explainer (one action = one AI request) → 3-item FAQ (action definition; overage = pause until reset or upgrade, servers untouched; BYO AI key = yes, optional).

### Trust & Security
H1 "Security and privacy, built in from day one" + 4 real trust-marker chips (**no SOC2/ISO/HIPAA badges**). → "How Ally keeps your servers safe": dark blocklist card (Linux: `rm -rf /`, `mkfs.ext4 /dev/sda`, `dd of=/dev/sda`; Windows: `format C:`, `Remove-Item C:\ -Recurse -Force`, `vssadmin delete shadows /all` — each with red BLOCKED pill) + 3 cards (risky steps ask first / reversible beats destructive / "done" = independently verified read-only). → "How your credentials are protected": AES-256-GCM at rest · never logged, never returned by any API after creation · SSH host fingerprints verified on every reconnect · command rate limits. → "Proven, not just promised" dark strip → link to How It Works `#shakedown`. → "Who can do what": Viewer (can NEVER execute, even if misconfigured) / Operator / Admin, per-server access. → "Your data": dashed box `[TBD — insert real data retention / training-data / sub-processor policy here before launch]` — makes no claims. → Responsible disclosure: `security@serverally.ai` (placeholder).

### How It Works (stub)
Nav + centered notice ("The full walkthrough lands here next.") + dashed `#shakedown` anchor block + footer. Will be replaced by the animated journey (reference: `ServerAlly Journey.dc.html`).

## Interactions & Behavior
- **Scroll reveals**: `jRise` 700ms ease, staggered 80–150ms per element, `animation-play-state` toggled by IntersectionObserver (threshold ~0.12) — **default state is `running`** so a failed observer degrades to "everything animates," never "everything invisible." Reveals play once (fill: both).
- **Hover**: buttons lift `translateY(-1/-2px)` + deepen shadow, 250ms; links shift to `#5048E5`.
- **FAQ**: one open at a time; chevron rotates 180° 250ms.
- **Reduced motion**: all animations set to `none` (finished states shown).
- **Aurora heroes**: 2–3 blurred radial blobs (indigo/violet at 18–30% alpha), 17–22s drift loops, white gradient fade at bottom.

## State Management
Per page, minimal: `w` (viewport for breakpoints ~768/920/1120), `faq` (open index, −1 = none), nav `menuOpen`; Pricing adds `plan` + rAF-tweened `servers`/`actions`. No data fetching.

## Design Tokens
- **Font**: Geist (Google Fonts) 400/500/600/700/800; mono = `ui-monospace, SFMono-Regular, Menlo`.
- **Colors**: page `#FFFFFF`; alt section `#F8FAFC`; dark section `#0F172A` (borders `#1E293B`/`#334155`, text `#F8FAFC`/`#94A3B8`); text `#0F172A`; secondary `#64748B`; muted `#94A3B8`; border `#E2E8F0`; brand gradient `135deg #6D5EF3 → #8B5CF6 55% → #A855F7`; link/CTA `#5048E5` (hover `#4338CA`); indigo tint `#EEF2FF`/`#C7D2FE`; success `#16A34A` on `#F0FDF4` border `#BBF7D0`; danger `#DC2626` on `#FEF2F2`; warning `#B45309` on `#FFFBEB` border `#FDE68A`.
- **Type scale**: H1 `clamp(2.1rem, 5–6vw, 4.4rem)`, ls −0.035em, lh 1.05; H2 `clamp(1.8rem, 3.4vw, 2.7rem)`, ls −0.03em; kicker 13px, 600, uppercase, ls 0.08em, `#6D5EF3`; body 14–17.5px, lh 1.6–1.65.
- **Spacing**: container max 1200px, x-pad `clamp(20px, 4vw, 32px)`; section y-pad `clamp(64px, 8vw, 112px)`; card padding 22–32px; grid gaps 12–28px.
- **Radius**: chips/inputs 9–14px; cards 16–18px; panels 20–26px; pills 9999px.
- **Shadows**: cards `0 24px 60px rgba(15,23,42,0.10)`; hero frame `0 40px 90px rgba(15,23,42,0.16)`; CTA pill `0 10px 28px rgba(109,94,243,0.34)`.

## Assets
`marketing-brief/assets/` (from the ServerMind repo): `logo/serverally-logo.svg`, `logo/serverally-mark.svg` (white version = CSS `filter: brightness(0) invert(1)`), real product screenshots `screens/01-assets.png`, `05-fleet-report.png`, `30-sidechat-mission-progress.png`, `32-sidechat-mission-verified.png`. More screenshots exist in the repo (`22-refuse-wipe-*`, `23-webshell-quarantine-approval`, etc.) for the upcoming How It Works page.

## Files
- `Home.dc.html` — Home (10 sections)
- `Pricing.dc.html` — Pricing with animated dials
- `Trust and Security.dc.html` — Trust & Security
- `How It Works.dc.html` — stub with `#shakedown` anchor
- `SiteNav.dc.html` — shared nav component
- `ServerAlly Journey.dc.html` — animated scroll-journey (design source for How It Works; frame-fix reference)
- `support.js` — prototype runtime (preview only; not production code)

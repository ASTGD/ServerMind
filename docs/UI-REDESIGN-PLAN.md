# ServerAlly UI redesign — premium SaaS, built with Fable 5

> **Status: BUILT — all 6 phases shipped (2026-07-22).** Executed with Fable 5, one phase per
> pass, browser-verified in both themes between phases. See the CLAUDE.md Decisions Log entry
> (2026-07-22) for what shipped and the deliberate deviations. Kept as the design reference for
> the primitives/tokens vocabulary.

## Context

ServerAlly is going to market as a hosted SaaS product, so the app UI now has to look
like one. The current UI grew feature-by-feature and three problems have accumulated:

1. **Every page sprawls edge-to-edge.** `Layout.tsx`'s content area is
   `<main className="flex-1 overflow-auto p-6">` with **no max-width and no centering**, so on
   a wide monitor every page (Dashboard, Servers, Missions, Reports, Settings…) stretches full
   width and reads as messy. Only a few document-style pages self-constrain.
2. **No design-system layer.** There are **no shared UI primitives** (no shadcn/ui) — cards,
   buttons, badges, and inputs are ad-hoc Tailwind repeated in every file (`rounded-xl border
   border-border bg-card p-4` is the de-facto "card"). There is no webfont; the app uses the
   system font. Brand gradient and status colors are hardcoded outside the token system.
3. **Specific weak spots the user named:** the Dashboard is not built for a SaaS customer (no
   subscription info, and it wastes the focus area on Recent Activity); the Missions page and
   mission cards use tiny 10–13px text and read as unclear; the sidebar needs a refresh; and the
   Ally chat **history can't be renamed and is hard to search** (a flat, ungrouped, unsearchable
   truncate list — even though the rename API already exists end-to-end).

The intended outcome: a **clean, premium SaaS UI** — constrained, consistent, calm (per the
brand: indigo→violet, whitespace, soft radius, *not* hacker-terminal) — that lifts every page,
then deeply redesigns the Dashboard, Sidebar, Missions, and Ally chat/history.

**Locked decisions (from the user):** (1) **Foundation-first** sequencing; (2) adopt **Inter**
as the webfont; (3) subscription = **a summary card on the Dashboard + a "Manage billing" link
out to WHMCS** (real invoices/payment live in WHMCS, never faked in-app).

**Build model:** author with **Fable 5** (`claude-fable-5` — Anthropic's most capable model,
right for a large, judgment-heavy design pass). Run each phase as its own Fable-5 pass, verifying
in the browser between phases. Do **not** big-bang all phases in one shot.

---

## Design direction (the north star for every phase)

Pulled from `marketing-brief/03-brand.md` and the live token system — reuse, don't reinvent:

- **Palette:** brand gradient **indigo `#6366F1` → violet `#8B5CF6` → purple `#A855F7`**; primary
  `#5048E5` (`243 75% 59%`). Neutrals = slate. Success green `#22C55E`, danger `#EF4444`,
  warning amber. Keep the existing light+dark HSL tokens in `frontend/src/index.css` — extend,
  don't replace.
- **Type:** **Inter**, self-hosted (no CDN — the app has no font today). A real type scale
  (display / h1 / h2 / body / small / caption) replaces the current ad-hoc `text-xs`/`text-sm`.
- **Shape & feel:** soft radius (~0.5–0.75rem, squircle brand mark), generous whitespace, subtle
  borders and shadows, calm. Premium = restraint + consistency, not decoration.
- **Motion:** subtle only; keep the existing `prefers-reduced-motion` handling in `index.css`.
- **Both themes:** every new component must work in light AND dark (tokens already cover both).

---

## Phase 1 — Foundation (design system). Highest leverage; do this first.

Goal: fix "too wide" and "no consistency" globally, so all 23 pages improve before any page is
touched individually.

1. **Global page container.** Add a single max-width, centered content wrapper so pages stop
   sprawling. In `frontend/src/components/layout/Layout.tsx`, wrap the `<Outlet/>` in a container
   (e.g. `mx-auto w-full max-w-[1400px]`) — one change, every page benefits. The Ally floating
   window overlays independently and is unaffected. Audit the ~5 pages that already set their own
   `max-w-*` (Dev, ScriptGenerator, PlaybookDetail, Installed, ReportView) so they don't
   double-constrain.

2. **Typography.** Self-host **Inter** (woff2 in `frontend/public/fonts/` + `@font-face` in
   `index.css`, or a local `@fontsource` install), set it as `fontFamily.sans` in
   `tailwind.config.js`, and define a consistent type scale.

3. **Primitive component layer** — new `frontend/src/components/ui/`. Build the small set the
   codebase already re-implements by hand, styled once, theme-aware: `Card`
   (+`CardHeader`/`CardTitle`/`CardContent`), `Button` (variants: primary/secondary/ghost/outline/
   danger + the brand-gradient variant used on Ally/Start-mission), `Badge`/`StatusPill`, `Input`,
   `SectionHeader`, `EmptyState`. Match the existing look so adoption is low-risk; these become
   the vocabulary Phases 2–6 build with.

4. **Tokenize brand + status colors.** The `from-indigo-500 to-violet-500` gradient and the
   green/amber/red status colors are hardcoded across many files. Add a `--brand-gradient` and
   status tokens (or a tiny `lib/statusColors.ts`) so they're defined once. Reuse the existing
   `lib/assetCategories.tsx` and `lib/grade` helpers rather than duplicating.

**Files:** `Layout.tsx`, `index.css`, `tailwind.config.js`, new `components/ui/*`, `public/fonts/*`.
**Verify:** every existing page now sits in a centered, capped column; nothing regresses in light
or dark; `npm run build` clean.

---

## Phase 2 — Sidebar redesign

Redesign `frontend/src/components/layout/Sidebar.tsx` (keep it `w-60`, static on `lg+`, drawer
below — that structure is fine). Improvements:

- Tighter visual hierarchy for the nav groups (primary nav, the "Automate" group, account/admin),
  clearer active state, refined spacing and section labels.
- Keep the pinned bottom block: the **Ask Ally** gradient hero (the floating window grows out of
  it — preserve that behavior and the live mission dot) and the **plan card**. Restyle the plan
  card with the new primitives; it already reads `getMyUsage` (plan, servers used/limit, actions
  used/limit, Upgrade CTA via `UpgradeModal`) — reuse that, don't refetch.
- Optional: a light/dark **theme toggle** (backlog item; tokens already support both).

**Verify:** nav, active states, Ask-Ally launch + mission dot, Upgrade modal all still work.

---

## Phase 3 — Dashboard redesign (the centerpiece)

Rebuild `frontend/src/routes/Dashboard.tsx` as a premium SaaS overview. Reuse the existing data
hooks (`listServers`, `getFleetHealth`, `listPlaybooks`, and **add `getMyUsage`**).

- **Remove Recent Activity from the focus area.** Per the user, not important enough for the
  dashboard. `RecentActivity` already exists in full on the Logs page — drop it from the dashboard
  bento (or demote to a small link). `components/dashboard/RecentActivity.tsx` stays for `/logs`.
- **Add a Subscription summary card** (net-new, fed by the existing `getMyUsage()` →
  `plan`, `used`/`limit`, `servers_used`/`servers_limit`, `resets_at`): plan name/badge, two usage
  meters (actions this month, servers), renewal/reset date, and an **Upgrade / Manage billing**
  button that opens `UpgradeModal` (which already links to `VITE_UPGRADE_URL` = the WHMCS order
  page). Do **not** add revenue/invoices/orders — those are WHMCS/admin-only by design (exactly
  why `BillingPreview` was deleted; see CLAUDE.md 2026-07-16).
- **Rebuild the layout as a clean bento** with the new primitives: a KPI strip (Servers, Health
  score, Alerts, Playbooks — the existing `StatCard`s, restyled), the **`FleetHealthPanel`**
  Recharts donut + top findings (the genuine centerpiece — keep and polish), `FleetComposition`,
  `QuickActions`, `RunningTasks` (self-hiding), and the new Subscription card. Give the customer,
  at a glance: fleet health, what needs attention, and their plan/usage.
- Keep the empty-state and loading branches; restyle with `EmptyState`.

**Files:** `routes/Dashboard.tsx`, `components/dashboard/*` (restyle), new `SubscriptionCard`.
**Verify LIVE:** with servers present — donut, KPIs, subscription meters (correct plan + numbers
from `/api/usage/me`), Upgrade button opens the modal; empty-state for a fresh account; dark mode.

---

## Phase 4 — Missions page + bigger mission-card text

Two parts; both are mostly typography + hierarchy — structure is already sound (master-detail).

1. **Enlarge mission text.** The complaint is real: mission text is dominated by `text-xs`(12px),
   `text-[10px]`, `text-[11px]`, `text-[13px]`. Raise the scale (body → ~14px, headings larger,
   keep code/badges legible) in the three files that render missions:
   `frontend/src/components/chat/MissionCard.tsx` (the offer card),
   `frontend/src/components/chat/MissionProgress.tsx` (live/finished card, steps, result card),
   and `frontend/src/components/missions/MissionStepList.tsx` (the detail-page transcript).
   These three are near-duplicate step patterns — consider a shared `StepRow` primitive.
2. **Clarify the Missions page** `frontend/src/routes/Missions.tsx`: keep the master-detail grid
   but restyle rows/detail with the new primitives, stronger status/verdict chips (reuse
   `statusChip` + the `Found`/`Ally did`/`Left for you` result blocks), larger readable text, and
   better separation between the RecipeLibrary "front door" and the list/detail so they stop
   competing. Inside the Phase-1 max-width container it already feels tighter.

**Verify LIVE:** open a real mission — steps, result card, and detail are comfortably readable;
status/verdict chips clear; recipes → list → detail read as three distinct zones.

---

## Phase 5 — Ally chat history: rename + searchable + grouped (pro design)

All in `frontend/src/components/layout/AssistantDrawer.tsx` (the history rail, ~lines 236–276).
**The rename backend already exists** — `PATCH /api/assistant/threads/{id}` and
`renameThread(id, title)` in `frontend/src/api/assistant.ts` — it's just never called. So this is
UI-only:

- **Inline rename:** a rename affordance on each thread row (double-click title or a hover
  "pencil") → editable field → `renameThread()` → invalidate `["assistant-threads"]` (the
  established react-query pattern). Add a small `updateThreadTitle` helper if useful.
- **Search:** a filter box above the list (client-side filter on title) so a conversation is easy
  to find — today the list is unsearchable.
- **Grouping + better rows:** group threads by recency (Today / Yesterday / This week / Older
  from `updated_at`), show a relative timestamp and message count per row, keep delete but make it
  less accidental (confirm or menu). Titles still auto-set from the first message; rename lets the
  user fix them.
- Restyle the rail and the "New chat" button with the new primitives; widen/clean the rail so
  titles aren't just truncated.

**Verify LIVE:** create 2–3 threads → rename one inline (persists on reload) → search filters the
list → threads grouped by date → delete works.

---

## Phase 6 — Propagate primitives to the remaining pages (cleanup pass)

With the foundation + named pages done, sweep the other pages (Servers, Reports, Playbooks,
Scripts, Team, Settings, Security, Backups, Logs, FileManager, Hosting, Installed, ServerDetail)
to adopt the new `components/ui/*` primitives and the type scale, replacing ad-hoc card/button/
input Tailwind. Mostly mechanical; big consistency payoff. Page-group by page-group, verifying
build + a spot-check per group. Lower priority than 1–5; can be incremental.

---

## Key facts the build needs (from codebase exploration — don't re-derive)

- **No shadcn/ui exists** — the `components/ui/` layer is net-new. Cards/buttons are raw Tailwind
  today, the de-facto card being `rounded-xl border border-border bg-card p-4`.
- **The width fix is one place:** `Layout.tsx`'s `<main>` wraps `<Outlet/>` with no max-width.
- **Design tokens** (`frontend/src/index.css`): full light + dark HSL set — `--background`,
  `--foreground`, `--card`, `--border`, `--primary`, `--muted`, `--accent`, `--destructive`,
  `--ring`, `--radius (0.5rem)`. `darkMode: ["class"]` in `tailwind.config.js`. No custom fonts.
- **Subscription data is ready:** `GET /api/usage/me` → `{ plan, used, limit, resets_at, enforced,
  servers_used, servers_limit }`, client `frontend/src/api/usage.ts` `getMyUsage()`. Free = 30
  actions / 2 servers; Pro = 1000 actions / 15 servers. Upgrade CTA exists (`UpgradeModal.tsx`,
  reads `VITE_UPGRADE_URL`). Revenue/orders/invoices are intentionally NOT customer-facing.
- **Thread rename is already end-to-end** except the UI: backend `PATCH /api/assistant/threads/
  {id}` (`app/routers/assistant.py`) + `renameThread()` (`frontend/src/api/assistant.ts`). Thread
  model: `{ id, title, updated_at, message_count }`. Auto-titled from the first 60 chars of the
  first user message.
- **Ally floating window** (`AssistantDrawer.tsx`) overlays the content area only (not the
  sidebar/topbar), grows out of the Ask-Ally button, and must survive navigation — don't break it.

---

## How to run this with Fable 5

- Switch the model to **Fable 5** (`claude-fable-5`) for the build sessions.
- **One phase per pass**, in order (1 → 6). Phase 1 is the prerequisite for all others.
- After each phase: `npm run build` clean, then drive the real app in the browser (dev servers
  on backend :8888 / frontend :5190) and verify the phase's checklist in **both light and dark**.
  Fix before moving on.
- Local dev nuance: if the app shows a "network error", `curl http://127.0.0.1:8888/health`
  first — the backend sometimes drops and the frontend keeps serving, so it looks up when it
  isn't. Restart the backend, don't chase a phantom frontend bug.
- Keep all changes token-driven and theme-aware; never hardcode a color the token system can
  express. Do NOT change backend behavior — this is a frontend visual redesign only.

## Kickoff prompt (paste into a Fable 5 session)

```
You are the design lead rebuilding the ServerAlly web app UI into a clean, premium SaaS
product. The approved plan is docs/UI-REDESIGN-PLAN.md — read it fully first, plus
marketing-brief/03-brand.md for the brand. It is your source of truth.

Repo: /Users/shafin/Documents/ServerMind, frontend in frontend/ (React 19 + Vite + TS +
Tailwind, TanStack Query, Zustand, React Router). No shadcn/ui exists yet.

Do PHASE 1 ONLY now (the Foundation phase in the plan), then STOP for my review before
Phase 2. One phase per pass — never build all phases at once.

After Phase 1: `npm run build` must be clean and `npm run test` (vitest) green; then verify
in the browser (backend :8888 / frontend :5190). If you see a "network error", curl
http://127.0.0.1:8888/health first — the backend drops sometimes.

Hard rules: keep + extend the existing light/dark HSL tokens in index.css (don't replace);
every component works in BOTH themes; token-driven colors only; self-host Inter (no CDN);
don't break the Ally floating window; don't change backend behavior; don't commit unless I
ask. Brand: indigo→violet→purple, primary #5048E5, slate neutrals, calm/premium, soft
radius, lots of whitespace — NOT terminal-dark.
```

## Verification (end-to-end, all phases)

- **Build:** `npm run build` clean after every phase; `npm run test` (vitest) green.
- **Global (Phase 1):** every page centered and width-capped; no edge-to-edge sprawl on a wide
  monitor; Inter loading; light + dark both correct.
- **Live browser (real account, servers present):**
  - Dashboard: fleet donut + KPIs + subscription card with correct plan/usage from
    `/api/usage/me` + working Upgrade/Manage-billing; Recent Activity no longer in the focus area.
  - Sidebar: nav + active states + Ask-Ally launch + mission dot + Upgrade modal.
  - Missions: readable (no tiny 10–12px text), clear status/verdict, distinct recipe/list/detail
    zones.
  - Ally history: inline rename persists across reload, search filters, date-grouped rows.
  - Zero console errors on a clean reload; the Ally floating window still overlays content (not
    chrome) and survives navigation.

# Assets UI — build plan

Goal: the Assets page becomes a grouped **list**, and opening an asset gives it a
**dedicated side menu whose items depend on what that asset actually is**. Sites gets the
same treatment afterwards, as a separate piece of work.

Written 2026-07-29 after benchmarking Ploi's two-level navigation
(see [PLOI-NAV-CAPTURE.md](PLOI-NAV-CAPTURE.md)).

---

## The one design decision everything rests on

**The menu is built from what the asset can DO, not from a list per asset type.**

A per-type list looks simpler until reality arrives: a VPS with CyberPanel on it is both a
VPS *and* a panel; a DigitalOcean droplet added over SSH is both a VPS *and* a cloud
instance; a Windows box may or may not have Remote Desktop. Hardcoding one list per type
means those mixed cases each need their own list, and the lists drift apart.

So each asset resolves to a set of **capabilities**, and each menu item declares the one it
needs:

| Capability | True when | Gives |
|---|---|---|
| `shell` | connection is ssh or winrm | run commands at all |
| `sftp` | connection is ssh | Files |
| `desktop` | connection is rdp, or winrm with RDP reachable | Open desktop |
| `panel` | `panel_type` is set, or connection is hosting | Websites, panel databases, email |
| `cloud` | `cloud_account_id` is set | power, resize, destroy |
| `unix` | ssh | UFW firewall, SSH keys, systemd services |
| `windows` | winrm | Windows-specific equivalents |

`menuFor(asset)` returns the items whose capability is present. One function, one place to
change, and the mixed cases fall out correctly with no extra code.

**An item that can never apply to this asset is absent, not greyed out.** A permanently dead
row is noise on every single visit. (Ploi greys out what the *plan* withholds — that is a
different thing, and a lock icon is right for that.)

---

## What each asset type ends up with

Resolved by the rules above, not written by hand:

**Bare metal / VPS** — Overview · Sites · Files · Scheduled tasks · Services · Deployments ·
Security · Access (firewall + SSH keys) · Backups · Monitoring · Logs · Installed · Settings
*(plus Hosting if a panel is detected, plus Cloud if it came from a cloud account)*

**Hosting panel** — Overview · Websites · Databases · Email · SSL · Logs · Settings
*(plus Files when we also have SSH to it)*

**Windows (WinRM)** — Overview · Files · Services · Security · Backups · Monitoring · Logs ·
Settings · Open desktop

**Windows (RDP)** — Overview · Settings · Open desktop. Nothing else: there is no command
channel, so every other item would be a lie.

**Cloud account** — its own page, because a cloud account is not a server. Instances ·
Import · Billing/region info · Settings.

---

## Verified inventory — checked against the code on 2026-07-29

Not from memory. Every row below was confirmed by reading the routers and services.

**Ready (page + API exist):** Firewall · SSH keys · Logs · Files · Security (audit +
threats) · Backups · Installed · Hosting · Settings *(today an actions menu, moves into the
sidebar)*

**Data exists, screen does not** — no backend work, only a page to assemble:

| Item | What already backs it |
|---|---|
| Sites | `GET /api/servers/:id/sites` + scan |
| Monitor | `/metrics/history` + `/alerts` + the three chart components |
| Services | `/service-monitors` + `ServicesPanel` |
| Insights | `fleet_service` already scores each server and ranks its findings; only the fleet-wide endpoint is exposed |
| Deployments | `/deploy/targets` |

**Missing entirely — nothing exists yet. TO BUILD LATER:**

| Item | Reality today | Size | Why it matters |
|---|---|---|---|
| **Cronjobs** (the server's own crontab) | Nothing touches the server's crontab. Our Scheduler runs *our* jobs on *our* clock — a different feature wearing a similar name | Small | Cheapest of the four, and it removes a label that currently misleads. **Do this one first.** |
| **Databases** | Nothing outside a control panel. Backups shell out to `mysqldump`, but there is no way to see, create or drop a database | Medium | Every website has one; today the owner cannot see it |
| **PHP versions** | Nothing. No version list, no default switch, no per-site switch | Medium | "My site needs PHP 8.1" is a real support ticket for exactly the non-technical owner we target |
| **Daemons** (Supervisor programs) | Nothing. We now *install* Supervisor but cannot manage programs in it | Medium | Laravel queues — matters more to the agency segment than the small owner, so it goes last |

**Why the shell is built before these four:** the menu is capability-driven, so a feature we
do not have is simply an absent item. Adding Databases later is one entry in the registry —
nothing gets reworked. Building the navigation first also means the sidebar gets used, and
judged, with nine working items before four more are poured into it.

**What we have that Ploi does not** — and should stay visible, because it is why someone
picks us: File Manager (Ploi charges for it) · Security audit · Threat scan · Installed
inventory · Ally and missions · Mission reports · Uptime and certificate monitoring · Mail
health · the setup wizard · Terminal · RDP desktop.

---

## Phase 1 — The Assets list

Replace the card grid in `routes/Servers.tsx`.

- Grouped by category, exactly as today (the grouping already exists — only the row
  rendering changes).
- Remove `AssetsRail` (the right sidebar). Its three numbers move into a thin strip under
  the page title, so nothing is lost.
- One row component with per-type variants:
  - status dot · name · host · OS · panel · site count · CPU/RAM/disk · health grade · chevron
  - an RDP row shows **Open desktop** instead of metrics it cannot collect
  - a hosting row shows the panel and its site count instead of CPU
  - an offline row shows *last seen*, not stale numbers
- Keep search and the type filter.
- Delete `MachineCard` and `HostingCard` once nothing else imports them (checked: only this
  page does).

**Verify:** every category renders; an RDP asset shows no fake metrics; light and dark; no
console errors; `npm run build` and vitest clean.

## Phase 2 — The asset shell and its menu

- `lib/assetMenu.ts` — capabilities + the item registry + `menuFor()`. Pure, so it gets
  unit tests: an RDP asset yields exactly 3 items; a CyberPanel VPS yields shell items *and*
  panel items; a hosting-only account yields no firewall item.
- `components/server/AssetSidebar.tsx` — the secondary menu as its own card: back link,
  asset identity, the items, a small fact footer (OS · category · last seen). Indented from
  the app sidebar with a clear gap, so it reads as part of the page, not part of the app.
- Rework `routes/ServerDetail.tsx`: the horizontal tab strip becomes this sidebar; the
  `<Outlet />` moves to its right. Header becomes a breadcrumb (`Assets / testserver`).
  The existing outlet context (`{ server, openAI }`) is unchanged, so **no child page needs
  editing**.

**Verify:** every existing child route still loads; deep links still work; the menu differs
correctly across the five asset types on the real account.

## Phase 3 — Fill the menu from what we already have

Each of these already has a working API and, in most cases, a component. This phase is
wiring, not new capability.

| Menu item | What backs it | Work |
|---|---|---|
| Sites | `GET /api/servers/:id/sites` + scan | new small page, list + scan button |
| Monitoring | `/metrics/history` + `/alerts` + the 3 chart components | assemble into a page |
| Services | `/service-monitors` + `ServicesPanel` | wrap as a page |
| Deployments | `/deploy/targets` + `Deployments.tsx` | per-server view |
| Set up this server | `/setup` + `ServerSetupPanel` | show as an item while the box is bare |
| Cloud | `CloudLifecyclePanel` | show when the asset came from a cloud account |
| Installed, Files, Security, Access, Backups, Logs, Hosting | already pages | move into the menu only |

## Phase 4 — Cloud account detail page

Cloud accounts are listed on Assets but have no detail page. Give them the same shell:
Instances (with import) · Settings. Reuses `ConnectCloudModal` and `CloudLifecyclePanel`.

## Phase 5 — The four real gaps

These need backend work and are deliberately last, so the navigation ships before them.

1. **Databases** — list/create/drop MySQL or Postgres on a plain SSH server. Today this only
   exists through a panel.
2. **PHP versions** — see installed versions, switch the default, switch per site.
3. **Daemons** — manage Supervisor programs (we now install Supervisor, so the foundation
   is there).
4. **Cronjobs — the server's own crontab.** Worth stating clearly: our current **Scheduler**
   runs *our* jobs on *our* schedule; it does not read or write the server's crontab. Ploi's
   Cronjobs does. They are different features with a confusingly similar name, so the menu
   item stays **"Scheduled tasks"** until the real crontab editor exists.

## Phase 6 — Sites

Same shell, same capability approach, after Assets is done and used.

---

## Risks worth naming up front

- `ServerDetail` is the parent of eight nested routes. The shell change touches all of them
  at once — but only their container, not their code, because the outlet context stays the
  same. Verify each one loads rather than assuming.
- Removing the right rail removes a place things were quietly displayed. Its numbers move to
  the header strip; check nothing else was only reachable from there.
- "Cronjobs" must not be used as a label until it edits a real crontab, or we teach customers
  something false about what we do.

## How each phase is verified

`npm run build` + vitest, then the real account in the browser, in both themes, with zero
console errors — and for Phase 2, one pass through every asset type we actually own
(VPS, CyberPanel VPS, Windows, RDP, hosting, cloud-imported).

# Assets & Categories — the premium plan (design + roadmap, 2026-07-05)

> **Supersedes and expands [SERVER-CATEGORIES.md](SERVER-CATEGORIES.md).** That doc scoped
> the rename + a 4-way category picker; this one is the full design for a **category-first
> "Assets" model with a proper, tailored UI per category**, plus the two real sub-products
> that surfaced (cloud-account import, RDP viewer). Implemented gradually.
>
> **Status: Phase A shipped (2026-07-05).** Servers→Assets (user-facing; DB stays
> `servers`), the `category` column (migration 026 + backfill), the Category Registry
> (`frontend/src/lib/assetCategories.tsx`), the category-first Add-Asset flow (tiles that
> cascade the right transport), category icons/badges on asset cards, an Edit re-file
> control, and i18n across all 4 locales. Cloud shows as a dimmed "Soon" tile.
> Live-verified: nav/cards/tiles + the SSH/WinRM/Hosting cascades.
>
> **Status: Phase B shipped (2026-07-06).** The 4th hosting adapter — **DirectAdmin**
> (`DirectAdminAdapter` in `hosting_service.py`: legacy `CMD_API_*`, HTTP Basic auth,
> URL-encoded `parse_qs` responses; connect + list sites, list/create DB, list/create
> email) + the Add-Asset panel picker (CyberPanel/cPanel/Plesk/**DirectAdmin**, port 2222).
> Mock-tested (11 cases) against the documented DA API — like cPanel/Plesk it needs one
> live pass per panel version (CyberPanel remains the live-proven one).
>
> **Status: Phase C shipped (2026-07-06).** The **Cloud Account** category — connect a
> whole provider account by API key, discover its instances, import the chosen ones as
> assets. **AWS first** (`cloud_service.py`: `_CloudAdapter` base + `AWSAdapter`, boto3
> lazy-imported; STS verify + EC2 `describe_instances` across the configured region or all
> enabled regions; friendly error mapping; one-bad-region resilience). Backend: migration
> 027 (`cloud_accounts` table + `servers.cloud_account_id`/`cloud_instance_id`),
> `/api/cloud-accounts` (connect→verify-before-save, list, delete=SET-NULL keeps assets,
> `{id}/instances`, `{id}/import`); credential is an AES-256-GCM provider-shaped JSON blob;
> the provider API only LISTS machines so import prefills asset rows and the user supplies
> one SSH key/password for the batch (dedupe + plan server-cap aware). Frontend: the Cloud
> tile now opens a `ConnectCloudModal` (connect → discover multi-select → batch SSH cred →
> import), imported assets carry a provider badge. Mock-tested (12 cases, no live AWS);
> **live-verified the connect + error path end-to-end** (real STS rejection surfaced as a
> friendly message, no account created) — the discover/import happy path needs one pass on
> a real AWS account (same caveat as the hosting adapters).
>
> **Status: Phase D (part 1) shipped (2026-07-06).** Two more clouds — **DigitalOcean** +
> **Hetzner Cloud** — via a shared `_TokenAdapter` (bearer-token REST, one global endpoint,
> no region dance): DO verifies on `/v2/account` + lists `/v2/droplets` (paginated); Hetzner
> verifies + lists `/v1/servers` (paginated); friendly 401→"rejected this API token" +
> network-error mapping. The `ConnectCloudModal` is now **provider-driven** (a declarative
> `PROVIDERS` config → provider picker + per-provider credential fields + hint + default SSH
> user), so adding a cloud is one backend adapter + one config entry. **Live-verified** the
> provider picker (AWS/DO/Hetzner render), DO's single-token form, and the DO reject path
> end-to-end (real `/v2/account` 401 → friendly message, no account created). 6 new mock
> tests (18 cloud total). GCP + Azure are Phase D part 2.
>
> **Status: Phase E foundation shipped (2026-07-06).** Remote Desktop as a Windows-asset
> capability. **Security core (fully wired + tested):** `rdp_enabled` opt-in per asset
> (migration 028, default off); `rdp_service` guards (Windows-only + enabled) + a short-lived,
> **credential-free** signed session token (RDP creds never reach the browser); endpoints
> `POST /rdp/enable` (needs manage) + `POST /rdp/session` (needs execute — so a **viewer role
> can never open a live desktop**, via the shared `resolve_server` gate). Frontend: an "Open
> Desktop" button on Windows assets + `RdpDesktopModal` (enable → issue session → an honest
> "streaming service not configured yet" state, or the connecting canvas once guacd is set).
> `RDP_GUACD_URL` empty = streaming not deployed. Verified: 6 rdp-service tests (guards +
> scoped token), route live + auth-gated, and the button correctly **hidden on non-Windows
> assets** (live). **Phase E part 2 (needs a live Windows/RDP host — same limit as WinRM,
> which was always mock-only):** the Apache Guacamole (`guacd`) Docker service +
> guacamole-common-js viewer that streams real pixels.

## The idea in one line

Today a user adds a **Server** and the very first question is a *protocol* ("SSH / WinRM /
Hosting Panel"). Non-technical users don't think in protocols — they think **"this is my
AWS box," "my cPanel hosting," "my Windows PC."** So the collection noun becomes **Assets**,
and adding one is **category-first**: pick *what it is*, get a form tailored to that thing,
and the right protocol/credentials are chosen for you underneath.

## Locked decisions

| Decision | Choice | Why |
|---|---|---|
| Umbrella noun | **Servers → Assets** (user-facing only) | Distinctive vs RunCloud/Ploi; pairs with "Fleet"; translates cleanly in all 8 launch languages. DB/tables/routes stay `servers` (see "How the rename goes"). |
| Add flow | **Category-first** (tiles, not a protocol dropdown) | The whole point — "what is this?" before "how does it connect?". |
| Categories | **Bare Metal · VPS · Hosting Panel/Platform · Windows Server · Cloud Account · (Remote Desktop)** | The user's list. Bare Metal + VPS are separate *tiles* over the same SSH transport (a value metric users think in), not two engines. |
| RDP | **Add-on to Windows**, not a standalone category | A Windows asset stays AI-automated over WinRM; RDP adds an optional "open desktop" viewer on the *same* asset, reusing its credentials. |
| Plan gating | **None** — every category on every plan | Keeps the locked "open features, two meters" pricing (plans differ only by the server/action meters). Cloud + RDP are NOT paywalled. |
| Cloud providers | **AWS first**, then DigitalOcean · Hetzner · GCP · Azure | AWS was named; the rest ship one adapter at a time, simplest-and-most-target-fit first. |
| Hosting scope | **Real panels first** (cPanel/CyberPanel/Plesk/DirectAdmin) | PaaS (Vercel/Netlify/Railway) is a *different* integration — noted as a later category, not v1. |

## How the rename goes (3 layers, 3 risk levels)

1. **User-facing copy — rename.** Nav label, "Add Asset" button/modal, page titles, empty
   states, tooltips, all 8 i18n locale files. Pure strings, zero functional risk.
2. **Frontend code — rename, cheap/optional.** `AddServerModal`→`AddAssetModal`,
   `ServerCard`→`AssetCard`, `routes/Servers`→`Assets`, the `Server` TS interface →
   `Asset`. IDE-assisted, no external contract; bundle it for internal consistency but
   safe to defer.
3. **Backend DB + API — do NOT rename.** The `servers` table, every `server_id` FK
   (command_logs, playbook_runs, scheduled_tasks, server_metrics, alerts, server_access,
   security_scans, backups, threat_scans, missions), and `/api/servers/*` stay exactly as
   they are. "Asset" is a presentation word on the same `Server` model — same as
   `connection_type`/`panel_type` already sit on it. Renaming the table = a huge, risky
   migration for a branding change. **Not worth it.**

---

## The architectural spine: a **Category Registry**

The premium move that makes "a proper UI per category" *scalable* instead of a pile of
`if (category === …)` branches: **one declarative registry** that every surface reads.

A category descriptor (frontend `categories.ts`, mirrored by a backend enum) declares:

```ts
interface AssetCategory {
  id: "bare_metal" | "vps" | "hosting" | "windows" | "cloud"
  label: string                    // "Bare Metal Server"
  icon: LucideIcon                 // the tile + card + detail icon
  blurb: string                    // one-liner on the Add tile
  transport: "ssh" | "winrm" | "hosting" | "cloud"   // → connection_type default
  addForm: React.FC                // the category-specific Add form (the "proper UI")
  connectionDefaults: Partial<ServerCreateBody>       // port/auth cascade (already exists)
  capabilities: Capability[]       // what the detail page shows: chat, terminal, files,
                                   //   playbooks, security, backups, monitoring, hosting,
                                   //   rdp, cloud-link
  badge?: (asset) => Badge         // e.g. panel type, cloud provider, "RDP"
}
```

- **Add-Asset modal** renders category **tiles** from the registry; picking one mounts that
  category's `addForm` and applies its `connectionDefaults` (the modal's existing
  `setConnectionType`/`setPanelType` cascade — reused, just triggered by a tile).
- **AssetCard / AssetDetail** read `icon`, `badge`, and `capabilities` from the registry —
  so a category shows the right icon and only the tabs/actions that make sense for it.
- **Adding a category later** = add a descriptor (+ its form component, + an adapter for
  cloud/rdp). No rewrite. This is the extensibility the "gradual" ask needs.

Backend counterpart: a nullable **`category`** column on `servers` (one Alembic migration,
purely descriptive — does NOT touch `connection_manager`/`ssh_service`/`winrm_service`/
`hosting_service`, no execution-path change). Existing rows backfill from
`connection_type`/`panel_type` (ssh→`vps` by default, winrm→`windows`, hosting→`hosting`).

---

## Per-category "proper UI"

Each category = a tile → a tailored Add form → an AssetCard badge → a capability-scoped
detail page. Reuse is heavy; only cloud + RDP need genuinely new backend.

### 1 · Bare Metal Server  &  2 · VPS  (transport: SSH — already fully built)
- **What:** a Linux/Unix box you have SSH to. Bare Metal vs VPS is the *user's* mental
  model (owned hardware vs rented instance) — same engine, distinct tiles/icons.
- **Add form:** host, port (22), username, key-or-password. VPS adds an optional
  **provider** tag (DigitalOcean/Hetzner/…); Bare Metal adds an optional **location/label**
  note. Both cascade `connection_type=ssh` from the registry.
- **Detail:** the full existing surface — chat, terminal, files, playbooks, security,
  backups, monitoring (+ the Hosting tab if a panel is detected on it).
- **New work:** essentially none beyond the tile + the `category` value. This is the proof
  the registry pattern works on what already exists.

### 3 · Hosting Panel / Platform  (transport: hosting or ssh+panel — mostly built)
- **What:** a panel account — CyberPanel, cPanel/WHM, Plesk, DirectAdmin.
- **Add form:** panel type picker → panel URL + API user/token (or SSH creds for the
  CyberPanel-CLI-over-SSH path already shipped). Ports auto-fill per panel (2083/8090/8443/
  2222). This is largely today's `AddServerModal` hosting branch, re-skinned as a tile.
- **Detail:** the Hosting tab (websites / databases / email / SSL) + hosting-aware chat.
- **New work:** DirectAdmin adapter (Phase-7 shipped only cyberpanel/cpanel/plesk);
  "platform"/PaaS (Vercel/Railway) explicitly deferred to a future category.

### 4 · Windows Server  (transport: WinRM — built; RDP is the add-on)
- **What:** a Windows Server managed over WinRM, AI-automated like any other asset.
- **Add form:** host, port (5985/5986), admin user + password, NTLM/Kerberos. (Today's
  winrm branch as a tile.)
- **Detail:** chat + playbooks + security + monitoring (no interactive PTY — WinRM streams
  via chat), **plus an "Open Desktop" button** when RDP is enabled (see §RDP building block).
- **New work:** the RDP toggle + viewer (Phase 3).

### 5 · Cloud Account  (transport: cloud → import → SSH/WinRM — NEW, the biggest lift)
- **What:** connect a whole cloud *account* by API key, **discover** its instances, and
  **import** the ones you pick as real assets. This is an *account* entity, not a server
  field.
- **Add flow (2 levels):** tile → provider picker (AWS/DO/Hetzner/GCP/Azure) → paste a
  **least-privilege, read-only** API key → we verify + **list instances** → you multi-select
  → each becomes a normal `servers` row (host/name/OS prefilled, `connection_type` inferred
  from detected OS, `category='cloud'`, linked to the account, provider badge).
- **Honest constraint (must show in UI):** the cloud API gives instance existence + IP +
  OS, **not a working login**. Import = "discover + prefill," then the user confirms a
  key/password per instance (or one keypair for the whole account). Don't imply zero-touch.
- **Detail:** the imported instance behaves as its OS (SSH/WinRM) + a **cloud badge** and a
  link back to its account; the account itself gets a small page (its instances, re-sync,
  disconnect).
- **New work:** `cloud_accounts` table + `cloud_service.py` (adapter-per-provider, mirroring
  the proven `hosting_service` pattern) + connect/list/import endpoints + the 2-level UI.

### (Windows add-on) · Remote Desktop (RDP)
- **What:** an optional **visual desktop viewer** on a Windows asset — for the moments a
  human wants to *see* the screen (a GUI installer, IIS Manager, a license dialog) that
  isn't practical to script. Not a category; a capability toggle on a Windows asset.
- **UI:** an "Open Desktop" button on the Windows asset → a full-screen viewer
  (canvas/video + keyboard/mouse over websockets).
- **New work:** an **Apache Guacamole** Docker service (translates RDP↔browser; purpose-built,
  matches our near-zero-infra pattern) + a viewer surface + **strict access control** (RDP
  sits OUTSIDE the AI-safety envelope — a human drives the mouse — so *who* may open a live
  desktop is checked against `team_members`/`server_access` before anything renders). Reuses
  the encrypted WinRM/RDP credentials already stored; no new credential type.

---

## The premium roadmap (ship gradually, each phase independently valuable)

| Phase | Ships | Size | Risk | Depends on |
|---|---|---|---|---|
| **A — Assets + Category Registry** | Rename (copy + i18n + optional code-org), `category` column + backfill migration, the Category Registry, the category-first Add-Asset flow, AssetCard/AssetDetail reading the registry. **All existing transports become tiles: Bare Metal, VPS, Hosting, Windows.** | **S–M** | Low (no execution-path change) | — |
| **B — DirectAdmin + Hosting polish** | The 4th hosting adapter; hosting tile refinements. | **S** | Low | A |
| **C — Cloud Accounts (AWS)** | `cloud_accounts` + `cloud_service` + AWS adapter + connect→discover→import flow + cloud badge/detail. | **L** (Phase-7-sized) | Med (new entity + billable-key handling) | A |
| **D — More clouds** | DigitalOcean → Hetzner → GCP → Azure, one adapter at a time (same flow). | **M each** | Low-Med | C |
| **E — RDP viewer** | Guacamole Docker service + "Open Desktop" on Windows assets + access control. | **L** (Phase-2B-sized) | Med (new infra, outside AI-safety envelope) | A |

**Recommended first step: Phase A only.** It's the whole *felt* change (Assets, category
tiles, tailored cards) with **zero new backend capability** — it just reorganizes what
exists behind a category registry. It de-risks everything after it (C/E plug into the same
registry) and fully answers "the Add-Server structure feels wrong for non-servers."

---

## Cross-cutting concerns

- **Security.** Every credential stays AES-256-GCM at rest (same as today). Cloud API keys
  are a step up in blast radius (they can provision/destroy billable infra) → the Add form
  **nudges toward read-only/least-privilege keys** (AWS: describe-instances-only policy; DO:
  read scope) and this becomes its own line in the Security Rules. RDP access is gated by
  team role *before* a desktop renders.
- **The meters don't change.** An Asset is a `servers` row, so cloud-imported instances and
  Windows/RDP assets all count against the same **server meter**; the **action meter** is
  unaffected (browsing/importing isn't an AI action). No new metering.
- **i18n.** The only genuinely multilingual cost is the new category strings ("Assets", each
  category label/blurb) across the 8 locale files — everything else is structural.
- **Backward-compat.** Existing servers get a `category` backfilled from their transport, so
  nothing breaks; a per-asset "change category" control (in Edit) lets users re-file.
- **Testing.** Deterministic: registry completeness (every category has icon/form/
  capabilities), the transport→category backfill, cloud adapters' auth/parse/error paths
  (mock the provider SDKs, like the hosting adapters), RDP access-control gating. Live: one
  real instance import per provider; one real RDP session.

## Deliberately NOT in this plan (future categories/edges)

- **PaaS platforms** (Vercel, Netlify, Railway, Heroku) — a different, API-only integration;
  a future category, not part of "hosting panels."
- **Standalone RDP-only assets** (a desktop with no WinRM automation) — the chosen model is
  RDP-as-Windows-add-on; revisit only if a real need appears.
- **Non-instance cloud resources** (S3, RDS, load balancers, DNS zones) — this plan imports
  *compute instances* as assets; managing other cloud resources is a separate product surface.
- **Renaming the `servers` table / `/api/servers` routes** — see "How the rename goes."

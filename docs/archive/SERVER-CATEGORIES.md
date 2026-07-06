# Add Asset → Categories (planning doc, 2026-07-05)

> Direction for redesigning the Add Server flow into an "Assets" model that's
> category-first instead of protocol-first. Scoped with the user before handing to
> Claude Code — two of the requested categories turned out to be full sub-projects,
> not just labels, and the umbrella noun changed mid-discussion. Not built yet.

## Decisions locked in

| Decision | Reasoning |
|---|---|
| Rename the umbrella noun from **"Servers"** to **"Assets"** (user-facing only — see scope note below) | Reconsidered from the original "keep Servers" recommendation. "Servers" matches RunCloud/Ploi/ServerPilot, but that's exactly the problem — this product already coins distinctive vocabulary (Ally, Missions, Playbooks, Skills), so the generic industry word was the odd one out. "Assets" is distinctive among direct competitors, is an established IT/ops term (not an invented pun, so no comprehension tax), pairs naturally with the already-shipped **Fleet** vocabulary ("fleet of assets" reads fine; "fleet of connections/resources" doesn't), and translates as the standard business word for "asset" in all eight launch languages — safer than an English-only metaphor for a multilingual-first product. |
| "Windows Remote Desktop" = **real RDP** (graphical/interactive), not a friendlier WinRM label | User's explicit call — see Phase 3, this is the biggest of the three phases. |
| "Cloud Platform" = **connecting a whole cloud account** (API keys) to discover/import instances, not a label on a manually-added server | User's explicit call — see Phase 2, this is Phase-7-sized (new entity + adapters), not a UI tweak. |

## How deep the "Assets" rename goes

Three layers, three risk levels — worth keeping separate so this doesn't balloon into a bigger migration than intended:

1. **User-facing copy — rename this.** Nav label, "Add Asset" button/modal title, page titles, empty states, tooltips, all 8 i18n locale files. This is the entire point of the change and is pure string editing, no functional risk.
2. **Frontend code organization — rename, optional/cheap.** Component/file names (`AddServerModal.tsx`→`AddAssetModal.tsx`, `ServerCard.tsx`→`AssetCard.tsx`, `routes/Servers.tsx`→`Assets.tsx`), the `Server` TypeScript interface → `Asset`. IDE-assisted, zero external contract, safe to bundle with the copy rename for internal consistency — but purely cosmetic, so fine to defer if it slows Phase 1 down.
3. **Backend DB schema + API routes — do NOT rename.** The `servers` table, its `server_id` foreign key columns, and `/api/servers/*` routes stay exactly as they are. This isn't just precedent — nearly every feature table built so far has a `server_id` FK pointing at `servers.id`: command_logs, playbook_runs, scheduled_tasks, server_metrics, alerts, server_access, security_scans, backups, threat_scans, missions. Renaming the table means touching all of those FKs plus every ORM relationship and query — a genuinely large, risky migration for a branding change. "Asset" is a presentation-layer word sitting on top of the same `Server` model/table, same as `connection_type`/`panel_type` already do today.

## The actual UX problem

`AddServerModal.tsx` currently asks **"Connection Type: SSH / WinRM / Hosting Panel"**
as the very first field — that's the transport protocol. A non-technical user doesn't
think in protocols; they think "this is my AWS box" / "this is my cPanel hosting" /
"this is my Windows PC." Fix: ask **"what is this?"** first, and let the category drive
the connection_type/panel_type defaults that already exist — `setConnectionType()` in
the modal already cascades port/username/auth per type; it just needs to be triggered
from a category tile instead of a raw dropdown.

## Category taxonomy

| Category | Underlying transport | Notes |
|---|---|---|
| Linux/Unix Server | `connection_type=ssh` | Bare metal vs VPS is a label/tag, not a separate category — no functional difference to ServerAlly. |
| Windows Server | `connection_type=winrm` | AI automation unchanged. Phase 3 *adds* an optional RDP viewer on top — doesn't replace this. |
| Hosting Account | `connection_type=hosting`, `panel_type=...` | cyberpanel / cpanel / plesk. DirectAdmin has no `hosting_service` adapter yet (Phase 7 only shipped those three) — the modal correctly omits it today; add both together if DirectAdmin becomes a priority. |
| Cloud Server | `connection_type=ssh` or `winrm` | An individual instance, however it got added. Phase 2 below is the account-level version of this. |

Note: "Server" survives as a **category label** (Linux/Unix Server, Windows Server)
even though it's no longer the collection noun — that's intentional, not a leftover
inconsistency. Assets → categorized into Server / Hosting Account / Cloud Server.

## Phase 1 — category picker (small, ship first, no dependencies)

- **Backend:** one nullable `category` column on `servers` (Alembic migration). Purely
  descriptive — does not touch `connection_manager.py` / `ssh_service` / `winrm_service`
  / `hosting_service`, no execution-path changes.
- **Frontend:** `AddServerModal.tsx` gets a category-tile first step (icons), reusing
  the existing `setConnectionType`/`setPanelType` cascade logic. Keep a raw "Advanced"
  protocol dropdown for power users and anything not yet categorized. `ServerCard.tsx`
  gets a per-category icon instead of the single generic `ServerIcon` + raw
  `connection_type` badge it renders today. Modal title/button copy becomes "Add Asset",
  nav label "Servers" → "Assets" (see rename-scope note above for what does/doesn't change).
- **i18n:** add the new "Assets"/"Add Asset" strings to all 8 locale files
  (`frontend/src/i18n/locales/*.json`) — the only genuinely multilingual cost of this change.
- **Touchpoints:** `backend/app/models/server.py`, a new `backend/alembic/versions/*`
  migration, `backend/app/schemas/server.py` (Create/Update/Out), `frontend/src/types/index.ts`
  (`Server`, `ServerCreateBody`), `frontend/src/api/servers.ts`, `AddServerModal.tsx`,
  `ServerCard.tsx`, `EditServerModal.tsx` (allow changing category after creation),
  `Sidebar.tsx` nav label, `routes/Servers.tsx` page copy.
- This alone fully answers the original ask and already works for a manually-added
  cloud VM (host/IP typed in, just labeled "Cloud Server"). Ship independent of Phase 2/3.

## Phase 2 — Cloud Platform: connect a whole account (~Phase-7-sized)

A new entity, not a new server field.

- New table `cloud_accounts`: id, user_id, provider (`aws`|`digitalocean`|`azure`|`gcp`|`hetzner`),
  label, `encrypted_credential` (AES-256-GCM, same pattern as `servers.encrypted_cred`), created_at.
- New service `cloud_service.py`, mirroring `hosting_service.py`'s proven adapter
  pattern: an `_Adapter` base + one subclass per provider (`AWSAdapter` via boto3
  `describe_instances`, `DigitalOceanAdapter` via DO API v2 `GET /v2/droplets`, etc.),
  uniform async dispatch, a `CloudError` mapped the same way `HostingError` is today.
- New endpoints: `POST /api/cloud-accounts` (connect + verify), `GET /api/cloud-accounts/{id}/instances`
  (discoverable, not-yet-imported instances), `POST /api/cloud-accounts/{id}/import`
  (turn selected instance(s) into real `servers` rows — host/name/OS prefilled,
  `connection_type` inferred from detected OS).
- Ship **one provider first** (whichever your users actually run), not all four —
  same phasing discipline as the Hosting Mode adapters.
- Real constraint: the cloud API gives you instance existence + IP + OS, **not a
  working SSH login**. Import is "discover + prefill," not zero-touch onboarding —
  the user still confirms a key/password per instance (or per batch, if one keypair
  covers the account). Don't let the UI imply otherwise.
- Credential risk is a step up from one server's SSH password — a cloud API key can
  provision/destroy billable infrastructure and often reaches other account services.
  Worth an explicit UI nudge toward least-privileged/read-only keys (AWS: read-only
  describe-instances policy; DigitalOcean: read-only token scope) — add as its own
  line in Security Rules once built.

## Phase 3 — Windows Remote Desktop: real RDP (~Phase-2B-sized, biggest lift)

Architecturally distinct from everything else ServerAlly does today.

- RDP (port 3389) is graphical/interactive, not a command channel. Ally's entire value
  prop (AI plans → validates → executes → streams text output) is built on shell
  transports (SSH/WinRM). There's no clean way for the AI to read or safely act on a
  screen buffer — so RDP should be **additive**, not a replacement: the server stays
  automated via WinRM (chat/missions/playbooks unchanged); RDP adds an optional visual
  viewer for the moments a human wants to see the desktop (GUI installer, IIS Manager,
  a license dialog — things not practical to script).
- Browsers can't speak RDP natively — this needs a gateway translating RDP into
  something renderable (canvas/video + keyboard/mouse over websockets). Recommend
  **Apache Guacamole** (open source, purpose-built for exactly this, supports RDP/VNC/SSH)
  as a new Docker service, rather than implementing the protocol from scratch — matches
  the project's "near-zero extra infra cost" pattern.
- No new credential type — reuse the encrypted WinRM admin credentials already stored.
- Sits outside the AI-safety envelope by construction (a human drives the mouse, not
  the AI issuing validated commands) — so team/role access control on *who* can open a
  live desktop matters more here than for chat. Check against `server_access`/`team_members`
  before shipping.

## Recommended sequencing

1. **Phase 1** (category picker + naming) — small, ship first.
2. **Phase 2** (Cloud Platform account import) — reuses the hosting_service adapter pattern directly.
3. **Phase 3** (Windows RDP viewer) — biggest lift, most separable from the AI-automation
   core; sequence last unless a specific customer need pulls it forward.

Phase 1 alone fully answers "the Add Server structure feels wrong for non-servers."
Phases 2 and 3 are real products in their own right that surfaced while naming a
dropdown option — worth estimating separately before committing dates for either.

import { Server as ServerIcon, AppWindow, Cloud } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import type { CloudAccount } from "@/api/cloud"
import type { Server } from "@/types"

/**
 * Assets, as three separate questions — see docs/ASSETS-AND-CLOUD-PLAN.md Part A.
 *
 * The old registry answered all three with one list of "categories", which is why the list
 * kept growing: every new answer to any of them became another tile AND another group.
 *
 *   1. **What can I add?**      → `ADD_TILES`. A choice, so it must be short.
 *   2. **Where does it live?**  → `groupFor`. Derived from the row, never stored.
 *   3. **Show me only these.**  → `ASSET_FILTERS`. Slices across groups.
 *
 * Keeping them apart is the whole point. A group answers *where did this come from?*; a
 * filter answers *show me only these*. "Has a control panel" is a property of a machine, not
 * a kind of machine — so it is a filter and a chip, never a group.
 */

// ── 1. What can I add? ───────────────────────────────────────────────────────

export interface AddTile {
  id: string
  label: string
  blurb: string
  icon: LucideIcon
  /** The transport a NEW asset from this tile connects over. Absent for Cloud, which is an
   *  account-import flow (connect → discover → import) rather than a direct add. */
  connectionType?: Server["connection_type"]
  /** true → picking the tile hands over to the Cloud Account flow. */
  cloudFlow?: boolean
  accent: string
}

/**
 * Three tiles, down from six.
 *
 * **Bare Metal and VPS were one thing wearing two hats.** A customer does not care whether
 * the machine is dedicated or virtual — only that it is Linux and they have SSH — and
 * nothing in the product behaved differently between them. Two choices only created doubt at
 * the moment of adding.
 *
 * **The Hosting Panel tile is gone because it was a dead end.** Read off a live CyberPanel on
 * 2026-07-04: its `adminUser/adminPass` API is a cloud-management surface only — no website
 * list or create, no database, no SSL; those are session+CSRF web routes. The reliable
 * surface is the `cyberpanel` CLI over SSH, which is what a Server with a panel already
 * gets. A tile leading anywhere else is a trap. (cPanel and Plesk do have real APIs; if we
 * ever support one WITHOUT SSH, a tile can come back — for that panel only.)
 *
 * **Windows Server and Windows (RDP) became one tile with one question inside it.** They
 * really are different connections with different abilities, so the TYPES stay apart and
 * `capabilitiesOf` keeps treating them differently — it is the CHOICE that merged.
 */
export const ADD_TILES: AddTile[] = [
  {
    id: "server",
    label: "Server",
    blurb: "A Linux machine you have SSH access to. Dedicated or virtual.",
    icon: ServerIcon,
    connectionType: "ssh",
    accent: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400",
  },
  {
    id: "windows",
    label: "Windows Server",
    blurb: "A Windows machine, over Remote Desktop or the command line.",
    icon: AppWindow,
    connectionType: "rdp",
    accent: "bg-sky-500/10 text-sky-600 dark:text-sky-400",
  },
  {
    id: "cloud",
    label: "Cloud Account",
    blurb: "Import instances from AWS, DigitalOcean, Hetzner and more.",
    icon: Cloud,
    cloudFlow: true,
    accent: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
  },
]

/**
 * How a Windows machine is reached. One question inside the Windows tile, the same shape as
 * choosing a password or a key — and the honest reason it is asked at all is that the two
 * genuinely differ in what they can do afterwards: RDP has no command channel, so a box
 * added that way gets *Open desktop* and no shell, no files and no Ally.
 */
export const WINDOWS_METHODS = [
  {
    id: "rdp" as const,
    label: "Remote Desktop",
    blurb: "See and use the screen, the way the Remote Desktop app does.",
    port: 3389,
  },
  {
    id: "winrm" as const,
    label: "Command line",
    blurb: "Let Ally run commands, read logs and manage it for you.",
    port: 5985,
  },
]

// ── 2. Where does it live? ───────────────────────────────────────────────────

export const CLOUD_PREFIX = "cloud:"

/** `server`, `windows`, or `cloud:<account-id>` — one zone per connected account. */
export type AssetGroupId = string

export interface AssetGroup {
  id: AssetGroupId
  label: string
  icon: LucideIcon
  accent: string
}

export const ASSET_GROUPS: AssetGroup[] = [
  { id: "server", label: "Servers", icon: ServerIcon, accent: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400" },
  { id: "windows", label: "Windows servers", icon: AppWindow, accent: "bg-sky-500/10 text-sky-600 dark:text-sky-400" },
]

/**
 * Which group an asset belongs to — **derived on every read, never stored**.
 *
 * This codebase learned that on 2 August with the server role: *"a column would go stale the
 * day somebody installs a panel by hand, and the screen would then insist we run a machine
 * the panel has taken over."* The same is true here, and worse: the stored `servers.category`
 * is written by two different doors that disagree, so a CyberPanel EC2 imported from AWS is
 * filed as a plain VPS while the same machine added by hand is filed as a panel.
 *
 * Deriving it also means a disconnected cloud account cannot orphan anything: the FK is
 * `SET NULL`, so the asset simply re-files itself here.
 *
 * A control panel does not appear in this function at all. It is a chip on the row and a
 * filter — `panel_type` keeps driving the Control-panel section through `capabilitiesOf`,
 * exactly as before.
 *
 * *Phase 3 adds one branch in front of these: an asset with a `cloud_account_id` lives in
 * that provider's zone. Until the zone exists, sending it there would make it vanish.*
 */
export function groupFor(
  s: Pick<Server, "connection_type" | "cloud_account_id">,
): AssetGroupId {
  // An asset that came from a cloud account lives THERE and nowhere else. Nobody thinks
  // "my VPS group"; they think "my AWS" — and for an agency, one zone per client account is
  // already how they hold it in their head.
  if (s.cloud_account_id) return `${CLOUD_PREFIX}${s.cloud_account_id}`
  if (s.connection_type === "winrm" || s.connection_type === "rdp") return "windows"
  return "server"
}

export function groupById(id: AssetGroupId): AssetGroup {
  return ASSET_GROUPS.find((g) => g.id === id) ?? ASSET_GROUPS[0]
}

/** The descriptor behind an asset's ROW ICON.
 *
 *  Deliberately about what the machine is, not where it is filed: a Linux EC2 sitting in the
 *  AWS zone should still look like a server. The zone already says whose it is.
 */
export function groupForServer(s: Pick<Server, "connection_type">): AssetGroup {
  return groupById(
    s.connection_type === "winrm" || s.connection_type === "rdp" ? "windows" : "server")
}

// ── The zones a page actually renders ────────────────────────────────────────

export interface AssetZone extends AssetGroup {
  /** Present when this zone IS a connected cloud account. */
  account?: CloudAccount
  servers: Server[]
}

/**
 * Every zone, in the order they are shown, with its assets.
 *
 * Provider zones come first because a customer who has connected an account came here for it,
 * and this needs no special case to be right for someone who has not: an empty generic group
 * is not rendered, so a fleet with no cloud accounts is unchanged.
 *
 * **A connected account with nothing imported still gets a zone.** Otherwise connecting an
 * account and importing nothing makes the account itself invisible, with no way back to it.
 */
export function assetZones(servers: Server[], accounts: CloudAccount[]): AssetZone[] {
  const known = new Set(accounts.map((a) => a.id))
  const byZone = new Map<string, Server[]>()

  for (const s of servers) {
    let id = groupFor(s)
    // The guard that matters: a server pointing at an account we cannot see would land in a
    // zone that is never drawn — and vanish from the page entirely. Falling back is always
    // recoverable; disappearing is not, and it looks exactly like the asset being deleted.
    if (id.startsWith(CLOUD_PREFIX) && !known.has(id.slice(CLOUD_PREFIX.length))) {
      id = groupFor({ connection_type: s.connection_type, cloud_account_id: null })
    }
    const list = byZone.get(id)
    if (list) list.push(s)
    else byZone.set(id, [s])
  }

  const zones: AssetZone[] = accounts.map((account) => ({
    id: `${CLOUD_PREFIX}${account.id}`,
    label: account.label,
    icon: Cloud,
    accent: "bg-violet-500/10 text-violet-600 dark:text-violet-400",
    account,
    servers: byZone.get(`${CLOUD_PREFIX}${account.id}`) ?? [],
  }))

  for (const group of ASSET_GROUPS) {
    const list = byZone.get(group.id) ?? []
    if (list.length) zones.push({ ...group, servers: list })
  }
  return zones
}

// ── 3. Show me only these. ───────────────────────────────────────────────────

export interface AssetFilter {
  id: string
  label: string
  match: (s: Server) => boolean
}

/**
 * Filters find things **wherever they live**, which is the one thing a group cannot do.
 *
 * An agency with forty CyberPanel servers might want to see them together — but they all sit
 * under Servers anyway, so a "Panels" group would just be "most of my servers", which sorts
 * nothing. As a filter it works across every group at once, including inside a provider zone
 * once Phase 3 adds those.
 *
 * Every one of these is derived from a field we already have. Nothing new is stored.
 */
export const ASSET_FILTERS: AssetFilter[] = [
  {
    id: "panels",
    label: "Panels",
    match: (s) => Boolean(s.panel_type),
  },
  {
    id: "windows",
    label: "Windows",
    match: (s) => groupFor(s) === "windows",
  },
  {
    id: "attention",
    label: "Needs attention",
    match: (s) => s.status === "auth_failed" || s.status === "host_changed" || s.status === "offline",
  },
]

export function filterById(id: string): AssetFilter | undefined {
  return ASSET_FILTERS.find((f) => f.id === id)
}

/**
 * The filters worth offering for THIS fleet, each with what it would show.
 *
 * A filter that would return nothing is **absent, not disabled** — the same rule the asset
 * and site menus already follow. A customer with no Windows server should never be shown a
 * Windows filter; it answers a question they do not have and makes the row longer for
 * everyone who does.
 */
export function availableFilters(servers: Server[]): { filter: AssetFilter; count: number }[] {
  return ASSET_FILTERS
    .map((filter) => ({ filter, count: servers.filter(filter.match).length }))
    .filter((f) => f.count > 0)
}

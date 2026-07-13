import { HardDrive, Server as ServerIcon, LayoutPanelTop, AppWindow, Cloud, Monitor } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import type { Server } from "@/types"

/**
 * The Category Registry — the single declarative source the "Assets" model reads from
 * (see docs/ASSETS-CATEGORIES-PLAN.md). Every surface (the Add-Asset tiles, the AssetCard
 * icon/badge, later the detail-page capabilities) reads a category descriptor here, so
 * adding a category is config + a form, not scattered `if`s.
 *
 * NOTE: `category` is a user-facing GROUPING on the same `servers` row; the transport
 * (`connection_type`/`panel_type`) still does the connecting. Bare Metal and VPS are two
 * tiles over the SAME ssh transport — a distinction users think in, not two engines.
 */
export type AssetCategoryId = "bare_metal" | "vps" | "hosting" | "windows" | "windows_rdp" | "cloud"

export interface AssetCategory {
  id: AssetCategoryId
  label: string
  blurb: string
  icon: LucideIcon
  /** The transport a NEW asset of this category connects over. Undefined for Cloud, which
   *  is a separate account-import flow (connect → discover → import), not a direct add. */
  connectionType?: Server["connection_type"]
  /** false → shown as a dimmed "coming soon" tile, not addable yet. */
  available: boolean
  /** true → picking the tile opens the Cloud Account flow instead of the add-asset form. */
  cloudFlow?: boolean
  /** Tailwind classes for this category's icon tile — gives each group a distinct accent. */
  accent: string
}

export const ASSET_CATEGORIES: AssetCategory[] = [
  { id: "bare_metal", label: "Bare Metal", blurb: "A physical server you have SSH to", icon: HardDrive, connectionType: "ssh", available: true, accent: "bg-slate-500/10 text-slate-600 dark:text-slate-300" },
  { id: "vps", label: "VPS", blurb: "A cloud/rented Linux server over SSH", icon: ServerIcon, connectionType: "ssh", available: true, accent: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400" },
  { id: "hosting", label: "Hosting Panel", blurb: "cPanel, CyberPanel or Plesk", icon: LayoutPanelTop, connectionType: "hosting", available: true, accent: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
  { id: "windows", label: "Windows Server", blurb: "Manage with Ally over WinRM", icon: AppWindow, connectionType: "winrm", available: true, accent: "bg-sky-500/10 text-sky-600 dark:text-sky-400" },
  { id: "windows_rdp", label: "Windows (RDP)", blurb: "Remote Desktop access on port 3389", icon: Monitor, connectionType: "rdp", available: true, accent: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400" },
  { id: "cloud", label: "Cloud Account", blurb: "Import instances from AWS & more", icon: Cloud, available: true, cloudFlow: true, accent: "bg-violet-500/10 text-violet-600 dark:text-violet-400" },
]

export const ADDABLE_CATEGORIES = ASSET_CATEGORIES.filter((c) => c.available)

export function categoryById(id: string | null | undefined): AssetCategory | undefined {
  return ASSET_CATEGORIES.find((c) => c.id === id)
}

/** Infer a category from an existing asset's transport — mirrors the backend
 *  `infer_category`, used as a fallback for rows without a stored category. */
export function inferCategory(connectionType: string, panelType: string | null): AssetCategoryId {
  if (connectionType === "winrm") return "windows"
  if (connectionType === "rdp") return "windows_rdp"
  if (connectionType === "hosting") return "hosting"
  if (connectionType === "ssh" && panelType) return "hosting"
  return "vps"
}

/** The category descriptor for an existing asset (stored category, else inferred). */
export function categoryForServer(s: Pick<Server, "category" | "connection_type" | "panel_type">): AssetCategory {
  const id = s.category ?? inferCategory(s.connection_type, s.panel_type)
  return categoryById(id) ?? ASSET_CATEGORIES[1] // fallback → VPS
}

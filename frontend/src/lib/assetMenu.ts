import {
  Archive, Clock, Cog, FileText, FolderOpen, KeyRound, LayoutDashboard,
  LayoutPanelTop, Package, ShieldCheck,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"
import type { Server } from "@/types"

/**
 * Which sections an asset gets — decided by what it can DO, not by what type it is.
 *
 * A per-type list looks simpler right up until reality arrives: a VPS with CyberPanel on it
 * is both a VPS and a panel; a droplet added over SSH is both a VPS and a cloud instance; a
 * Windows box may or may not answer on Remote Desktop. Hardcoding a list per type means
 * every mixed case needs its own list, and the lists drift apart the first time one is
 * edited without the others.
 *
 * So an asset resolves to a set of capabilities, each section declares the one it needs, and
 * the mixed cases fall out correctly with no extra code.
 *
 * **A section that can never work on this asset is absent, not disabled.** A permanently
 * dead row is noise on every single visit, and worse, it implies the feature exists here and
 * is merely switched off. (A section withheld by the customer's *plan* is a different thing
 * — that deserves a lock, because paying would genuinely unlock it.)
 *
 * Every rule below was read off the services rather than assumed:
 *   - Files runs over SFTP (paramiko)              → SSH only
 *   - Logs reads Linux paths, no Windows branch    → SSH only
 *   - Backups shell out to tar / mysqldump         → SSH only
 *   - Installed probes a Linux filesystem          → SSH only
 *   - Firewall and SSH keys are ufw/firewalld      → SSH only
 *   - Security has a Windows check battery         → SSH and WinRM
 *   - Scheduled tasks go through connection_manager → SSH and WinRM
 *   - The interactive terminal refuses non-SSH      → SSH only
 */

export type Capability = "shell" | "sftp" | "unix" | "windows" | "desktop" | "panel" | "cloud"

export function capabilitiesOf(server: Server): Set<Capability> {
  const caps = new Set<Capability>()
  const c = server.connection_type

  if (c === "ssh" || c === "winrm") caps.add("shell")
  if (c === "ssh") { caps.add("sftp"); caps.add("unix") }
  if (c === "winrm") caps.add("windows")
  // A pure RDP asset is desktop-only; a WinRM box can also open one.
  if (c === "rdp" || c === "winrm") caps.add("desktop")
  // A panel is a panel whether we reach it by its API or by SSH to the box it runs on.
  if (server.panel_type || c === "hosting") caps.add("panel")
  if (server.cloud_account_id) caps.add("cloud")

  return caps
}

export interface MenuItem {
  /** Route segment under /servers/:id — "" is the index (Overview). */
  path: string
  label: string
  icon: LucideIcon
  /** The capability this section cannot work without. Absent means "always". */
  needs?: Capability
  /** Grouped in the sidebar so a long menu still scans. */
  group: "manage" | "operate" | "account"
}

/**
 * The registry. Order inside a group is the order shown.
 *
 * Sites, Monitoring, Services and Deployments are deliberately not here yet — their APIs
 * exist but their per-asset screens do not, and a menu item that leads nowhere is worse
 * than one that is missing. They arrive in Phase 3 by adding rows to this list.
 */
export const MENU: MenuItem[] = [
  { path: "", label: "Overview", icon: LayoutDashboard, group: "manage" },
  { path: "hosting", label: "Websites", icon: LayoutPanelTop, needs: "panel", group: "manage" },
  { path: "files", label: "Files", icon: FolderOpen, needs: "sftp", group: "manage" },
  { path: "installed", label: "Installed", icon: Package, needs: "sftp", group: "manage" },

  { path: "security", label: "Security", icon: ShieldCheck, needs: "shell", group: "operate" },
  { path: "access", label: "Firewall & keys", icon: KeyRound, needs: "unix", group: "operate" },
  { path: "scheduler", label: "Scheduled tasks", icon: Clock, needs: "shell", group: "operate" },
  { path: "backups", label: "Backups", icon: Archive, needs: "sftp", group: "operate" },
  { path: "logs", label: "Logs", icon: FileText, needs: "sftp", group: "operate" },

  { path: "settings", label: "Settings", icon: Cog, group: "account" },
]

/** The sections this particular asset can actually use. */
export function menuFor(server: Server): MenuItem[] {
  const caps = capabilitiesOf(server)
  return MENU.filter((item) => !item.needs || caps.has(item.needs))
}

/** Which quick actions belong in the asset header. */
export function actionsFor(server: Server) {
  const caps = capabilitiesOf(server)
  return {
    // The interactive terminal refuses anything that is not SSH, so offering it elsewhere
    // would open a session that immediately closes.
    terminal: caps.has("sftp"),
    desktop: caps.has("desktop"),
    // Ally needs somewhere to run what it decides. An RDP box has no command channel.
    ally: caps.has("shell"),
  }
}

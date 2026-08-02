import {
  Activity, Archive, CalendarClock, Clock, Cog, Database, FileText, FolderOpen, Globe, HeartPulse,
  Flag, KeyRound, Code2, LayoutDashboard, LayoutPanelTop, Package, Rocket, ShieldCheck,
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
  /**
   * A capability whose PRESENCE makes this section wrong.
   *
   * Needed because "works on a plain server, but a control panel owns this itself" is a
   * real shape. PHP is the case: on a CyberPanel box PHP is lsphp with the panel's own
   * vhost layout and its own switcher, so our page read a server running 77 PHP sites and
   * reported "no PHP websites found" — honest, but a menu item promising something it
   * cannot deliver.
   */
  excludes?: Capability
  /** Grouped in the sidebar so a long menu still scans. */
  group: "manage" | "operate" | "account"
}

/**
 * The registry. Order inside a group is the order shown.
 *
 * "Start here" leads while it exists, because on a fresh server it is the one thing that
 * has to happen before anything else means anything. It disappears once answered, and then
 * Sites leads — a server exists to serve something, and that is what an owner opens.
 *
 * Note the deliberate split between "Sites" and "Control panel". They sound similar and are
 * not: Sites is what this machine actually serves — discovered from its own web server
 * config, joined with uptime and certificate state — while Control panel is the panel's own
 * operations (its website records, databases, email). A CyberPanel box legitimately has
 * both, and calling the second one "Websites" made two items compete for the same meaning.
 */
/** On a Linux server the home page is a one-time question, so it is named as one. */
export const HOME_LABEL_START = "Start here"
/** On an asset that never faces that question it really is an overview, so it says so. */
export const HOME_LABEL_OVERVIEW = "Overview"

export const MENU: MenuItem[] = [
  // Labelled by what it IS, which differs by asset — see the rename in `menuFor`.
  // "Overview" was the old name for both and it was misleading: on a Linux server this
  // page is a one-time decision, not a summary of anything.
  { path: "", label: HOME_LABEL_START, icon: Flag, group: "manage" },
  { path: "sites", label: "Sites", icon: Globe, needs: "sftp", group: "manage" },
  { path: "hosting", label: "Control panel", icon: LayoutPanelTop, needs: "panel", group: "manage" },
  { path: "files", label: "Files", icon: FolderOpen, needs: "sftp", group: "manage" },
  { path: "installed", label: "Installed", icon: Package, needs: "sftp", group: "manage" },
  { path: "php", label: "PHP", icon: Code2, needs: "sftp", excludes: "panel", group: "manage" },
  { path: "databases", label: "Databases", icon: Database, needs: "unix", excludes: "panel", group: "manage" },

  { path: "monitoring", label: "Monitoring", icon: Activity, needs: "shell", group: "operate" },
  { path: "services", label: "Services", icon: HeartPulse, needs: "unix", group: "operate" },
  { path: "deployments", label: "Deployments", icon: Rocket, needs: "sftp", group: "operate" },
  { path: "security", label: "Security", icon: ShieldCheck, needs: "shell", group: "operate" },
  { path: "access", label: "Firewall & keys", icon: KeyRound, needs: "unix", group: "operate" },
  { path: "scheduler", label: "Scheduled tasks", icon: Clock, needs: "shell", group: "operate" },
  { path: "cron", label: "Cron jobs", icon: CalendarClock, needs: "unix", group: "operate" },
  { path: "backups", label: "Backups", icon: Archive, needs: "sftp", group: "operate" },
  { path: "logs", label: "Logs", icon: FileText, needs: "sftp", group: "operate" },

  { path: "settings", label: "Settings", icon: Cog, group: "account" },
]

/**
 * The sections this particular asset can actually use.
 *
 * Overview is a **one-time** page on a Linux server. While the machine is clean it asks the
 * question that decides everything else — is ServerAlly the control panel here, or are we
 * installing a real one and watching it? Once that is answered it has nothing left to say,
 * so it leaves the menu and the server's home becomes Sites. Every other thing that used to
 * be on it (specs, installed software, metrics, services) has its own section.
 *
 * An asset that cannot host — Windows, Remote Desktop, a hosting account — never faces the
 * question and has no Sites, so Overview stays as its only page.
 */
/**
 * A panel section is named after the panel, because that is the word the customer knows.
 *
 * Someone who bought a CyberPanel server thinks "CyberPanel", not "control panel" — the
 * generic label makes them stop and work out which of the two site-ish sections they want.
 * Same reasoning that made Sites stop being called Websites.
 */
const PANEL_LABEL: Record<string, string> = {
  cyberpanel: "CyberPanel",
  cpanel: "cPanel",
  whm: "WHM",
  plesk: "Plesk",
  directadmin: "DirectAdmin",
  hestiacp: "HestiaCP",
  aapanel: "aaPanel",
  cloudpanel: "CloudPanel",
}

export function menuFor(server: Server, opts: { decided?: boolean } = {}): MenuItem[] {
  const caps = capabilitiesOf(server)
  const items = MENU.filter(
    (item) => (!item.needs || caps.has(item.needs))
      && !(item.excludes && caps.has(item.excludes)),
  )
  const named = items.map((item) => {
    if (item.path !== "hosting") return item
    // A panel we do not have a name for keeps the generic label rather than showing a raw
    // database value like "directadmin_v2" to a customer.
    const label = PANEL_LABEL[(server.panel_type ?? "").toLowerCase()]
    return label ? { ...item, label } : item
  })
  // Defaults to NOT decided, so the question stays on screen until we know otherwise —
  // a menu that hides the fork while the answer is still loading would flash it away on
  // the one server that needs it.
  const hasSites = named.some((i) => i.path === "sites")
  if (hasSites && opts.decided) return named.filter((i) => i.path !== "")
  // An asset with no Sites never faces the question, so its home page is a genuine
  // overview — calling it "Start here" would promise a choice it will never be offered.
  return hasSites
    ? named
    : named.map((i) => (i.path === ""
      ? { ...i, label: HOME_LABEL_OVERVIEW, icon: LayoutDashboard }
      : i))
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


/**
 * Which "add a website" doors to offer on this asset.
 *
 * The deterministic installers write a web-server config directly, which a control panel
 * owns — so on a panel server they refuse at runtime. Offering a button that then says no
 * is worse than not offering it: the customer has already decided to trust it by the time
 * it declines. So the chooser reads the asset first, the same way the menu does.
 */
export interface InstallerOptions {
  /** Empty site, WordPress, Laravel, web application — anything that writes a vhost. */
  direct: boolean
  /** Create it through the panel instead, which is where a panel server's sites belong. */
  panel: boolean
  /** Ally, which looks at the server and adapts — the case an installer cannot handle. */
  ally: boolean
}

export function installerOptionsFor(server: Server): InstallerOptions {
  const caps = capabilitiesOf(server)
  const hasPanel = caps.has("panel")
  return {
    // Needs SFTP to place files and a web server we own.
    direct: caps.has("sftp") && !hasPanel,
    panel: hasPanel,
    // Ally needs somewhere to run what it decides.
    ally: caps.has("shell"),
  }
}

import {
  Activity, Clock, Cog, FileText, LayoutDashboard, Lock,
} from "lucide-react"
import type { LucideIcon } from "lucide-react"
import type { SiteDetail } from "@/api/sites"

/**
 * A site's own menu.
 *
 * A site is a first-class thing, like a server — reached from the fleet list or from the
 * server it lives on, and the same page either way. It used to live inside the server's
 * layout, which meant you could be looking at one website while every menu item beside it
 * was about the machine: firewall, PHP versions, backups. Those belong to the server. Logs
 * and scheduled jobs belong to the site, and on a machine with fifteen sites the per-server
 * versions cannot answer the question anyone actually asks — *what about this one*.
 *
 * Decided by what the site can DO, the same way the server menu works. A section that can
 * never apply here is ABSENT, not greyed out: a permanently dead row is noise on every
 * visit, and worse, it implies the feature exists and is merely switched off.
 */

export type SiteCapability = "shell" | "panel" | "installed" | "ours"

export function capabilitiesOf(site: SiteDetail): Set<SiteCapability> {
  const caps = new Set<SiteCapability>()
  // Everything below reads or edits the server the site sits on, over SSH.
  if (site.server?.connection_type === "ssh") caps.add("shell")
  // A control panel owns its sites: its own logs, its own certificates, its own removal.
  // Anything we did behind its back would be invisible to it.
  if (site.server?.panel_type) caps.add("panel")
  // Something is actually running here, as opposed to an empty site waiting for a choice.
  if (site.requested_type && site.requested_type !== "static") caps.add("installed")
  if (site.app_type && site.app_type !== "static" && site.app_type !== "unknown") {
    caps.add("installed")
  }
  // We built it, so we know its layout and may safely change or remove it.
  if (site.source === "manual") caps.add("ours")
  return caps
}

export interface SiteMenuItem {
  /** Route segment under /sites/:id — "" is the index. */
  path: string
  label: string
  icon: LucideIcon
  needs?: SiteCapability
  /** A capability whose PRESENCE makes this section wrong. */
  excludes?: SiteCapability
}

export const SITE_MENU: SiteMenuItem[] = [
  { path: "", label: "Overview", icon: LayoutDashboard },
  // Certificates on a panel server are the panel's own job, renewed by it.
  { path: "https", label: "HTTPS", icon: Lock, needs: "shell", excludes: "panel" },
  { path: "logs", label: "Logs", icon: FileText, needs: "shell" },
  { path: "cron", label: "Scheduled jobs", icon: Clock, needs: "shell" },
  // Deployments are still per-server; a site-scoped one needs deploy targets linked to a
  // site, which is its own piece of work. Left out until then rather than shown and dead.
  { path: "uptime", label: "Uptime", icon: Activity },
  { path: "settings", label: "Settings", icon: Cog },
]

export function menuForSite(site: SiteDetail): SiteMenuItem[] {
  const caps = capabilitiesOf(site)
  return SITE_MENU.filter(
    (item) => (!item.needs || caps.has(item.needs))
      && !(item.excludes && caps.has(item.excludes)),
  )
}

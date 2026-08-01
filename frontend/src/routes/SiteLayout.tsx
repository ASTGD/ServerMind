import { Link, NavLink, Outlet, useParams } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import {
  ArrowLeft, CircleAlert, CircleCheck, CircleDashed, ExternalLink, Loader2, Server as ServerIcon,
} from "lucide-react"
import { getSite, APP_LABEL, type SiteDetail } from "@/api/sites"
import { menuForSite } from "@/lib/siteMenu"
import { cn } from "@/lib/utils"

/**
 * One site, with its own menu.
 *
 * A site is a first-class thing here, like a server: it has one address, and both the fleet
 * list and a server's own list lead to it. It used to be nested inside the server's layout,
 * which meant looking at a website while the menu beside it offered the machine's firewall
 * and PHP versions.
 *
 * The parent server is a LINK in the header, not the menu — the relationship matters, but a
 * site is not a subsection of a server any more than a server is a subsection of the fleet.
 *
 * Read fresh by id, so the page works from a link or a bookmark, and shared with every tab
 * beneath it through the outlet context rather than fetched again per tab.
 */
export default function SiteLayout() {
  const { siteId = "" } = useParams()

  const { data: site, isLoading } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId),
    // While something is installing the answer changes on its own, so the page keeps up
    // rather than making someone reload to find out whether it worked.
    refetchInterval: (q) => (q.state.data?.status === "installing" ? 5000 : false),
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <Loader2 size={20} className="animate-spin" />
      </div>
    )
  }
  if (!site) {
    return (
      <p className="py-16 text-center text-small text-muted-foreground">
        This site is no longer here.
      </p>
    )
  }

  const menu = menuForSite(site)

  return (
    <div className="space-y-4">
      <header>
        <Link
          to={`/servers/${site.server.id}/sites`}
          className="inline-flex items-center gap-1 text-caption text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft size={12} /> All sites on {site.server.name}
        </Link>

        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="text-h1 text-foreground">{site.domain}</h1>
          <a
            href={`${site.has_ssl ? "https" : "http"}://${site.domain}`}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-caption text-muted-foreground hover:text-foreground"
          >
            <ExternalLink size={11} /> Open
          </a>
        </div>

        <p className="mt-0.5 flex flex-wrap items-center gap-2 text-small text-muted-foreground">
          <SiteStatus site={site} />
          <span>·</span>
          <span>{APP_LABEL[site.app_type] ?? site.app_type}
            {site.app_version ? ` ${site.app_version}` : ""}</span>
          <span>·</span>
          <Link to={`/servers/${site.server.id}/sites`}
            className="inline-flex items-center gap-1 hover:text-foreground">
            <ServerIcon size={11} /> {site.server.name}
          </Link>
        </p>
      </header>

      <div className="flex flex-col gap-4 lg:flex-row">
        {/* A card inside the page, not a second full-height rail glued to the app nav —
            same shape as the server's own menu, so the two levels read as siblings. */}
        <nav className="w-full shrink-0 lg:w-56">
          <div className="rounded-xl bg-muted/40 p-2">
            {menu.map((item) => (
              <NavLink
                key={item.path}
                to={item.path ? `/sites/${site.id}/${item.path}` : `/sites/${site.id}`}
                end={item.path === ""}
                className={({ isActive }) => cn(
                  "flex items-center gap-2 rounded-lg px-2.5 py-1.5 text-sm transition-colors",
                  isActive
                    ? "bg-card font-medium text-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-card/60 hover:text-foreground",
                )}
              >
                <item.icon size={14} />
                {item.label}
              </NavLink>
            ))}
          </div>

          {/* Facts, not links — what am I looking at, without a click. */}
          <dl className="mt-2 space-y-1 px-2.5 text-caption text-muted-foreground">
            {site.doc_root && (
              <div className="flex justify-between gap-2">
                <dt>Folder</dt>
                <dd className="truncate font-mono" title={site.doc_root}>{site.doc_root}</dd>
              </div>
            )}
            <div className="flex justify-between gap-2">
              <dt>HTTPS</dt>
              <dd>{site.has_ssl ? "on" : "off"}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt>Added by</dt>
              <dd>{site.source === "manual" ? "ServerAlly" : "found on the server"}</dd>
            </div>
          </dl>
        </nav>

        <div className="min-w-0 flex-1">
          <Outlet context={{ site }} />
        </div>
      </div>
    </div>
  )
}

function SiteStatus({ site }: { site: SiteDetail }) {
  if (site.status === "installing") {
    return (
      <span className="inline-flex items-center gap-1">
        <Loader2 size={12} className="animate-spin" /> Setting up
      </span>
    )
  }
  if (site.status === "failed") {
    return (
      <span className="inline-flex items-center gap-1 text-destructive">
        <CircleAlert size={12} /> Setup failed
      </span>
    )
  }
  const up = site.uptime?.status
  if (up === "up") {
    return (
      <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
        <CircleCheck size={12} /> Up
      </span>
    )
  }
  if (up === "down") {
    return (
      <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400">
        <CircleAlert size={12} /> Down{site.uptime?.error ? ` — ${site.uptime.error}` : ""}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1">
      <CircleDashed size={12} /> Not monitored
    </span>
  )
}

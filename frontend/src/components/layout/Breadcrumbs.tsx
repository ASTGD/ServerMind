import { Link, useLocation } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { ChevronRight } from "lucide-react"
import { getServer } from "@/api/servers"
import { getSite } from "@/api/sites"
import { APP_SECTIONS } from "@/lib/siteMenu"

/** Human labels for known path segments. Unknown segments are title-cased;
 *  opaque ids (server/playbook/token) are resolved or shown as "Details". */
const LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  servers: "Servers",
  playbooks: "Playbooks",
  scripts: "My Scripts",
  generate: "Generate",
  logs: "Logs",
  team: "Team",
  settings: "Settings",
  accept: "Accept invite",
  overview: "Overview",
  terminal: "Terminal",
  files: "Files",
  security: "Security",
  backups: "Backups",
  scheduler: "Scheduler",
  hosting: "Hosting",
  installed: "Installed",
  sites: "Sites",
  https: "HTTPS",
  cron: "Scheduled jobs",
  uptime: "Uptime",
  // Title-casing turns this into "Php", which is not how anybody writes it.
  php: "PHP version",
  database: "Database",
  deploy: "Deploy",
}

function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

interface Crumb {
  label: string
  to: string
}

/** Contextual breadcrumb trail for the top bar. Derives the trail from the URL and
 *  resolves the server name when on a /servers/:id route (shares the cached query). */
export default function Breadcrumbs() {
  const { pathname } = useLocation()
  const seg = pathname.split("/").filter(Boolean)

  const serverId = seg[0] === "servers" && seg.length >= 2 ? seg[1] : undefined
  const { data: server } = useQuery({
    queryKey: ["server", serverId],
    queryFn: () => getServer(serverId!),
    enabled: !!serverId,
    staleTime: 60_000,
  })

  // A site is reached at its own address, but it lives on a machine, and the trail is where
  // that shows. Without it a site page is an island: the domain alone never says which of
  // forty servers you are about to change. The same cached query the page itself uses.
  const siteId = seg[0] === "sites" && seg.length >= 2 ? seg[1] : undefined
  const { data: site } = useQuery({
    queryKey: ["site", siteId],
    queryFn: () => getSite(siteId!),
    enabled: !!siteId,
    staleTime: 60_000,
  })

  const crumbs: Crumb[] = []
  let acc = ""

  // Servers / <server> / <domain> — the site's own segments hang off its server, so the
  // way back up is to the machine rather than to a flat list of every site.
  if (siteId) {
    crumbs.push({ label: "Servers", to: "/servers" })
    crumbs.push({
      label: site?.server?.name ?? "…",
      to: site ? `/servers/${site.server.id}/sites` : "/servers",
    })
    crumbs.push({ label: site?.domain ?? "…", to: `/sites/${siteId}` })
    seg.slice(2).forEach((s) => {
      // The application section is named after the application, the same as its menu row —
      // somebody with a WordPress site is looking for the word WordPress, not "App".
      const label = s === "app"
        ? (APP_SECTIONS[(site?.app_type || "").toLowerCase()]?.label ?? "Application")
        : LABELS[s] ?? titleCase(s)
      crumbs.push({ label, to: `/sites/${siteId}/${s}` })
    })
    return <Trail crumbs={crumbs} />
  }

  seg.forEach((s, i) => {
    acc += `/${s}`
    if (i === 1 && seg[0] === "servers") {
      crumbs.push({ label: server?.name ?? "…", to: acc })
    } else {
      crumbs.push({ label: LABELS[s] ?? (s.length > 20 ? "Details" : titleCase(s)), to: acc })
    }
  })

  if (crumbs.length === 0) crumbs.push({ label: "Dashboard", to: "/dashboard" })

  return <Trail crumbs={crumbs} />
}

function Trail({ crumbs }: { crumbs: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-sm">
      {crumbs.map((c, i) => {
        const last = i === crumbs.length - 1
        return (
          // Keyed by POSITION. The destination is not unique — while a site's server is
          // still loading, its crumb points at /servers too, which is the same place the
          // first crumb points, and React then drops one of them.
          <span key={i} className="flex min-w-0 items-center gap-1.5">
            {i > 0 && <ChevronRight size={14} className="shrink-0 text-muted-foreground/40" />}
            {last ? (
              <span className="truncate font-semibold text-foreground">{c.label}</span>
            ) : (
              <Link
                to={c.to}
                className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
              >
                {c.label}
              </Link>
            )}
          </span>
        )
      })}
    </nav>
  )
}

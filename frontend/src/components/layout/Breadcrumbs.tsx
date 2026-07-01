import { Link, useLocation } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { ChevronRight } from "lucide-react"
import { getServer } from "@/api/servers"

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

  const crumbs: Crumb[] = []
  let acc = ""
  seg.forEach((s, i) => {
    acc += `/${s}`
    if (i === 1 && seg[0] === "servers") {
      crumbs.push({ label: server?.name ?? "…", to: acc })
    } else {
      crumbs.push({ label: LABELS[s] ?? (s.length > 20 ? "Details" : titleCase(s)), to: acc })
    }
  })

  if (crumbs.length === 0) crumbs.push({ label: "Dashboard", to: "/dashboard" })

  return (
    <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-sm">
      {crumbs.map((c, i) => {
        const last = i === crumbs.length - 1
        return (
          <span key={c.to} className="flex min-w-0 items-center gap-1.5">
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

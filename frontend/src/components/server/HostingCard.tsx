import { Link, useNavigate } from "react-router-dom"
import { LayoutPanelTop, Globe, ArrowUpRight } from "lucide-react"
import type { Server } from "@/types"
import ConnectionStatus from "./ConnectionStatus"

interface Props {
  server: Server
}

/** A hosting panel (CyberPanel / cPanel / Plesk / DirectAdmin). Same card format as a
 *  machine so the grid stays consistent, but the body is panel-flavored (panel type instead
 *  of OS) with an "Open panel" quick action — it never shows CPU/RAM, so it reads distinctly. */
export default function HostingCard({ server }: Props) {
  const navigate = useNavigate()
  const panel = server.panel_type ? server.panel_type[0].toUpperCase() + server.panel_type.slice(1) : "Hosting panel"
  return (
    <Link
      to={`/servers/${server.id}`}
      className="flex flex-col rounded-lg border border-border bg-card p-4 transition-all hover:border-primary/50 hover:shadow-sm"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" title="Hosting panel">
            <LayoutPanelTop size={18} />
          </div>
          <div className="min-w-0">
            <p className="truncate font-medium text-foreground">{server.name}</p>
            <p className="truncate text-xs text-muted-foreground">{server.host}</p>
          </div>
        </div>
        <ConnectionStatus status={server.status} />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span className="flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 font-medium">
          <Globe size={11} />
          {panel}
        </span>
        <span className="rounded bg-muted px-1.5 py-0.5">Hosting panel</span>
      </div>

      <div className="mt-3 flex items-center justify-end border-t border-border pt-2.5">
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); navigate(`/servers/${server.id}/hosting`) }}
          className="flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
        >
          <ArrowUpRight size={13} /> Open panel
        </button>
      </div>
    </Link>
  )
}

import { Link } from "react-router-dom"
import { LayoutPanelTop, Globe, ExternalLink } from "lucide-react"
import type { Server } from "@/types"
import ConnectionStatus from "./ConnectionStatus"

interface Props {
  server: Server
}

/** The web port each panel serves its dashboard on — "Open panel" launches it in a new tab. */
const PANEL_PORT: Record<string, number> = { cyberpanel: 8090, cpanel: 2083, plesk: 8443, directadmin: 2222 }

/** A hosting panel (CyberPanel / cPanel / Plesk / DirectAdmin). Same card format as a
 *  machine so the grid stays consistent, but the body is panel-flavored (panel type instead
 *  of OS) with an "Open panel" launch action that opens the real panel in a new tab. */
export default function HostingCard({ server }: Props) {
  const panel = server.panel_type ? server.panel_type[0].toUpperCase() + server.panel_type.slice(1) : "Hosting panel"
  const panelUrl = `https://${server.host}:${PANEL_PORT[server.panel_type ?? ""] ?? 8090}`
  return (
    <Link
      to={`/servers/${server.id}`}
      className="flex flex-col rounded-lg border border-border bg-card p-4 transition-all hover:border-primary/50 hover:shadow-sm"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" title="Hosting panel">
            <LayoutPanelTop size={18} aria-hidden />
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

      <div className="mt-auto flex justify-end pt-3">
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); window.open(panelUrl, "_blank", "noopener,noreferrer") }}
          title={`Open ${panel} at ${panelUrl}`}
          className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-emerald-500/50 hover:bg-emerald-500/5 hover:text-emerald-600 dark:hover:text-emerald-400"
        >
          <ExternalLink size={13} /> Open panel
        </button>
      </div>
    </Link>
  )
}

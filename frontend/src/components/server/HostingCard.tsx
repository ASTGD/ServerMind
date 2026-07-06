import { Link } from "react-router-dom"
import { LayoutPanelTop, Globe, ExternalLink } from "lucide-react"
import type { Server } from "@/types"
import { hostingBrand } from "@/lib/assetBrands"
import BrandIcon, { hasBrandIcon } from "./BrandIcon"
import AssetMetrics from "./AssetMetrics"
import ConnectionStatus from "./ConnectionStatus"

interface Props {
  server: Server
}

/** The web port each panel serves its dashboard on — "Open panel" launches it in a new tab. */
const PANEL_PORT: Record<string, number> = { cyberpanel: 8090, cpanel: 2083, plesk: 8443, directadmin: 2222 }

/** A hosting panel (CyberPanel / cPanel / Plesk / DirectAdmin). Same card format as a
 *  machine so the grid stays consistent, but the whole card is BRANDED to its panel
 *  (background/border/icon/badge/button in the panel's color) and the body is
 *  panel-flavored, with an "Open panel" action that opens the real panel in a new tab. */
export default function HostingCard({ server }: Props) {
  const brand = hostingBrand(server.panel_type)
  const panelName = brand?.name ?? (server.panel_type ? server.panel_type[0].toUpperCase() + server.panel_type.slice(1) : "Hosting panel")
  const panelUrl = `https://${server.host}:${PANEL_PORT[server.panel_type ?? ""] ?? 8090}`
  const cardClass = brand ? brand.card : "border-border bg-card hover:border-primary/50"
  const tileClass = brand ? brand.tile : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
  const badgeClass = brand ? brand.badge : "bg-muted"
  const buttonHover = brand ? brand.button : "hover:border-emerald-500/50 hover:bg-emerald-500/5 hover:text-emerald-600 dark:hover:text-emerald-400"
  return (
    <Link
      to={`/servers/${server.id}`}
      className={`flex aspect-square flex-col rounded-2xl border p-4 transition-all hover:shadow-sm ${cardClass}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg ${hasBrandIcon(server.panel_type) ? "border border-border bg-background" : tileClass}`} title={panelName}>
            {hasBrandIcon(server.panel_type) ? <BrandIcon slug={server.panel_type ?? undefined} size={24} /> : <LayoutPanelTop size={18} aria-hidden />}
          </div>
          <div className="min-w-0">
            <p className="truncate font-medium text-foreground">{server.name}</p>
            <p className="truncate text-xs text-muted-foreground">{server.host}</p>
          </div>
        </div>
        <ConnectionStatus status={server.status} />
      </div>

      <div className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className={`flex items-center gap-1 rounded px-1.5 py-0.5 font-medium ${badgeClass}`}>
            <Globe size={11} />
            {panelName}
          </span>
          <span className="rounded bg-muted px-1.5 py-0.5 text-muted-foreground">Hosting panel</span>
        </div>

        <div className="mt-auto pt-3">
          <AssetMetrics server={server} />
        </div>
      </div>

      <div className="pt-3">
        <button
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); window.open(panelUrl, "_blank", "noopener,noreferrer") }}
          title={`Open ${panelName} at ${panelUrl}`}
          className={`flex w-full items-center justify-center gap-1.5 rounded-lg border border-border bg-background/60 px-2.5 py-2 text-xs font-medium text-foreground transition-colors ${buttonHover}`}
        >
          <ExternalLink size={13} /> Open panel
        </button>
      </div>
    </Link>
  )
}

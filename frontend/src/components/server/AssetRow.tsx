import { useState } from "react"
import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import {
  AlertTriangle, ChevronRight, ExternalLink, MonitorPlay, Sparkles, TerminalSquare,
} from "lucide-react"
import type { Server } from "@/types"
import { getMetrics } from "@/api/servers"
import { groupForServer } from "@/lib/assetGroups"
import { hostingBrand } from "@/lib/assetBrands"
import BrandIcon, { osIconSlug, providerIconSlug, hasBrandIcon } from "./BrandIcon"
import { useTerminalStore } from "@/store/terminalStore"
import { useAssistantStore } from "@/store/assistantStore"
import { cn } from "@/lib/utils"

/**
 * One asset, as a row.
 *
 * A row can say more per pixel than a card, but only if it stays honest about what this
 * particular asset can actually report. An RDP box has no shell, so it can never produce
 * CPU or memory — showing empty bars there would read as "broken", when the truth is
 * "not applicable". A hosting account has no machine metrics at all. So the middle of the
 * row is chosen per asset type rather than rendered once and left blank.
 */

const GRADE_TONE: Record<string, string> = {
  A: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  B: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  C: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  D: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  F: "bg-red-500/15 text-red-700 dark:text-red-300",
}

function statusDot(server: Server) {
  if (server.status === "online") return "bg-emerald-500"
  if (server.status === "auth_failed" || server.status === "host_changed") return "bg-red-500"
  if (server.status === "offline") return "bg-red-500"
  return "bg-muted-foreground/40"
}

/** CPU / RAM / disk as three small numbers. Shares the Dashboard's per-server query cache,
 *  so a fleet-sized list costs no extra requests. */
function LiveNumbers({ server }: { server: Server }) {
  const live = server.status === "online"
    && (server.connection_type === "ssh" || server.connection_type === "winrm")

  const { data, isError } = useQuery({
    queryKey: ["server-metrics", server.id],
    queryFn: () => getMetrics(server.id),
    enabled: live,
    retry: false,
    staleTime: 30_000,
    refetchInterval: live ? 60_000 : false,
  })

  if (!live || isError || !data) return null

  const cells: [string, number | null][] = [
    ["CPU", data.cpu_percent], ["RAM", data.ram_percent], ["Disk", data.disk_percent],
  ]
  return (
    <div className="hidden shrink-0 items-center gap-3 sm:flex">
      {cells.map(([label, value]) => (
        <span key={label} className="text-[11.5px] tabular-nums text-muted-foreground">
          {label}{" "}
          <span className={cn(
            "font-medium",
            (value ?? 0) >= 90 ? "text-red-600 dark:text-red-400"
              : (value ?? 0) >= 70 ? "text-amber-600 dark:text-amber-400"
                : "text-foreground",
          )}>
            {value == null ? "—" : `${Math.round(value)}%`}
          </span>
        </span>
      ))}
    </div>
  )
}

interface Props {
  server: Server
  /** Health grade from the fleet report, when the caller already has it. */
  grade?: string
  /** How many websites we have recorded on this asset. */
  sites?: number
  /** True when this row sits inside its own provider's zone, where the heading already
   *  names the provider — so the badge would be the same fact twice. */
  inProviderZone?: boolean
  onOpenDesktop?: (server: Server) => void
}

export default function AssetRow({ server, grade, sites, inProviderZone, onOpenDesktop }: Props) {
  const [showMsg, setShowMsg] = useState(false)
  const openSession = useTerminalStore((s) => s.openSession)
  const openServer = useAssistantStore((s) => s.openServer)

  const group = groupForServer(server)
  const GroupIcon = group.icon
  const isRdp = server.connection_type === "rdp"
  const canDesktop = server.connection_type === "winrm" || isRdp
  const isHosting = server.connection_type === "hosting"
  const needsAttention = server.status === "auth_failed" || server.status === "host_changed"

  // The panel each hosting asset serves its dashboard on, so the row can link straight to it.
  const PANEL_PORT: Record<string, number> = {
    cyberpanel: 8090, cpanel: 2083, plesk: 8443, directadmin: 2222,
  }
  const panel = hostingBrand(server.panel_type)

  const osSlug = osIconSlug(server.os_type)
    ?? (group.id === "windows" || canDesktop ? "windows" : undefined)
  const osBrand = hasBrandIcon(osSlug)
  const provider = server.cloud_account_id && !inProviderZone ? server.tags?.[0] : undefined
  const providerSlug = providerIconSlug(provider)

  // The second line answers "what is this and where does it live", in the order someone
  // scanning actually needs it.
  const facts: string[] = [`${server.host}:${server.port}`]
  if (server.os_type) facts.push(server.os_version ? `${server.os_type} ${server.os_version}` : server.os_type)
  if (sites) facts.push(`${sites} site${sites === 1 ? "" : "s"}`)
  if (needsAttention) facts.push(server.status === "auth_failed" ? "sign-in failing" : "host key changed")

  function act(e: React.MouseEvent, fn: () => void) {
    e.preventDefault()
    e.stopPropagation()
    fn()
  }

  return (
    <Link
      to={`/servers/${server.id}`}
      className={cn(
        "flex items-center gap-3 border-t border-border px-3 py-2.5 transition-colors first:border-t-0 hover:bg-muted/40",
        needsAttention && "bg-red-500/[0.03]",
      )}
    >
      <span className={cn("h-2 w-2 shrink-0 rounded-full", statusDot(server))}
        title={server.status ?? "unknown"} />

      <div className={cn(
        "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
        osBrand ? "border border-border bg-muted/40" : group.accent,
      )} title={server.os_type || group.label}>
        {isHosting && hasBrandIcon(server.panel_type)
          ? <BrandIcon slug={server.panel_type ?? undefined} size={18} />
          : osBrand ? <BrandIcon slug={osSlug} size={18} /> : <GroupIcon size={16} />}
      </div>

      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-1.5 truncate text-[14px] font-medium text-foreground">
          {server.name}
          {hasBrandIcon(providerSlug) && <BrandIcon slug={providerSlug} size={12} />}
          {/* A control panel is a PROPERTY of this machine, not a kind of machine — so it is
              a chip here rather than a group of its own, and it is named after the real
              panel (the 29 July rule), because "Hosting panel" tells nobody anything. */}
          {server.panel_type && (
            <span className="shrink-0 rounded border border-border px-1.5 py-px text-[10.5px] font-normal text-muted-foreground">
              {/* The raw value when we have no brand for it: a panel we do not recognise is
                  still a panel, and dropping the chip would hide a fact we hold. */}
              {panel?.name ?? server.panel_type}
            </span>
          )}
        </p>
        <p className="truncate text-[11.5px] text-muted-foreground">{facts.join(" · ")}</p>
      </div>

      {/* An asset only shows numbers it can genuinely produce. */}
      {!isRdp && !isHosting && <LiveNumbers server={server} />}
      {server.status !== "online" && server.last_seen && (
        <span className="hidden shrink-0 text-[11.5px] text-muted-foreground md:block">
          {(() => {
            try {
              return `Last seen ${formatDistanceToNow(new Date(server.last_seen), { addSuffix: true })}`
            } catch { return "Offline" }
          })()}
        </span>
      )}

      {grade && (
        <span className={cn(
          "hidden shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold sm:block",
          GRADE_TONE[grade] ?? "bg-muted text-muted-foreground",
        )} title="Health grade">
          {grade}
        </span>
      )}

      {needsAttention && (
        <div className="relative shrink-0">
          <button
            type="button" aria-label="Action needed"
            onClick={(e) => act(e, () => setShowMsg((v) => !v))}
            className="flex h-6 w-6 items-center justify-center rounded-full text-red-500 hover:bg-red-500/10"
          >
            <AlertTriangle size={14} />
          </button>
          {showMsg && (
            <div className="absolute right-0 top-7 z-20 w-60 rounded-lg border border-border bg-card p-3 text-left shadow-lg">
              <p className="text-xs font-semibold text-foreground">
                {server.status === "auth_failed" ? "We can’t sign in" : "The host key changed"}
              </p>
              <p className="mt-1 text-[11px] text-muted-foreground">
                Open the asset to fix it.
              </p>
            </div>
          )}
        </div>
      )}

      <div className="flex shrink-0 items-center gap-1">
        {canDesktop ? (
          <button
            type="button" onClick={(e) => act(e, () => onOpenDesktop?.(server))}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <MonitorPlay size={13} /> <span className="hidden lg:inline">Desktop</span>
          </button>
        ) : isHosting ? (
          <a
            href={`https://${server.host}:${PANEL_PORT[server.panel_type ?? ""] ?? 8090}`}
            target="_blank" rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <ExternalLink size={13} /> <span className="hidden lg:inline">{panel?.name ?? "Panel"}</span>
          </a>
        ) : (
          <button
            type="button" onClick={(e) => act(e, () => openSession(server))}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <TerminalSquare size={13} /> <span className="hidden lg:inline">Terminal</span>
          </button>
        )}
        {/* An RDP box has no command channel, so there is nothing for Ally to run there. */}
        {!isRdp && (
          <button
            type="button" onClick={(e) => act(e, () => openServer(server))}
            className="flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Sparkles size={13} /> <span className="hidden lg:inline">Ask Ally</span>
          </button>
        )}
        <ChevronRight size={15} className="text-muted-foreground/60" />
      </div>
    </Link>
  )
}

import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Loader2, RefreshCw, Bell } from "lucide-react"
import { getMetrics } from "@/api/servers"
import { getMetricsHistory } from "@/api/monitoring"
import MetricKpis from "@/components/monitoring/MetricKpis"
import MetricsChart from "@/components/monitoring/MetricsChart"
import AlertsModal from "@/components/server/AlertsModal"
import type { ServerMetrics as IServerMetrics } from "@/types"

interface Props {
  serverId: string
  /**
   * Render for a narrow column (the Overview card) rather than a full-width page.
   *
   * Only spacing depends on it — the same numbers and the same chart appear either way.
   * Note this cannot be a CSS breakpoint: `lg:` follows the VIEWPORT, so on a wide screen a
   * narrow column would still try to fit four cards across and squash them.
   */
  compact?: boolean
}

const WINDOWS: { v: 6 | 24 | 48 | 168; l: string }[] = [
  { v: 6, l: "6h" },
  { v: 24, l: "24h" },
  { v: 48, l: "48h" },
  { v: 168, l: "7d" },
]

function formatUptime(seconds: number | null): string {
  if (seconds === null) return "—"
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

export default function ServerMetrics({ serverId, compact = false }: Props) {
  const [showAlerts, setShowAlerts] = useState(false)
  const [window, setWindow] = useState<6 | 24 | 48 | 168>(24)

  const { data, isLoading, isError, refetch, isFetching } = useQuery<IServerMetrics>({
    queryKey: ["metrics", serverId],
    queryFn: () => getMetrics(serverId),
    refetchInterval: 30_000,
    retry: 1,
  })

  const { data: history = [], isLoading: histLoading } = useQuery({
    queryKey: ["metrics-history", serverId, window],
    queryFn: () => getMetricsHistory(serverId, window),
    refetchInterval: 60_000,
  })

  const ramUsed = data?.ram_used_mb ? `${(data.ram_used_mb / 1024).toFixed(1)} GB` : undefined
  const ramTotal = data?.ram_total_mb ? `${(data.ram_total_mb / 1024).toFixed(1)} GB` : undefined
  const diskUsed = data?.disk_used_gb ? `${data.disk_used_gb.toFixed(1)} GB` : undefined
  const diskTotal = data?.disk_total_gb ? `${data.disk_total_gb.toFixed(1)} GB` : undefined

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-foreground">Live Metrics</h3>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowAlerts(true)}
            title="Alerts"
            className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <Bell size={12} /> Alerts
          </button>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            aria-label="Refresh"
            className="rounded p-1 text-muted-foreground transition-colors hover:text-foreground"
          >
            <RefreshCw size={13} className={isFetching ? "animate-spin" : ""} />
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-6 text-muted-foreground">
          <Loader2 size={18} className="animate-spin" />
        </div>
      ) : isError || !data ? (
        <p className="text-sm text-muted-foreground">Could not load live metrics — server may be offline.</p>
      ) : (
        <>
          <MetricKpis
            history={history}
            cpu={data.cpu_percent}
            ram={data.ram_percent}
            disk={data.disk_percent}
            load={data.load_1}
            ramDetail={ramUsed && ramTotal ? `${ramUsed} / ${ramTotal}` : undefined}
            diskDetail={diskUsed && diskTotal ? `${diskUsed} / ${diskTotal}` : undefined}
            windowLabel={WINDOWS.find((w) => w.v === window)?.l ?? "24h"}
            compact={compact}
          />

          {/* Load average is on its own card now, so only uptime is left to state. */}
          <p className="text-xs text-muted-foreground">
            Uptime{" "}
            <span className="font-mono font-medium text-foreground">
              {formatUptime(data.uptime_seconds ?? null)}
            </span>
          </p>
        </>
      )}

      {/* One chart, always visible.
          Always visible because this is the reason the section exists — hiding it behind a
          disclosure made the page read as "live numbers only", which is what a customer
          reported. One chart rather than three because the useful question is whether the
          CPU spike and the memory spike were the same moment, and three stacked charts made
          the reader line up three x-axes by eye to answer it. */}
      <div className="space-y-3 border-t border-border pt-3">
        <div className="flex overflow-hidden rounded-lg border border-border">
          {WINDOWS.map((opt) => (
            <button
              key={opt.v}
              onClick={() => setWindow(opt.v)}
              className={`flex-1 px-2 py-1 text-xs font-medium transition-colors ${
                window === opt.v
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
              }`}
            >
              {opt.l}
            </button>
          ))}
        </div>

        {histLoading ? (
          <div className="flex items-center justify-center py-10 text-muted-foreground">
            <Loader2 size={16} className="animate-spin" />
          </div>
        ) : history.length === 0 ? (
          <p className="py-8 text-center text-xs text-muted-foreground">
            No history yet — the first points arrive within 5 minutes.
          </p>
        ) : (
          <div className="rounded-lg border border-border p-3">
            <MetricsChart data={history} height={compact ? 200 : 280} />
          </div>
        )}
      </div>

      {showAlerts && <AlertsModal serverId={serverId} onClose={() => setShowAlerts(false)} />}
    </div>
  )
}

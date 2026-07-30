import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Loader2, RefreshCw, Bell, ChevronDown, ChevronRight, Cpu, MemoryStick, HardDrive } from "lucide-react"
import { getMetrics } from "@/api/servers"
import { getMetricsHistory } from "@/api/monitoring"
import CpuChart from "@/components/monitoring/CpuChart"
import RamChart from "@/components/monitoring/RamChart"
import DiskChart from "@/components/monitoring/DiskChart"
import AlertsModal from "@/components/server/AlertsModal"
import type { ServerMetrics as IServerMetrics } from "@/types"

interface Props {
  serverId: string
  /**
   * Whether the history charts start open.
   *
   * Collapsed suits the narrow Overview column, where the charts would be squeezed. But on
   * the Monitoring page — a page that exists for no other reason than to show this — hidden
   * history reads as "we only have live numbers", which is what a real customer reported.
   */
  historyOpen?: boolean
}

const WINDOWS: { v: 6 | 24 | 48 | 168; l: string }[] = [
  { v: 6, l: "6h" },
  { v: 24, l: "24h" },
  { v: 48, l: "48h" },
  { v: 168, l: "7d" },
]

function MetricBar({ label, value, used, total }: { label: string; value: number | null; used?: string; total?: string }) {
  if (value === null) return null
  const color = value > 85 ? "bg-red-500" : value > 60 ? "bg-yellow-500" : "bg-green-500"
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono font-medium text-foreground">
          {value.toFixed(1)}%{used && total ? ` · ${used} / ${total}` : ""}
        </span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-muted">
        <div className={`h-1.5 rounded-full ${color} transition-all`} style={{ width: `${Math.min(value, 100)}%` }} />
      </div>
    </div>
  )
}

function formatUptime(seconds: number | null): string {
  if (seconds === null) return "—"
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

export default function ServerMetrics({ serverId, historyOpen = false }: Props) {
  const [showHistory, setShowHistory] = useState(historyOpen)
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
    enabled: showHistory,
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
          <div className="space-y-3">
            <MetricBar label="CPU" value={data.cpu_percent ?? null} />
            <MetricBar label="RAM" value={data.ram_percent ?? null} used={ramUsed} total={ramTotal} />
            <MetricBar label="Disk" value={data.disk_percent ?? null} used={diskUsed} total={diskTotal} />
          </div>

          <div className="grid grid-cols-2 gap-3 border-t border-border pt-3 text-xs">
            {data.load_1 !== null && (
              <div>
                <p className="text-muted-foreground">Load avg</p>
                <p className="font-mono font-medium text-foreground">
                  {data.load_1?.toFixed(2)} / {data.load_5?.toFixed(2)} / {data.load_15?.toFixed(2)}
                </p>
              </div>
            )}
            <div>
              <p className="text-muted-foreground">Uptime</p>
              <p className="font-mono font-medium text-foreground">{formatUptime(data.uptime_seconds ?? null)}</p>
            </div>
          </div>
        </>
      )}

      {/* History (read-only charts) — collapsed by default to keep the widget compact. */}
      <div className="border-t border-border pt-3">
        <button
          onClick={() => setShowHistory((s) => !s)}
          className="flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          {showHistory ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          History
        </button>

        {showHistory && (
          <div className="mt-3 space-y-3">
            <div className="flex overflow-hidden rounded-lg border border-border">
              {WINDOWS.map((opt) => (
                <button
                  key={opt.v}
                  onClick={() => setWindow(opt.v)}
                  className={`flex-1 px-2 py-1 text-xs font-medium transition-colors ${
                    window === opt.v ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                  }`}
                >
                  {opt.l}
                </button>
              ))}
            </div>

            {histLoading ? (
              <div className="flex items-center justify-center py-6 text-muted-foreground">
                <Loader2 size={16} className="animate-spin" />
              </div>
            ) : history.length === 0 ? (
              <p className="py-4 text-center text-xs text-muted-foreground">
                No history yet — the first points arrive within 5 minutes.
              </p>
            ) : (
              <div className="space-y-3">
                <div className="rounded-lg border border-border p-3">
                  <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-foreground">
                    <Cpu size={13} className="text-emerald-400" /> CPU
                  </div>
                  <CpuChart data={history} />
                </div>
                <div className="rounded-lg border border-border p-3">
                  <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-foreground">
                    <MemoryStick size={13} className="text-blue-400" /> RAM
                  </div>
                  <RamChart data={history} />
                </div>
                <div className="rounded-lg border border-border p-3">
                  <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-foreground">
                    <HardDrive size={13} className="text-violet-400" /> Disk
                  </div>
                  <DiskChart data={history} />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {showAlerts && <AlertsModal serverId={serverId} onClose={() => setShowAlerts(false)} />}
    </div>
  )
}

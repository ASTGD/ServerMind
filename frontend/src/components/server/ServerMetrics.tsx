import { useQuery } from "@tanstack/react-query"
import { getMetrics } from "@/api/servers"
import { Loader2, RefreshCw } from "lucide-react"
import type { ServerMetrics as IServerMetrics } from "@/types"

interface Props {
  serverId: string
}

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

export default function ServerMetrics({ serverId }: Props) {
  const { data, isLoading, isError, refetch, isFetching } = useQuery<IServerMetrics>({
    queryKey: ["metrics", serverId],
    queryFn: () => getMetrics(serverId),
    refetchInterval: 30_000,
    retry: 1,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8 text-muted-foreground">
        <Loader2 size={18} className="animate-spin" />
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="rounded-lg border border-border bg-card p-4 text-sm text-muted-foreground">
        Could not load metrics. Server may be offline.
      </div>
    )
  }

  const ramUsed = data.ram_used_mb ? `${(data.ram_used_mb / 1024).toFixed(1)} GB` : undefined
  const ramTotal = data.ram_total_mb ? `${(data.ram_total_mb / 1024).toFixed(1)} GB` : undefined
  const diskUsed = data.disk_used_gb ? `${data.disk_used_gb.toFixed(1)} GB` : undefined
  const diskTotal = data.disk_total_gb ? `${data.disk_total_gb.toFixed(1)} GB` : undefined

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-foreground">Live Metrics</h3>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="rounded p-1 text-muted-foreground hover:text-foreground transition-colors"
        >
          <RefreshCw size={13} className={isFetching ? "animate-spin" : ""} />
        </button>
      </div>

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
    </div>
  )
}

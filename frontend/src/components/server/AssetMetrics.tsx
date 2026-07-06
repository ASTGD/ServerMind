import { useQuery } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import { getMetrics } from "@/api/servers"
import type { Server } from "@/types"

/** One compact metric row: label · bar · percent, coloured by load. */
function Metric({ label, value }: { label: string; value: number | null }) {
  const v = value ?? 0
  const color = v >= 90 ? "bg-red-500" : v >= 70 ? "bg-amber-500" : "bg-green-500"
  return (
    <div className="flex items-center gap-2">
      <span className="w-7 shrink-0 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
        <div className={`h-full rounded-full transition-all ${color}`} style={{ width: `${Math.min(100, v)}%` }} />
      </div>
      <span className="w-8 shrink-0 text-right text-[10px] tabular-nums text-muted-foreground">{value == null ? "—" : `${Math.round(v)}%`}</span>
    </div>
  )
}

/** At-a-glance stats for an asset card. Online SSH/WinRM boxes show live CPU/RAM/Disk
 *  bars (shares the Dashboard's `["server-metrics", id]` query cache — one fetch per
 *  server, auto-refreshing); offline shows when it was last seen; API-only hosting has
 *  no SSH metrics so it renders nothing. Metric errors degrade to a quiet line. */
export default function AssetMetrics({ server }: { server: Server }) {
  const isOnline = server.status === "online"
  const live = isOnline && (server.connection_type === "ssh" || server.connection_type === "winrm")

  const { data, isLoading, isError } = useQuery({
    queryKey: ["server-metrics", server.id],
    queryFn: () => getMetrics(server.id),
    enabled: live,
    retry: false,
    staleTime: 30_000,
    refetchInterval: live ? 60_000 : false,
  })

  if (!isOnline) {
    let when = "No live stats"
    if (server.last_seen) {
      try {
        when = `Last seen ${formatDistanceToNow(new Date(server.last_seen), { addSuffix: true })}`
      } catch {
        when = "Offline"
      }
    }
    return <p className="text-[11px] text-muted-foreground">{when}</p>
  }
  if (!live) return null
  if (isLoading) return <p className="text-[11px] text-muted-foreground">Loading stats…</p>
  if (isError || !data) return <p className="text-[11px] text-muted-foreground">Stats unavailable</p>

  return (
    <div className="space-y-1.5">
      <Metric label="CPU" value={data.cpu_percent} />
      <Metric label="RAM" value={data.ram_percent} />
      <Metric label="Disk" value={data.disk_percent} />
    </div>
  )
}

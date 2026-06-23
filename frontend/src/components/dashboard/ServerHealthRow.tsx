import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Server as ServerIcon } from "lucide-react"
import { getMetrics } from "@/api/servers"
import type { Server } from "@/types"
import { cn } from "@/lib/utils"

/** A thin CPU/RAM/Disk usage bar, coloured by load. */
function MetricBar({ label, value }: { label: string; value: number | null }) {
  const v = value ?? 0
  const color = v >= 90 ? "bg-red-500" : v >= 70 ? "bg-amber-500" : "bg-green-500"
  return (
    <div className="min-w-0 flex-1">
      <div className="mb-1 flex justify-between text-[11px] text-muted-foreground">
        <span>{label}</span>
        <span className="tabular-nums">{value == null ? "—" : `${Math.round(v)}%`}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${Math.min(100, v)}%` }} />
      </div>
    </div>
  )
}

const dotClass: Record<Server["status"], string> = {
  online: "bg-green-500",
  offline: "bg-red-500",
  unknown: "bg-muted-foreground",
}

/**
 * One server in the fleet list. For online servers it fetches live metrics
 * (auto-refreshing) and shows CPU/RAM/Disk bars; offline/unknown servers just
 * show their status, and metric errors degrade gracefully.
 */
export default function ServerHealthRow({ server }: { server: Server }) {
  const isOnline = server.status === "online"
  const { data, isLoading, isError } = useQuery({
    queryKey: ["server-metrics", server.id],
    queryFn: () => getMetrics(server.id),
    enabled: isOnline,
    retry: false,
    staleTime: 30_000,
    refetchInterval: isOnline ? 30_000 : false,
  })

  return (
    <Link
      to={`/servers/${server.id}`}
      className="flex flex-col gap-3 rounded-lg border border-border bg-card p-4 transition-all hover:border-primary/40 hover:shadow-sm sm:flex-row sm:items-center"
    >
      <div className="flex min-w-0 items-center gap-3 sm:w-56 sm:shrink-0">
        <span className={cn("h-2.5 w-2.5 shrink-0 rounded-full", dotClass[server.status] ?? dotClass.unknown)} />
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted">
          <ServerIcon size={16} className="text-muted-foreground" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">{server.name}</p>
          <p className="truncate text-xs text-muted-foreground">
            {server.os_type ?? server.connection_type} · {server.host}
          </p>
        </div>
      </div>

      <div className="flex flex-1 items-center gap-4">
        {isOnline && isLoading ? (
          <span className="text-xs text-muted-foreground">Loading metrics…</span>
        ) : isOnline && isError ? (
          <span className="text-xs text-muted-foreground">Metrics unavailable</span>
        ) : isOnline && data ? (
          <>
            <MetricBar label="CPU" value={data.cpu_percent} />
            <MetricBar label="RAM" value={data.ram_percent} />
            <MetricBar label="Disk" value={data.disk_percent} />
          </>
        ) : (
          <span className="text-xs capitalize text-muted-foreground">{server.status}</span>
        )}
      </div>
    </Link>
  )
}

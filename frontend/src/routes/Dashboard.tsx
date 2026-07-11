import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Server as ServerIcon, ShieldCheck, AlertTriangle, BookOpen, Plus, ServerOff } from "lucide-react"
import { listServers } from "@/api/servers"
import { listPlaybooks } from "@/api/playbooks"
import { getFleetHealth } from "@/api/fleet"
import type { Server } from "@/types"
import StatCard from "@/components/dashboard/StatCard"
import FleetHealthPanel from "@/components/dashboard/FleetHealthPanel"
import FleetComposition from "@/components/dashboard/FleetComposition"
import QuickActions from "@/components/dashboard/QuickActions"
import RunningTasks from "@/components/dashboard/RunningTasks"
import RecentActivity from "@/components/dashboard/RecentActivity"
import BillingPreview from "@/components/dashboard/BillingPreview"

export default function Dashboard() {
  const { data: servers = [], isLoading } = useQuery<Server[]>({
    queryKey: ["servers"],
    queryFn: listServers,
  })
  const { data: playbooks = [] } = useQuery({
    queryKey: ["playbooks", "all"],
    queryFn: () => listPlaybooks(),
  })
  const { data: fleetHealth } = useQuery({
    queryKey: ["fleet-health"],
    queryFn: getFleetHealth,
    enabled: servers.length > 0,
    refetchInterval: 30_000,
  })

  const online = servers.filter((s) => s.status === "online").length
  const attention = servers.filter((s) => s.status !== "online").length

  const avgScore = useMemo(() => {
    if (!fleetHealth || fleetHealth.servers.length === 0) return null
    const sum = fleetHealth.servers.reduce((acc, s) => acc + s.score, 0)
    return Math.round(sum / fleetHealth.servers.length)
  }, [fleetHealth])

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">Dashboard</h1>
          {servers.length > 0 && (
            <p className="mt-0.5 flex items-center gap-2 text-sm text-muted-foreground">
              <span className={`h-2 w-2 rounded-full ${attention ? "bg-amber-500" : "bg-green-500"}`} />
              {online} of {servers.length} servers healthy
              {attention > 0 && `, ${attention} need${attention === 1 ? "s" : ""} attention`}
            </p>
          )}
        </div>
        <Link
          to="/servers"
          className="flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <Plus size={15} />
          Add server
        </Link>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-[70px] animate-pulse rounded-lg border border-border bg-card" />
          ))}
        </div>
      ) : servers.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-16 text-center">
          <ServerOff size={32} className="mb-3 text-muted-foreground/50" />
          <p className="font-medium text-foreground">No servers yet</p>
          <p className="mt-1 text-sm text-muted-foreground">Add your first server to start managing it with AI.</p>
          <Link
            to="/servers"
            className="mt-4 flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus size={14} />
            Add server
          </Link>
        </div>
      ) : (
        <>
          {/* Running now — slim, auto-hides when nothing is running */}
          <RunningTasks />

          {/* KPI strip */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard icon={ServerIcon} label="Servers" value={servers.length} to="/servers" />
            <StatCard
              icon={ShieldCheck}
              label="Health score"
              value={avgScore ?? "—"}
              tone={avgScore == null ? "default" : avgScore >= 85 ? "green" : avgScore >= 60 ? "amber" : "red"}
            />
            <StatCard
              icon={AlertTriangle}
              label="Alerts"
              value={attention}
              tone={attention ? "amber" : "default"}
              to="/servers"
            />
            <StatCard icon={BookOpen} label="Playbooks" value={playbooks.length} to="/playbooks" />
          </div>

          {/* Bento grid */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.3fr_1fr]">
            <FleetHealthPanel health={fleetHealth} servers={servers} />
            <RecentActivity servers={servers} />
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.3fr_1fr]">
            <FleetComposition servers={servers} />
            <QuickActions />
          </div>

          <BillingPreview />
        </>
      )}
    </div>
  )
}

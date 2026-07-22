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
import SubscriptionCard from "@/components/dashboard/SubscriptionCard"
import { SectionHeader, EmptyState, buttonVariants } from "@/components/ui"
import { cn } from "@/lib/utils"

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
      <SectionHeader
        title="Dashboard"
        description={
          servers.length > 0 ? (
            <span className="flex items-center gap-2">
              <span className={cn("h-2 w-2 rounded-full", attention ? "bg-warning" : "bg-success")} />
              {online} of {servers.length} servers healthy
              {attention > 0 && `, ${attention} need${attention === 1 ? "s" : ""} attention`}
            </span>
          ) : undefined
        }
        actions={
          <Link to="/servers" className={buttonVariants({ size: "sm" })}>
            <Plus size={15} />
            Add server
          </Link>
        }
      />

      {isLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-[74px] animate-pulse rounded-xl border border-border bg-card" />
          ))}
        </div>
      ) : servers.length === 0 ? (
        <EmptyState
          icon={ServerOff}
          title="No servers yet"
          description="Add your first server to start managing it with AI."
          action={
            <Link to="/servers" className={buttonVariants({ size: "sm" })}>
              <Plus size={14} />
              Add server
            </Link>
          }
        />
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

          {/* Bento — fleet health (the centerpiece) beside the subscription summary,
              then composition beside quick actions. Recent activity lives on /logs. */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.3fr_1fr]">
            <FleetHealthPanel health={fleetHealth} servers={servers} />
            <SubscriptionCard />
            <FleetComposition servers={servers} />
            <QuickActions />
          </div>
        </>
      )}
    </div>
  )
}

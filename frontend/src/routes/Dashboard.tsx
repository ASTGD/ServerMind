import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Server as ServerIcon, Activity, AlertTriangle, BookOpen, Plus, ServerOff } from "lucide-react"
import { listServers } from "@/api/servers"
import { listPlaybooks } from "@/api/playbooks"
import { useAuthStore } from "@/store/authStore"
import type { Server } from "@/types"
import StatCard from "@/components/dashboard/StatCard"
import ServerHealthRow from "@/components/dashboard/ServerHealthRow"
import QuickActions from "@/components/dashboard/QuickActions"

const CONN_LABELS: Record<string, string> = {
  ssh: "Linux / SSH",
  winrm: "Windows / WinRM",
  hosting: "Hosting panel",
}

export default function Dashboard() {
  const user = useAuthStore((s) => s.user)
  const firstName = user?.name?.split(" ")[0] ?? "there"

  const { data: servers = [], isLoading } = useQuery<Server[]>({
    queryKey: ["servers"],
    queryFn: listServers,
  })
  const { data: playbooks = [] } = useQuery({
    queryKey: ["playbooks", "all"],
    queryFn: () => listPlaybooks(),
  })

  const online = servers.filter((s) => s.status === "online").length
  const attention = servers.filter((s) => s.status !== "online").length

  const byConn = servers.reduce<Record<string, number>>((acc, s) => {
    acc[s.connection_type] = (acc[s.connection_type] ?? 0) + 1
    return acc
  }, {})

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Welcome back, {firstName}</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">Here's how your fleet is doing today.</p>
        </div>
        <Link
          to="/servers"
          className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <Plus size={15} />
          Add Server
        </Link>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          icon={ServerIcon}
          label="Total servers"
          value={servers.length}
          to="/servers"
          loading={isLoading}
        />
        <StatCard
          icon={Activity}
          label="Online"
          value={online}
          tone="green"
          sub={servers.length ? `${Math.round((online / servers.length) * 100)}% of fleet` : undefined}
          loading={isLoading}
        />
        <StatCard
          icon={AlertTriangle}
          label="Needs attention"
          value={attention}
          tone={attention ? "amber" : "default"}
          to="/servers"
          loading={isLoading}
        />
        <StatCard
          icon={BookOpen}
          label="Playbooks"
          value={playbooks.length}
          tone="blue"
          to="/playbooks"
          sub="ready to run"
        />
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Fleet */}
        <div className="space-y-3 lg:col-span-2">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-foreground">Your fleet</h2>
            <Link to="/servers" className="text-xs text-muted-foreground hover:text-foreground">
              View all
            </Link>
          </div>

          {isLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-20 animate-pulse rounded-lg border border-border bg-card" />
              ))}
            </div>
          ) : servers.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-16 text-center">
              <ServerOff size={32} className="mb-3 text-muted-foreground/50" />
              <p className="font-medium text-foreground">No servers yet</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Add your first server to start managing it with AI.
              </p>
              <Link
                to="/servers"
                className="mt-4 flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
              >
                <Plus size={14} />
                Add Server
              </Link>
            </div>
          ) : (
            <div className="space-y-3">
              {servers.map((s) => (
                <ServerHealthRow key={s.id} server={s} />
              ))}
            </div>
          )}
        </div>

        {/* Sidebar column */}
        <div className="space-y-6">
          <QuickActions />

          {servers.length > 0 && (
            <div className="rounded-xl border border-border bg-card p-5">
              <h2 className="text-sm font-semibold text-foreground">Fleet breakdown</h2>
              <div className="mt-4 space-y-3">
                {Object.entries(byConn).map(([conn, count]) => {
                  const pct = Math.round((count / servers.length) * 100)
                  return (
                    <div key={conn}>
                      <div className="mb-1 flex justify-between text-xs">
                        <span className="text-foreground">{CONN_LABELS[conn] ?? conn}</span>
                        <span className="tabular-nums text-muted-foreground">{count}</span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                        <div className="h-full rounded-full bg-primary/70" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

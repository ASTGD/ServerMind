import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Activity, Loader2, Plus, RefreshCw, Trash2, CircleCheck, CircleAlert,
  CircleDashed, RotateCw, TriangleAlert,
} from "lucide-react"
import {
  listForServer, discoverServices, watchService, updateServiceMonitor,
  resetServiceMonitor, deleteServiceMonitor,
  type ServiceMonitor, type DiscoveredService,
} from "@/api/serviceMonitors"
import { Button, EmptyState } from "@/components/ui"
import { cn } from "@/lib/utils"

function StatusIcon({ m }: { m: ServiceMonitor }) {
  if (m.gave_up) return <TriangleAlert size={15} className="shrink-0 text-red-600 dark:text-red-400" />
  if (m.status === "up") return <CircleCheck size={15} className="shrink-0 text-emerald-600 dark:text-emerald-400" />
  if (m.status === "down") return <CircleAlert size={15} className="shrink-0 text-red-600 dark:text-red-400" />
  return <CircleDashed size={15} className="shrink-0 text-muted-foreground" />
}

function MonitorRow({ m, serverId }: { m: ServiceMonitor; serverId: string }) {
  const qc = useQueryClient()
  const invalidate = () => qc.invalidateQueries({ queryKey: ["service-monitors", serverId] })

  const toggleRestart = useMutation({
    mutationFn: () => updateServiceMonitor(m.id, {
      unit: m.unit, label: m.label, failure_threshold: m.failure_threshold,
      auto_restart: !m.auto_restart, max_restarts: m.max_restarts,
      restart_window_seconds: m.restart_window_seconds, is_active: m.is_active,
    }),
    onSuccess: invalidate,
  })
  const reset = useMutation({ mutationFn: () => resetServiceMonitor(m.id), onSuccess: invalidate })
  const remove = useMutation({ mutationFn: () => deleteServiceMonitor(m.id), onSuccess: invalidate })

  return (
    <li className={cn(
      "rounded-xl border bg-card p-3",
      m.gave_up ? "border-red-500/40 bg-red-500/[0.04]"
        : m.status === "down" ? "border-red-500/30" : "border-border",
    )}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 gap-2.5">
          <span className="mt-0.5"><StatusIcon m={m} /></span>
          <div className="min-w-0">
            <p className="flex flex-wrap items-center gap-2">
              <span className="text-[14px] font-medium text-foreground">{m.label}</span>
              <code className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                {m.unit}
              </code>
              {m.auto_restart && !m.gave_up && (
                <span className="flex items-center gap-1 rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                  <RotateCw size={9} /> auto-restart
                </span>
              )}
            </p>
            {/* When we've given up, that IS the message — a crash loop that keeps being
                restarted looks healthier than it is, so it has to be said plainly. */}
            {m.gave_up ? (
              <p className="mt-1 text-[12px] text-red-600 dark:text-red-400">
                Keeps stopping — ServerAlly stopped restarting it. {m.last_error}
              </p>
            ) : m.last_error ? (
              <p className="mt-1 text-[12px] text-muted-foreground">{m.last_error}</p>
            ) : (
              <p className="mt-1 text-[11.5px] text-muted-foreground">
                {m.status === "up" ? "Running" : "Not checked yet"}
                {m.restart_count > 0 && ` · restarted ${m.restart_count}×`}
              </p>
            )}
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {m.gave_up && (
            <Button size="sm" variant="outline" disabled={reset.isPending}
              onClick={() => reset.mutate()}>
              {reset.isPending ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
              Try again
            </Button>
          )}
          <Button size="sm" variant="ghost" disabled={toggleRestart.isPending}
            title={m.auto_restart
              ? "Stop restarting this automatically"
              : "Let Ally restart this automatically when it stops"}
            onClick={() => toggleRestart.mutate()}>
            <RotateCw size={13} className={m.auto_restart ? "text-primary" : ""} />
          </Button>
          <Button size="sm" variant="ghost" disabled={remove.isPending}
            onClick={() => remove.mutate()}>
            <Trash2 size={13} />
          </Button>
        </div>
      </div>
    </li>
  )
}

/**
 * Services — watch the things that keep a server useful.
 *
 * Alerts could only ever fire on CPU, RAM and disk, so a database could die on an idle
 * server and nothing was said. This watches named services and, if allowed, restarts
 * them — with a hard cap, because an auto-healer with no bound just hammers a crashing
 * box and hides the real fault.
 */
export default function ServicesPanel({ serverId }: { serverId: string }) {
  const qc = useQueryClient()
  const [picking, setPicking] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ["service-monitors", serverId],
    queryFn: () => listForServer(serverId),
    refetchInterval: 30_000,
  })

  const discover = useQuery({
    queryKey: ["service-discover", serverId],
    queryFn: () => discoverServices(serverId),
    enabled: picking,
  })

  const add = useMutation({
    mutationFn: (s: DiscoveredService) =>
      watchService(serverId, { unit: s.unit, label: s.label }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["service-monitors", serverId] })
      qc.invalidateQueries({ queryKey: ["service-discover", serverId] })
    },
  })

  const monitors = data?.monitors ?? []
  const down = monitors.filter((m) => m.status === "down" || m.gave_up).length

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-h3 text-foreground">
            <Activity className="h-4 w-4 text-primary" /> Services
          </h2>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            We check every 2 minutes and tell you when one stops.
            {down > 0 && (
              <span className="ml-1 font-medium text-red-600 dark:text-red-400">
                {down} need{down === 1 ? "s" : ""} attention.
              </span>
            )}
          </p>
        </div>
        <Button size="sm" variant={picking ? "outline" : "primary"}
          onClick={() => setPicking((p) => !p)}>
          <Plus size={14} /> {picking ? "Done" : "Watch a service"}
        </Button>
      </div>

      {picking && (
        <div className="mb-3 rounded-xl border border-dashed border-border bg-muted/30 p-3">
          {discover.isLoading ? (
            <p className="text-[12.5px] text-muted-foreground">
              <Loader2 size={13} className="mr-1 inline animate-spin" />
              Looking at what&rsquo;s installed…
            </p>
          ) : discover.isError ? (
            <p className="text-[12.5px] text-red-600 dark:text-red-400">
              Couldn&rsquo;t read the services on this server.
            </p>
          ) : (
            <>
              <p className="mb-2 text-[11.5px] text-muted-foreground">
                Found on this server — nothing was changed.
              </p>
              <div className="flex flex-wrap gap-1.5">
                {(discover.data?.services ?? []).map((s) => (
                  <Button key={s.unit} size="sm" variant="outline"
                    disabled={s.watched || add.isPending}
                    onClick={() => add.mutate(s)}>
                    <span className={cn("mr-1 h-1.5 w-1.5 rounded-full",
                      s.running ? "bg-emerald-500" : "bg-red-500")} />
                    {s.label}{s.watched && " ✓"}
                  </Button>
                ))}
                {(discover.data?.services ?? []).length === 0 && (
                  <p className="text-[12.5px] text-muted-foreground">
                    No familiar services found on this server.
                  </p>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {isLoading ? (
        <p className="py-6 text-center text-sm text-muted-foreground">Loading…</p>
      ) : monitors.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No services watched yet"
          description="Pick a service and we'll tell you if it ever stops — and restart it for you if you want."
        />
      ) : (
        <ul className="space-y-2">
          {monitors.map((m) => <MonitorRow key={m.id} m={m} serverId={serverId} />)}
        </ul>
      )}
    </div>
  )
}

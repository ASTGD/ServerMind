import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { formatDistanceToNow } from "date-fns"
import { CalendarClock, CheckCircle2, XCircle, Pause, Clock } from "lucide-react"
import { listSchedules } from "@/api/scheduler"

export default function SchedulerWidget({ serverId }: { serverId: string }) {
  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ["schedules", serverId],
    queryFn: () => listSchedules(serverId),
  })

  const active = tasks.filter((t) => t.is_active)
  const upcoming = [...active]
    .filter((t) => t.next_run)
    .sort((a, b) => (a.next_run! > b.next_run! ? 1 : -1))
    .slice(0, 3)

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-sm font-medium text-foreground">
          <CalendarClock size={14} /> Scheduler
        </h3>
        <Link to={`/servers/${serverId}/scheduler`} className="text-xs text-primary hover:underline">
          Manage
        </Link>
      </div>

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : tasks.length === 0 ? (
        <p className="text-xs text-muted-foreground">No tasks scheduled.</p>
      ) : (
        <div className="space-y-2">
          {/* Summary row */}
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>
              <span className="font-medium text-foreground">{active.length}</span> active
            </span>
            {tasks.length - active.length > 0 && (
              <>
                <span className="text-border">·</span>
                <span>{tasks.length - active.length} paused</span>
              </>
            )}
          </div>

          {/* Upcoming tasks */}
          {upcoming.length > 0 && (
            <div className="space-y-1.5 pt-0.5">
              {upcoming.map((task) => {
                const statusIcon =
                  task.last_status === "success" ? (
                    <CheckCircle2 size={12} className="text-emerald-500 shrink-0" />
                  ) : task.last_status === "failed" ? (
                    <XCircle size={12} className="text-red-500 shrink-0" />
                  ) : task.is_active ? (
                    <Clock size={12} className="text-muted-foreground shrink-0" />
                  ) : (
                    <Pause size={12} className="text-muted-foreground shrink-0" />
                  )

                return (
                  <div key={task.id} className="flex items-center gap-2 text-xs">
                    {statusIcon}
                    <span className="min-w-0 flex-1 truncate text-foreground">{task.title}</span>
                    <span className="shrink-0 text-muted-foreground">
                      {formatDistanceToNow(new Date(task.next_run!), { addSuffix: true })}
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

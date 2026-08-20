import { useQuery } from "@tanstack/react-query"
import { Loader2, Check, Ban, Square, Clock } from "lucide-react"
import { Link, useParams } from "react-router-dom"
import { listRuns, type BlueprintRun } from "@/api/blueprints"
import RunScreen from "@/components/activity/RunScreen"
import { EmptyState } from "@/components/ui"

/** Activity — the ONE place long jobs are read, running first then finished.
 * Three signs (top-bar pill, server strip, site strip) all point here; this is the
 * destination. See docs/BLUEPRINTS-PLAN.md §9. */

function RunRow({ run }: { run: BlueprintRun }) {
  const icon =
    run.status === "running" ? <Loader2 size={15} className="animate-spin text-primary" />
    : run.status === "done" && run.left_for_you.length ? <Clock size={15} className="text-amber-600 dark:text-amber-400" />
    : run.status === "done" ? <Check size={15} className="text-emerald-600 dark:text-emerald-400" />
    : run.status === "stopped" ? <Square size={15} className="text-muted-foreground" />
    : <Ban size={15} className="text-red-600 dark:text-red-400" />
  const when = run.created_at ? new Date(run.created_at).toLocaleString() : ""
  return (
    <Link to={`/activity/${run.id}`}
      className="flex items-center gap-3 border-b border-border px-4 py-3 last:border-0 hover:bg-muted/40">
      {icon}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm">{run.title}</p>
        <p className="text-xs text-muted-foreground">
          {run.server_name ?? ""}{run.server_name ? " · " : ""}
          {run.status === "running"
            ? `step ${Math.min(run.current + 1, run.steps_total)} of ${run.steps_total}`
            : `${run.steps_done} of ${run.steps_total} steps`}
          {run.status === "done" && run.left_for_you.length ? " · waiting for you" : ""}
          {" · "}{when}
        </p>
      </div>
    </Link>
  )
}

export default function ActivityPage() {
  const { runId } = useParams()
  const { data: runs = [] } = useQuery({
    queryKey: ["blueprint-runs"],
    queryFn: () => listRuns(),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((r) => r.status === "running") ? 3000 : 15000,
  })

  if (runId) {
    return (
      <div className="mx-auto max-w-3xl space-y-4">
        <Link to="/activity" className="text-sm text-muted-foreground hover:text-foreground">← Activity</Link>
        <RunScreen runId={runId} />
      </div>
    )
  }

  const running = runs.filter((r) => r.status === "running")
  const finished = runs.filter((r) => r.status !== "running")

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-h1">Activity</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Long jobs on your servers — what is running now, and what already ran.
        </p>
      </div>
      {runs.length === 0 && (
        <EmptyState title="Nothing has run yet"
          description="Start a job from a server's page — like setting up a website — and it shows here, step by step." />
      )}
      {running.length > 0 && (
        <div>
          <p className="mb-2 text-[13px] font-medium text-muted-foreground">Running now</p>
          <div className="space-y-4">
            {running.map((r) => <RunScreen key={r.id} runId={r.id} />)}
          </div>
        </div>
      )}
      {finished.length > 0 && (
        <div>
          <p className="mb-2 text-[13px] font-medium text-muted-foreground">Finished</p>
          <div className="overflow-hidden rounded-xl border border-border bg-card">
            {finished.map((r) => <RunRow key={r.id} run={r} />)}
          </div>
        </div>
      )}
    </div>
  )
}

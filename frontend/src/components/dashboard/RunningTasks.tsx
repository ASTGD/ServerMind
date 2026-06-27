import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Loader2, ChevronRight } from "lucide-react"
import { formatDistanceToNow } from "date-fns"
import { getAllActiveRuns, type ActiveRunSummary } from "@/api/servers"
import RunLogModal from "@/components/playbooks/RunLogModal"

/** Dashboard "control tower" — everything currently running across all servers,
 * click-through to the live log (Update 17, Phase 3). Hidden when nothing runs. */
export default function RunningTasks() {
  const [open, setOpen] = useState<ActiveRunSummary | null>(null)
  const { data: runs = [] } = useQuery({
    queryKey: ["active-runs-all"],
    queryFn: getAllActiveRuns,
    refetchInterval: 8000,
    refetchOnWindowFocus: true,
  })

  if (runs.length === 0) return null

  return (
    <>
      <div className="rounded-xl border border-primary/20 bg-primary/5 p-5">
        <div className="flex items-center gap-2">
          <Loader2 size={15} className="animate-spin text-primary" />
          <h2 className="text-sm font-semibold text-foreground">
            Running now <span className="text-muted-foreground">({runs.length})</span>
          </h2>
        </div>
        <div className="mt-3 space-y-2">
          {runs.map((r) => (
            <button
              key={r.id}
              onClick={() => setOpen(r)}
              className="flex w-full items-center justify-between gap-3 rounded-lg border border-border bg-card px-3 py-2.5 text-left transition-colors hover:border-primary/40"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-foreground">{r.title}</p>
                <p className="truncate text-xs text-muted-foreground">
                  on {r.server_name}
                  {r.started_at
                    ? ` · started ${formatDistanceToNow(new Date(r.started_at), { addSuffix: true })}`
                    : ""}
                </p>
              </div>
              <ChevronRight size={16} className="shrink-0 text-muted-foreground" />
            </button>
          ))}
        </div>
      </div>

      {open && (
        <RunLogModal
          serverId={open.server_id}
          runId={open.id}
          title={open.title}
          serverName={open.server_name}
          onClose={() => setOpen(null)}
        />
      )}
    </>
  )
}

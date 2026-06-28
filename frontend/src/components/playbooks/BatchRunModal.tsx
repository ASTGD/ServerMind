import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { X, Loader2, CheckCircle2, XCircle, Clock, Ban, ChevronRight } from "lucide-react"
import { getRunsStatus, type FleetRun, type FleetSkip } from "@/api/playbooks"
import RunLogModal from "./RunLogModal"

const TERMINAL = ["success", "failed", "stalled", "cancelled", "partial", "blocked"]

function statusBadge(status: string | undefined) {
  switch (status) {
    case "success":
      return <span className="flex items-center gap-1 text-green-500"><CheckCircle2 size={13} /> Done</span>
    case "failed":
      return <span className="flex items-center gap-1 text-red-500"><XCircle size={13} /> Failed</span>
    case "stalled":
      return <span className="flex items-center gap-1 text-orange-500"><Clock size={13} /> Stopped</span>
    case "cancelled":
      return <span className="flex items-center gap-1 text-amber-500"><Ban size={13} /> Cancelled</span>
    default:
      return <span className="flex items-center gap-1 text-primary"><Loader2 size={13} className="animate-spin" /> Installing…</span>
  }
}

interface Props {
  runs: FleetRun[]
  skipped?: FleetSkip[]
  playbookTitle: string
  onClose: () => void
}

/** Fleet-install batch view — one row per server with live status and
 * click-through to each server's live log (Update 18). Servers already running
 * this playbook are listed as skipped (no duplicate install — Update 19 #2). */
export default function BatchRunModal({ runs, skipped = [], playbookTitle, onClose }: Props) {
  const [logRun, setLogRun] = useState<FleetRun | null>(null)
  const runIds = runs.map((r) => r.run_id)

  const { data: statuses = [] } = useQuery({
    queryKey: ["batch-status", runIds.join(",")],
    queryFn: () => getRunsStatus(runIds),
    refetchInterval: 5000,
    refetchOnWindowFocus: true,
  })
  const statusMap: Record<string, string> = Object.fromEntries(statuses.map((s) => [s.id, s.status]))
  const reasonMap: Record<string, string | null | undefined> = Object.fromEntries(
    statuses.map((s) => [s.id, s.failure_reason]),
  )
  const done = runs.filter((r) => TERMINAL.includes(statusMap[r.run_id] ?? "")).length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h2 className="font-semibold text-foreground">{playbookTitle}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Running on {runs.length} servers · {done} of {runs.length} done
              {skipped.length > 0 ? ` · ${skipped.length} skipped` : ""}
            </p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-2 overflow-y-auto px-6 py-4">
          {runs.map((r) => {
            const st = statusMap[r.run_id]
            const reason = reasonMap[r.run_id]
            const failed = st === "failed" || st === "stalled"
            return (
              <button
                key={r.run_id}
                onClick={() => setLogRun(r)}
                className="flex w-full flex-col gap-1 rounded-lg border border-border bg-background px-3 py-2.5 text-left transition-colors hover:border-primary/40"
              >
                <div className="flex w-full items-center justify-between gap-3">
                  <p className="min-w-0 truncate text-sm font-medium text-foreground">{r.server_name}</p>
                  <div className="flex shrink-0 items-center gap-2 text-xs font-medium">
                    {statusBadge(st)}
                    <ChevronRight size={14} className="text-muted-foreground" />
                  </div>
                </div>
                {failed && (
                  <p
                    className={`pl-0.5 text-xs leading-snug ${st === "stalled" ? "text-orange-500/90" : "text-red-500/90"}`}
                  >
                    {reason ?? "Failed — open to view the log."}
                  </p>
                )}
              </button>
            )
          })}
          {skipped.map((s) => (
            <div
              key={s.server_id}
              className="flex w-full items-center justify-between gap-3 rounded-lg border border-dashed border-border bg-background px-3 py-2.5 opacity-80"
            >
              <p className="min-w-0 truncate text-sm font-medium text-foreground">{s.server_name}</p>
              <span className="flex shrink-0 items-center gap-1 text-xs font-medium text-amber-500">
                <Clock size={13} /> Already running — skipped
              </span>
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-border px-6 py-4">
          <p className="text-xs text-muted-foreground">
            Installs run in the background — close this any time; track them in "Running now" and the bell.
          </p>
          <button
            onClick={onClose}
            className="shrink-0 rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted/50"
          >
            Close
          </button>
        </div>
      </div>

      {logRun && (
        <RunLogModal
          serverId={logRun.server_id}
          runId={logRun.run_id}
          title={playbookTitle}
          serverName={logRun.server_name}
          onClose={() => setLogRun(null)}
        />
      )}
    </div>
  )
}

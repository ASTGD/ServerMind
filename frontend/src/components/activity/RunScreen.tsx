import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Activity, AlertTriangle, Ban, Check, CircleDashed, Clock, Eye, Loader2,
  Lock, Package, ShieldCheck, Square, UploadCloud, Globe,
} from "lucide-react"
import { getRun, stopRun, type BlueprintStep } from "@/api/blueprints"
import { Button } from "@/components/ui"

/** The live screen for one blueprint run — the checklist that fills in.
 *
 * The design rules it carries (docs/BLUEPRINTS-PLAN.md §9):
 * - every step keeps its RESULT once done, not just a tick;
 * - the running step shows a live line so a four-minute install reads as movement;
 * - a WAITING step is amber, plainly "waiting for you" — never red;
 * - the bar only exists because the plan's length is known.
 */

const STEP_ICON: Record<string, typeof Eye> = {
  look: Eye, prepare: Package, create: Globe, confirm: Check,
  https: Lock, watch: Activity, backup: UploadCloud, safety: ShieldCheck,
}

function StepMark({ state }: { state: BlueprintStep["state"] }) {
  if (state === "done") return <Check size={16} className="shrink-0 text-emerald-600 dark:text-emerald-400" />
  if (state === "running") return <Loader2 size={16} className="shrink-0 animate-spin text-primary" />
  if (state === "failed") return <Ban size={16} className="shrink-0 text-red-600 dark:text-red-400" />
  if (state === "waiting") return <Clock size={16} className="shrink-0 text-amber-600 dark:text-amber-400" />
  if (state === "skipped") return <CircleDashed size={16} className="shrink-0 text-muted-foreground" />
  return <CircleDashed size={16} className="shrink-0 text-muted-foreground/50" />
}

function StepRow({ step, active }: { step: BlueprintStep; active: boolean }) {
  const Icon = STEP_ICON[step.key] ?? CircleDashed
  const noteTone =
    step.state === "failed" ? "text-red-600 dark:text-red-400"
    : step.state === "waiting" ? "text-amber-700 dark:text-amber-400"
    : "text-muted-foreground"
  return (
    <div className={`flex items-start gap-3 px-5 py-2.5 ${active ? "bg-primary/5" : ""}`}>
      <span className="mt-0.5"><StepMark state={step.state} /></span>
      <div className="min-w-0 flex-1">
        <p className={`flex items-center gap-2 text-sm ${step.state === "pending" ? "text-muted-foreground/70" : "text-foreground"}`}>
          <Icon size={14} className="shrink-0 text-muted-foreground" />
          {step.label}
          {step.state === "skipped" && <span className="text-xs text-muted-foreground">skipped</span>}
        </p>
        {step.note && <p className={`mt-0.5 text-[13px] ${noteTone}`}>{step.note}</p>}
      </div>
    </div>
  )
}

export default function RunScreen({ runId }: { runId: string }) {
  const qc = useQueryClient()
  const { data: run } = useQuery({
    queryKey: ["blueprint-run", runId],
    queryFn: () => getRun(runId),
    // Poll only while it is alive; a finished run is a record, not a feed.
    refetchInterval: (q) => (q.state.data?.status === "running" ? 2000 : false),
  })
  const stop = useMutation({
    mutationFn: () => stopRun(runId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["blueprint-run", runId] }),
  })

  if (!run) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>

  const pct = run.steps_total ? Math.round((run.steps_done / run.steps_total) * 100) : 0
  const running = run.status === "running"
  const tone =
    run.status === "failed" ? "border-red-300 bg-red-50 text-red-800 dark:border-red-800 dark:bg-red-950/40 dark:text-red-300"
    : run.status === "stopped" ? "border-border bg-muted text-muted-foreground"
    : run.left_for_you.length
      ? "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-300"
      : "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="border-b border-border px-5 py-4">
        <div className="flex items-start gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-[15px] font-medium">{run.title}</p>
            <p className="mt-0.5 text-[13px] text-muted-foreground">
              {run.server_name ?? "server"}
              {run.inputs.site_type ? ` · ${run.inputs.site_type}` : ""}
              {running ? ` · step ${Math.min(run.current + 1, run.steps_total)} of ${run.steps_total}` : ""}
            </p>
          </div>
          {running && (
            <Button variant="outline" size="sm" onClick={() => stop.mutate()} disabled={stop.isPending}
              title="Stops what comes next. It cannot undo steps that already ran.">
              <Square size={13} className="mr-1.5" /> Stop
            </Button>
          )}
        </div>
        <div className="mt-3 flex items-center gap-3">
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${pct}%` }} />
          </div>
          <span className="text-[13px] tabular-nums text-muted-foreground">{run.steps_done} of {run.steps_total}</span>
        </div>
      </div>

      <div className="py-1.5">
        {run.steps.map((s, i) => (
          <StepRow key={s.key} step={s} active={running && i === run.current} />
        ))}
      </div>

      {run.message && run.status !== "running" && (
        <div className={`mx-5 mb-4 rounded-lg border px-4 py-3 text-sm ${tone}`}>{run.message}</div>
      )}

      {run.left_for_you.length > 0 && (
        <div className="border-t border-border px-5 py-3.5">
          <p className="mb-1.5 flex items-center gap-1.5 text-[13px] font-medium text-amber-700 dark:text-amber-400">
            <AlertTriangle size={13} /> Left for you
          </p>
          {run.left_for_you.map((item) => (
            <p key={item} className="text-[13px] leading-relaxed text-muted-foreground">{item}</p>
          ))}
        </div>
      )}

      {run.found.length > 0 && (
        <div className="border-t border-border px-5 py-3.5">
          <p className="mb-1.5 text-[13px] font-medium text-muted-foreground">What we found</p>
          {run.found.map((f) => (
            <p key={f} className="text-[13px] leading-relaxed text-muted-foreground">· {f}</p>
          ))}
        </div>
      )}
    </div>
  )
}

import { useState } from "react"
import {
  Rocket, CheckCircle2, XCircle, Loader2, Square, ChevronDown, ChevronRight,
  AlertTriangle, Flag, Hand,
} from "lucide-react"

export interface MissionStep {
  index: number
  cmd: string
  description: string
  riskLevel?: string
  needsApproval?: boolean
  running: boolean
  exitCode?: number
  outputTail?: string
  note?: string
  /** Which server this step ran on (cross-server missions, Stage 2). */
  serverName?: string
}

export interface MissionState {
  goal: string
  status: "running" | "complete" | "blocked" | "failed" | "stopped"
  steps: MissionStep[]
  summary?: string
  stepsUsed?: number
}

function StepRow({ step }: { step: MissionStep }) {
  const [open, setOpen] = useState(false)
  const icon = step.running ? (
    <Loader2 size={13} className="shrink-0 animate-spin text-indigo-500" />
  ) : step.exitCode === 0 ? (
    <CheckCircle2 size={13} className="shrink-0 text-emerald-500" />
  ) : (
    <XCircle size={13} className="shrink-0 text-red-500" />
  )
  const hasDetail = Boolean(step.outputTail || step.note)
  return (
    <div className="text-xs">
      <button
        onClick={() => hasDetail && setOpen((o) => !o)}
        className={`flex w-full items-start gap-1.5 text-left ${hasDetail ? "cursor-pointer" : "cursor-default"}`}
      >
        <span className="mt-0.5">{icon}</span>
        <span className="min-w-0 flex-1">
          {step.serverName && (
            <span className="mr-1.5 rounded bg-indigo-500/10 px-1 py-px text-[10px] font-medium text-indigo-600 dark:text-indigo-400">
              {step.serverName}
            </span>
          )}
          <span className="text-foreground">{step.description || step.cmd}</span>
          {step.note && <span className="ml-1 text-amber-600 dark:text-amber-400">({step.note})</span>}
        </span>
        {hasDetail && (
          <span className="mt-0.5 shrink-0 text-muted-foreground">
            {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </span>
        )}
      </button>
      {open && (
        <div className="ml-5 mt-1 space-y-1">
          <pre className="overflow-x-auto rounded bg-[#0d0d0d] px-2 py-1 font-mono text-[11px] text-zinc-300">$ {step.cmd}</pre>
          {step.outputTail && (
            <pre className="max-h-36 overflow-auto whitespace-pre-wrap break-all rounded bg-[#0d0d0d] px-2 py-1 font-mono text-[11px] text-zinc-400">
              {step.outputTail}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}

/** Live mission timeline — one row per step, a Stop button while running, and a final
 *  banner (done / blocked / failed / stopped). */
export default function MissionProgress({
  mission,
  onStop,
}: {
  mission: MissionState
  onStop: () => void
}) {
  const running = mission.status === "running"
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <Rocket size={15} className="shrink-0 text-primary" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{mission.goal}</span>
        {running ? (
          <button
            onClick={onStop}
            className="flex shrink-0 items-center gap-1 rounded-md bg-red-500/90 px-2 py-1 text-[11px] font-medium text-white hover:bg-red-500"
          >
            <Square size={10} /> Stop
          </button>
        ) : (
          <span className="shrink-0 text-[11px] text-muted-foreground">
            {mission.steps.length} step{mission.steps.length === 1 ? "" : "s"}
          </span>
        )}
      </div>

      <div className="space-y-1.5 px-3 py-2.5">
        {mission.steps.length === 0 && running && (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 size={12} className="animate-spin" /> Planning the first step…
          </p>
        )}
        {mission.steps.map((s) => (
          <StepRow key={s.index} step={s} />
        ))}
        {running && mission.steps.length > 0 && mission.steps.every((s) => !s.running) && (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 size={12} className="animate-spin" /> Deciding the next step…
          </p>
        )}
      </div>

      {mission.status !== "running" && (
        <div
          className={`flex items-start gap-2 border-t px-3 py-2 text-xs ${
            mission.status === "complete"
              ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
              : mission.status === "blocked"
                ? "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-400"
                : "border-red-500/20 bg-red-500/10 text-red-600 dark:text-red-400"
          }`}
        >
          {mission.status === "complete" ? (
            <Flag size={13} className="mt-0.5 shrink-0" />
          ) : mission.status === "blocked" ? (
            <Hand size={13} className="mt-0.5 shrink-0" />
          ) : (
            <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          )}
          <span>
            {mission.status === "stopped"
              ? "Mission stopped."
              : mission.summary || `Mission ${mission.status}.`}
          </span>
        </div>
      )}
    </div>
  )
}

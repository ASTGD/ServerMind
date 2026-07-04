import { useState } from "react"
import {
  Rocket, CheckCircle2, XCircle, Loader2, Square, ChevronDown, ChevronRight,
  AlertTriangle, Flag, Hand, ShieldCheck, ShieldAlert, Clock,
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
  /** A read-only check the verification gate ran to prove the goal (not an executor step). */
  verifying?: boolean
  /** A `wait` step — polling a long-running job; doesn't consume the step budget. */
  waiting?: boolean
}

export interface MissionState {
  goal: string
  status: "running" | "complete" | "blocked" | "failed" | "stopped"
  steps: MissionStep[]
  summary?: string
  stepsUsed?: number
  /** Verification gate outcome on a completed mission: true = goal proven, false =
   *  finished but the goal could NOT be confirmed (honest, not a success). */
  verified?: boolean
  /** What the verifier confirmed (verified) or what's still unproven (caveat). */
  verification?: string
}

function StepRow({ step }: { step: MissionStep }) {
  const [open, setOpen] = useState(false)
  const icon = step.running ? (
    step.waiting ? (
      <Clock size={13} className="shrink-0 animate-pulse text-amber-500" />
    ) : (
      <Loader2 size={13} className="shrink-0 animate-spin text-indigo-500" />
    )
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
          {step.verifying && (
            <span className="mr-1.5 inline-flex items-center gap-0.5 rounded bg-violet-500/10 px-1 py-px text-[10px] font-medium text-violet-600 dark:text-violet-400">
              <ShieldCheck size={9} /> verify
            </span>
          )}
          {step.waiting && (
            <span className="mr-1.5 inline-flex items-center gap-0.5 rounded bg-amber-500/10 px-1 py-px text-[10px] font-medium text-amber-600 dark:text-amber-400">
              <Clock size={9} /> wait
            </span>
          )}
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

      {mission.status !== "running" && (() => {
        // A completed mission that the verification gate could NOT confirm is finished
        // but is NOT a success — show it honestly (amber), never a false green.
        const unconfirmed = mission.status === "complete" && mission.verified === false
        const verified = mission.status === "complete" && mission.verified === true
        const tone =
          verified || (mission.status === "complete" && mission.verified === undefined)
            ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
            : unconfirmed || mission.status === "blocked"
              ? "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-400"
              : "border-red-500/20 bg-red-500/10 text-red-600 dark:text-red-400"
        const Icon = verified
          ? ShieldCheck
          : unconfirmed
            ? ShieldAlert
            : mission.status === "complete"
              ? Flag
              : mission.status === "blocked"
                ? Hand
                : AlertTriangle
        return (
          <div className={`flex items-start gap-2 border-t px-3 py-2 text-xs ${tone}`}>
            <Icon size={13} className="mt-0.5 shrink-0" />
            <span className="min-w-0">
              {mission.status === "stopped"
                ? "Mission stopped."
                : mission.summary || `Mission ${mission.status}.`}
              {verified && mission.verification && (
                <span className="mt-1 flex items-start gap-1 font-medium">
                  <ShieldCheck size={12} className="mt-px shrink-0" /> Verified: {mission.verification}
                </span>
              )}
              {unconfirmed && (
                <span className="mt-1 flex items-start gap-1 font-medium">
                  <ShieldAlert size={12} className="mt-px shrink-0" />
                  Couldn't fully confirm: {mission.verification || "please double-check this yourself."}
                </span>
              )}
            </span>
          </div>
        )
      })()}
    </div>
  )
}

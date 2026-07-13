import { useState } from "react"
import { createPortal } from "react-dom"
import {
  Rocket, CheckCircle2, XCircle, Loader2, Square, ChevronDown, ChevronRight,
  AlertTriangle, Hand, ShieldCheck, ShieldAlert, Clock, Maximize2, Minimize2, Check, Brain,
  ArrowRight,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { serverColor, FLEET_COLOR } from "@/lib/serverColor"
import ServerTag from "./ServerTag"

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
  /** Planned with a stronger model (the mission was struggling) — model ladder. */
  strong?: boolean
}

/** Owner-facing structured outcome — the clear result card at the end of a mission
 *  (headline + what Ally Found / Did / Left for the user), from the backend `result`. */
export interface MissionResult {
  headline: string
  found: string[]
  did: string[]
  left: string[]
}

/** A risky step paused for the user — rendered INSIDE this mission's card so the
 *  approval always binds visibly to ITS mission (several may run at once). */
export interface MissionApproval {
  index: number
  cmd: string
  description: string
  riskLevel?: string
  serverName?: string | null
}

export interface MissionState {
  /** Routing key for control frames (approve/stop) — null if the mission row
   *  couldn't be persisted (the backend then routes to the sole live mission). */
  missionId?: string | null
  goal: string
  /** The home server — the card's identity tint. Fleet missions carry none. */
  serverName?: string | null
  status: "running" | "complete" | "blocked" | "failed" | "stopped"
  steps: MissionStep[]
  summary?: string
  stepsUsed?: number
  /** Verification gate outcome on a completed mission: true = goal proven, false =
   *  finished but the goal could NOT be confirmed (honest, not a success). */
  verified?: boolean
  /** What the verifier confirmed (verified) or what's still unproven (caveat). */
  verification?: string
  /** Owner-facing outcome rendered as a clear result card (headline + Found/Did/Left). */
  result?: MissionResult | null
  /** Set while a risky step waits for the user's OK (in-card approval). */
  pendingApproval?: MissionApproval | null
  /** Tappable answers when a mission blocks on a question (proactivity Track C). */
  options?: string[]
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
          {step.strong && (
            <span
              className="mr-1.5 inline-flex items-center gap-0.5 rounded bg-fuchsia-500/10 px-1 py-px text-[10px] font-medium text-fuchsia-600 dark:text-fuchsia-400"
              title="Ally used a stronger model for this step"
            >
              <Brain size={9} /> stronger model
            </span>
          )}
          {step.serverName && <ServerTag name={step.serverName} className="mr-1.5" />}
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

/** The status icon used by both the full card header and the collapsed pill. */
function StatusIcon({ mission }: { mission: MissionState }) {
  if (mission.status === "running") return <Loader2 size={13} className="shrink-0 animate-spin text-indigo-500" />
  if (mission.status === "complete")
    return mission.verified === false
      ? <ShieldAlert size={13} className="shrink-0 text-amber-500" />
      : <CheckCircle2 size={13} className="shrink-0 text-emerald-500" />
  if (mission.status === "blocked") return <Hand size={13} className="shrink-0 text-amber-500" />
  if (mission.status === "stopped") return <Square size={13} className="shrink-0 text-muted-foreground" />
  return <XCircle size={13} className="shrink-0 text-red-500" />
}

/** The clear "what happened" result at the end of a mission: Found / Did / Left-for-you.
 *  Renders only the sections that have content, so a simple mission stays compact. */
function ResultLists({ result }: { result: MissionResult }) {
  const sections = [
    { label: "Found", items: result.found, Icon: AlertTriangle, color: "text-red-400" },
    { label: "Ally did", items: result.did, Icon: Check, color: "text-emerald-400" },
    { label: "Left for you", items: result.left, Icon: ArrowRight, color: "text-amber-400" },
  ].filter((s) => s.items.length > 0)
  if (!sections.length) return null
  // Rendered on the DARK result card — light text, subtle white dividers.
  return (
    <div className="border-t border-white/10">
      {sections.map((s) => (
        <div key={s.label} className="border-b border-white/10 px-3.5 py-2.5 last:border-b-0">
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-zinc-500">{s.label}</p>
          <div className="space-y-1.5">
            {s.items.map((it, i) => (
              <div key={i} className="flex items-start gap-2 text-xs leading-relaxed">
                <s.Icon size={13} className={cn("mt-0.5 shrink-0", s.color)} />
                <span className="min-w-0 text-zinc-200">{it}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * A mission "workspace card": live step timeline, an in-card approval box when a risky
 * step pauses, a Stop while running, and a final banner. Collapses to a one-line pill
 * (the conversation stays calm around long work) and pops into a bigger overlay via ⤢.
 * The header carries the home server's stable color, so with several cards running you
 * can tell whose work is whose at a glance.
 */
export default function MissionProgress({
  mission,
  onStop,
  onApprove,
  onOption,
}: {
  mission: MissionState
  onStop: () => void
  /** Approve the step in `mission.pendingApproval` (routed by mission id). */
  onApprove?: () => void
  /** A blocked mission's tappable answer was picked — send it as the next message. */
  onOption?: (text: string) => void
}) {
  const [collapsed, setCollapsed] = useState(false)
  const [big, setBig] = useState(false)
  const running = mission.status === "running"
  const color = mission.serverName ? serverColor(mission.serverName) : FLEET_COLOR

  // Collapsed → a single calm line: status, goal, step count. Click to reopen.
  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className={cn(
          "flex w-full items-center gap-2 rounded-xl border border-l-4 bg-card px-3 py-2 text-left",
          "border-border", color.ring,
        )}
        title="Show the mission card"
      >
        <StatusIcon mission={mission} />
        <span className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">{mission.goal}</span>
        {mission.serverName && <ServerTag name={mission.serverName} />}
        <span className="shrink-0 text-[11px] text-muted-foreground">
          {mission.steps.length} step{mission.steps.length === 1 ? "" : "s"}
        </span>
        <ChevronDown size={12} className="shrink-0 text-muted-foreground" />
      </button>
    )
  }

  const card = (
    <div className={cn("overflow-hidden rounded-xl border border-l-4 border-border bg-card", color.ring, big && "flex max-h-full flex-col")}>
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <Rocket size={15} className="shrink-0 text-primary" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{mission.goal}</span>
        {mission.serverName && <ServerTag name={mission.serverName} />}
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
        <button
          onClick={() => setBig((b) => !b)}
          title={big ? "Back to the chat view" : "Open bigger"}
          className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
        >
          {big ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
        </button>
        {!big && (
          <button
            onClick={() => setCollapsed(true)}
            title="Collapse to one line"
            className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
          >
            <ChevronDown size={13} className="rotate-180" />
          </button>
        )}
      </div>

      <div className={cn("space-y-1.5 px-3 py-2.5", big && "min-h-0 flex-1 overflow-y-auto")}>
        {mission.steps.length === 0 && running && (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 size={12} className="animate-spin" /> Planning the first step…
          </p>
        )}
        {mission.steps.map((s) => (
          <StepRow key={s.index} step={s} />
        ))}
        {running && mission.steps.length > 0 && mission.steps.every((s) => !s.running) && !mission.pendingApproval && (
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Loader2 size={12} className="animate-spin" /> Deciding the next step…
          </p>
        )}
      </div>

      {/* In-card approval — the OK always binds visibly to THIS mission's step. */}
      {running && mission.pendingApproval && (
        <div className="space-y-1.5 border-t border-amber-500/25 bg-amber-500/5 px-3 py-2.5">
          <p className="flex items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-400">
            <Hand size={12} className="shrink-0" />
            Ally needs your OK for this step
            {mission.pendingApproval.serverName && (
              <ServerTag name={mission.pendingApproval.serverName} />
            )}
          </p>
          {mission.pendingApproval.description && (
            <p className="text-xs text-foreground">{mission.pendingApproval.description}</p>
          )}
          <pre className="overflow-x-auto rounded bg-[#0d0d0d] px-2 py-1 font-mono text-[11px] text-zinc-300">
            $ {mission.pendingApproval.cmd}
          </pre>
          <div className="flex items-center gap-2 pt-0.5">
            <button
              onClick={onApprove}
              className="flex items-center gap-1 rounded-md bg-emerald-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-emerald-500"
            >
              <Check size={11} /> Approve
            </button>
            <button
              onClick={onStop}
              className="flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-[11px] font-medium text-foreground hover:bg-accent"
            >
              <Square size={10} /> Stop the mission
            </button>
            {mission.pendingApproval.riskLevel === "high" && (
              <span className="rounded bg-red-500/10 px-1.5 py-0.5 text-[10px] font-medium text-red-600 dark:text-red-400">
                high risk
              </span>
            )}
          </div>
        </div>
      )}

      {mission.status !== "running" && (() => {
        // A completed mission that the verification gate could NOT confirm is finished
        // but is NOT a success — show it honestly (amber), never a false green.
        const unconfirmed = mission.status === "complete" && mission.verified === false
        const verified = mission.status === "complete" && mission.verified !== false
        // Per-outcome identity on the DARK result card: circled icon, colored border,
        // headline color, and a status badge — the "verdict" a non-technical owner reads.
        const v = verified
          ? { border: "border-emerald-500/40", chip: "bg-emerald-500/20", ic: "text-emerald-400",
              title: "text-emerald-300", badge: "bg-emerald-500/20 text-emerald-300",
              Icon: ShieldCheck, label: mission.verified === undefined ? "Done" : "Verified" }
          : unconfirmed
            ? { border: "border-amber-500/40", chip: "bg-amber-500/20", ic: "text-amber-400",
                title: "text-amber-300", badge: "bg-amber-500/20 text-amber-300",
                Icon: ShieldAlert, label: "Not confirmed" }
            : mission.status === "blocked"
              ? { border: "border-amber-500/40", chip: "bg-amber-500/20", ic: "text-amber-400",
                  title: "text-amber-300", badge: "bg-amber-500/20 text-amber-300",
                  Icon: Hand, label: "Needs your OK" }
              : mission.status === "stopped"
                ? { border: "border-zinc-600", chip: "bg-zinc-700", ic: "text-zinc-400",
                    title: "text-zinc-200", badge: "bg-zinc-700 text-zinc-300",
                    Icon: Square, label: "Stopped" }
                : { border: "border-red-500/40", chip: "bg-red-500/20", ic: "text-red-400",
                    title: "text-red-300", badge: "bg-red-500/20 text-red-300",
                    Icon: AlertTriangle, label: "Failed" }
        const headline =
          mission.status === "stopped"
            ? "Mission stopped."
            : mission.result?.headline || mission.summary || `Mission ${mission.status}.`
        // A distinct, rounded, DARK card so the result reads as its own report and stands
        // out from the rest of the workspace. The header names the site/server clearly.
        return (
          <div className="border-t border-border p-2.5">
            <div className={cn("overflow-hidden rounded-2xl border bg-zinc-900 shadow-lg", v.border)}>
              {/* Header — verdict + the site/server this result is about, stated clearly. */}
              <div className="flex items-start gap-2.5 px-3.5 pt-3 pb-2.5">
                <span className={cn("mt-px flex h-7 w-7 shrink-0 items-center justify-center rounded-full", v.chip)}>
                  <v.Icon size={15} className={v.ic} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500">
                      Mission result
                    </span>
                    <span className={cn("ml-auto rounded-full px-2 py-0.5 text-[10px] font-semibold", v.badge)}>
                      {v.label}
                    </span>
                  </div>
                  {mission.serverName && (
                    <p className="mt-0.5 flex items-center gap-1.5 text-sm font-semibold text-zinc-100">
                      <span className={cn("h-2 w-2 shrink-0 rounded-full", color.dot)} />
                      <span className="truncate">{mission.serverName}</span>
                    </p>
                  )}
                  <p className={cn("mt-1 text-[13px] font-medium leading-snug", v.title)}>{headline}</p>
                  {verified && mission.verification && (
                    <p className="mt-1 flex items-start gap-1 text-[11px] text-zinc-400">
                      <ShieldCheck size={11} className="mt-px shrink-0 text-emerald-400" /> Verified: {mission.verification}
                    </p>
                  )}
                  {unconfirmed && (
                    <p className="mt-1 flex items-start gap-1 text-[11px] text-zinc-400">
                      <ShieldAlert size={11} className="mt-px shrink-0 text-amber-400" />
                      Couldn't fully confirm: {mission.verification || "please double-check this yourself."}
                    </p>
                  )}
                </div>
              </div>

              {/* Body — the clear Found / Ally did / Left-for-you breakdown. */}
              {mission.result && <ResultLists result={mission.result} />}

              {/* Track C: a blocked mission that asked a question — tap an answer to reply
                  (free text still works by typing). Sits at the card's foot. */}
              {mission.status === "blocked" && mission.options && mission.options.length > 0 && (
                <div className="flex flex-wrap gap-1.5 border-t border-white/10 px-3.5 py-2.5">
                  {mission.options.map((o, i) => (
                    <button
                      key={i}
                      onClick={() => onOption?.(o)}
                      className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-[11px] font-medium text-amber-300 transition-colors hover:bg-amber-500/20"
                    >
                      {o}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        )
      })()}
    </div>
  )

  // ⤢ big view: the SAME card in a roomy centered overlay; a slim inline stub keeps its
  // place in the conversation. Portaled to <body> so the drawer's CSS transform (which
  // would otherwise re-root position:fixed) can't confine the backdrop.
  if (big) {
    return (
      <>
        <div className="flex items-center gap-2 rounded-xl border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
          <StatusIcon mission={mission} />
          <span className="min-w-0 flex-1 truncate">{mission.goal}</span>
          <span className="shrink-0">viewing large</span>
        </div>
        {createPortal(
          <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4 md:p-10" onClick={() => setBig(false)}>
            <div className="max-h-full w-full max-w-3xl" onClick={(e) => e.stopPropagation()}>
              {card}
            </div>
          </div>,
          document.body,
        )}
      </>
    )
  }

  return card
}

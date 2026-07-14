import { useState } from "react"
import { CheckCircle2, XCircle, ChevronDown, ChevronRight, Clock } from "lucide-react"
import type { MissionStepRecord } from "@/api/missions"
import { redactSecrets } from "@/lib/redactSecrets"

/** One transcript step — description + (on click) the redacted command + output. */
function StepRow({ s, i }: { s: MissionStepRecord; i: number }) {
  const [open, setOpen] = useState(false)
  const ok = (s.exit_code ?? 0) === 0
  const cmd = redactSecrets(s.cmd || "").text
  const out = redactSecrets(s.output_tail || "").text
  const hasDetail = Boolean(cmd || out)
  const isWait = Boolean(s.note && /wait/i.test(s.note))
  return (
    <div className="text-xs">
      <button
        onClick={() => hasDetail && setOpen((o) => !o)}
        className={`flex w-full items-start gap-1.5 text-left ${hasDetail ? "cursor-pointer" : "cursor-default"}`}
      >
        <span className="mt-0.5 w-5 shrink-0 text-right text-[10px] text-muted-foreground">{i + 1}</span>
        <span className="mt-0.5 shrink-0">
          {s.verify ? (
            <CheckCircle2 size={12} className="text-violet-500" />
          ) : isWait ? (
            <Clock size={12} className="text-amber-500" />
          ) : ok ? (
            <CheckCircle2 size={12} className="text-emerald-500" />
          ) : (
            <XCircle size={12} className="text-red-500" />
          )}
        </span>
        <span className="min-w-0 flex-1">
          {s.verify && <span className="mr-1.5 rounded bg-violet-500/10 px-1 py-px text-[10px] font-medium text-violet-600 dark:text-violet-400">verify</span>}
          {s.server && <span className="mr-1.5 rounded bg-indigo-500/10 px-1 py-px text-[10px] font-medium text-indigo-600 dark:text-indigo-400">{s.server}</span>}
          <span className="text-foreground">{s.description || cmd}</span>
          {s.note && <span className="ml-1 text-amber-600 dark:text-amber-400">({s.note})</span>}
        </span>
        {hasDetail && <span className="mt-0.5 shrink-0 text-muted-foreground">{open ? <ChevronDown size={11} /> : <ChevronRight size={11} />}</span>}
      </button>
      {open && (
        <div className="ml-11 mt-1 space-y-1">
          {cmd && <pre className="overflow-x-auto rounded bg-[#0d0d0d] px-2 py-1 font-mono text-[11px] text-zinc-300">$ {cmd}</pre>}
          {out && <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded bg-[#0d0d0d] px-2 py-1 font-mono text-[11px] text-zinc-400">{out}</pre>}
        </div>
      )}
    </div>
  )
}

/** The mission's step-by-step transcript — redacted, each step expandable to its command +
 *  output. Shared by the Missions detail pane (and any deep link into a mission's log). */
export default function MissionStepList({ steps, summary }: { steps: MissionStepRecord[]; summary?: string | null }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      {summary && <p className="mb-3 border-b border-border pb-3 text-xs text-muted-foreground">{summary}</p>}
      {steps.length === 0 ? (
        <p className="text-xs text-muted-foreground">No steps recorded.</p>
      ) : (
        <div className="space-y-1.5">
          {steps.map((s, i) => (
            <StepRow key={i} s={s} i={i} />
          ))}
        </div>
      )}
    </div>
  )
}

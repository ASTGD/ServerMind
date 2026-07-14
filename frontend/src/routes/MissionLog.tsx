import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link, useParams } from "react-router-dom"
import { formatDistanceToNow } from "date-fns"
import { ArrowLeft, CheckCircle2, XCircle, ChevronDown, ChevronRight, FileText, ScrollText } from "lucide-react"
import { getMission, type MissionStepRecord } from "@/api/missions"
import { isReport } from "@/api/reports"
import { redactSecrets } from "@/lib/redactSecrets"

/** One transcript step — description + (on click) the redacted command + output. */
function StepRow({ s, i }: { s: MissionStepRecord; i: number }) {
  const [open, setOpen] = useState(false)
  const ok = (s.exit_code ?? 0) === 0
  const cmd = redactSecrets(s.cmd || "").text
  const out = redactSecrets(s.output_tail || "").text
  const hasDetail = Boolean(cmd || out)
  return (
    <div className="text-xs">
      <button
        onClick={() => hasDetail && setOpen((o) => !o)}
        className={`flex w-full items-start gap-1.5 text-left ${hasDetail ? "cursor-pointer" : "cursor-default"}`}
      >
        <span className="mt-0.5 w-5 shrink-0 text-right text-[10px] text-muted-foreground">{i + 1}</span>
        <span className="mt-0.5 shrink-0">
          {ok ? <CheckCircle2 size={12} className="text-emerald-500" /> : <XCircle size={12} className="text-red-500" />}
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

export default function MissionLog() {
  const { id = "" } = useParams()
  const { data: m, isLoading, isError } = useQuery({ queryKey: ["mission", id], queryFn: () => getMission(id), enabled: !!id })

  if (isLoading) return <p className="px-6 py-8 text-sm text-muted-foreground">Loading log…</p>
  if (isError || !m) return <p className="px-6 py-8 text-sm text-muted-foreground">Mission log not found.</p>

  const steps = m.steps ?? []
  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-6">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <Link to="/logs" className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Logs
        </Link>
        {isReport(m) && (
          <Link to={`/reports/${m.id}`} className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-accent">
            <FileText className="h-3.5 w-3.5" /> View report
          </Link>
        )}
      </div>

      <header className="mb-4">
        <h1 className="flex items-center gap-2 text-lg font-semibold text-foreground">
          <ScrollText className="h-5 w-5 text-primary" /> Mission log
        </h1>
        <p className="mt-1 text-sm text-foreground">{m.goal}</p>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
          {m.server_name && <span>{m.server_name}</span>}
          {m.skill && <span>· {m.skill}</span>}
          <span>· {steps.length} step{steps.length === 1 ? "" : "s"}</span>
          {m.created_at && <span>· {formatDistanceToNow(new Date(m.created_at), { addSuffix: true })}</span>}
        </div>
      </header>

      <div className="rounded-xl border border-border bg-card p-4">
        {m.summary && <p className="mb-3 border-b border-border pb-3 text-xs text-muted-foreground">{m.summary}</p>}
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
      <p className="mt-2 px-1 text-[11px] text-muted-foreground">Secrets in commands and output are masked.</p>
    </div>
  )
}

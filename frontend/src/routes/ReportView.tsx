import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Link, useParams } from "react-router-dom"
import {
  ArrowLeft, Printer, FileDown, Braces, Copy, Check, Globe, AlertTriangle,
  ArrowRight, ShieldCheck, ShieldAlert, ChevronDown, ChevronRight, Sparkles, Loader2,
} from "lucide-react"
import {
  getReport, reportVerdict, reportSubject, reportToMarkdown, reportToJson,
  reportFilename, downloadText,
} from "@/api/reports"
import { generateIncidentReport, type MissionDetail } from "@/api/missions"
import { SHEET_TONE, Section, IncidentNarrative } from "@/components/reports/reportUI"
import { redactSecrets } from "@/lib/redactSecrets"
import { useAuthStore } from "@/store/authStore"
import { cn } from "@/lib/utils"

const PRINT_CSS = `
@media print {
  .no-print { display: none !important; }
  body * { visibility: hidden; }
  .report-sheet, .report-sheet * { visibility: visible; }
  .report-sheet { position: absolute; left: 0; top: 0; width: 100%; box-shadow: none; border: 0; border-radius: 0; }
  @page { margin: 18mm; }
}
`

export default function ReportView() {
  const { id = "" } = useParams()
  const user = useAuthStore((s) => s.user)
  const [copied, setCopied] = useState(false)
  const [showLog, setShowLog] = useState(false)
  const qc = useQueryClient()
  const { data: m, isLoading, isError } = useQuery({ queryKey: ["report", id], queryFn: () => getReport(id), enabled: !!id })

  // "Explain this incident" — generate the narrative, then patch it into the cached report.
  const genIncident = useMutation({
    mutationFn: () => generateIncidentReport(id),
    onSuccess: (rep) =>
      qc.setQueryData<MissionDetail>(["report", id], (old) => (old ? { ...old, incident_report: rep } : old)),
  })

  if (isLoading) return <p className="px-6 py-8 text-sm text-muted-foreground">Loading report…</p>
  if (isError || !m) return <p className="px-6 py-8 text-sm text-muted-foreground">Report not found.</p>

  const v = reportVerdict(m)
  const r = m.result
  const incident = m.incident_report ?? null
  const date = (m.updated_at || m.created_at || "").slice(0, 10)
  const steps = m.steps ?? []

  const onCopy = async () => {
    await navigator.clipboard.writeText(reportToMarkdown(m))
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const btn = "flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent"

  return (
    <div className="mx-auto max-w-[880px] px-4 py-6 sm:px-6">
      {/* Toolbar — hidden when printing */}
      <div className="no-print mb-4 flex flex-wrap items-center justify-between gap-2">
        <Link to="/reports" className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Reports
        </Link>
        <div className="flex flex-wrap items-center gap-1.5">
          <button onClick={() => window.print()} className={cn(btn, "border-primary/40 bg-primary/5 text-primary hover:bg-primary/10")}>
            <Printer className="h-3.5 w-3.5" /> Download PDF
          </button>
          <button onClick={() => downloadText(reportFilename(m, "md"), reportToMarkdown(m), "text/markdown")} className={btn}>
            <FileDown className="h-3.5 w-3.5" /> Markdown
          </button>
          <button onClick={() => downloadText(reportFilename(m, "json"), JSON.stringify(reportToJson(m), null, 2), "application/json")} className={btn}>
            <Braces className="h-3.5 w-3.5" /> JSON
          </button>
          <button onClick={onCopy} className={btn}>
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />} {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>

      {/* The report "sheet" — a clean white document (same on screen + PDF) */}
      <article className="report-sheet mx-auto max-w-[820px] rounded-xl border border-zinc-200 bg-white p-8 text-zinc-900 shadow-sm">
        <header className="flex items-start justify-between gap-4 border-b border-zinc-200 pb-4">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-400">ServerAlly · Mission Report</p>
            <h1 className="mt-1 flex items-center gap-2 text-lg font-bold text-zinc-900">
              <Globe className="h-4 w-4 text-zinc-400" /> {reportSubject(m)}
            </h1>
            <p className="mt-0.5 text-xs text-zinc-500">
              {m.server_name ? <>on <span className="font-medium text-zinc-700">{m.server_name}</span> · </> : null}
              {date || "—"}
            </p>
          </div>
          <span className={cn("flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-bold", SHEET_TONE[v.tone])}>
            {v.tone === "good" ? <ShieldCheck className="h-3.5 w-3.5" /> : v.tone === "warn" ? <ShieldAlert className="h-3.5 w-3.5" /> : null}
            {v.label}
          </span>
        </header>

        <div className="mt-4">
          <p className="text-[11px] font-bold uppercase tracking-wider text-zinc-400">Goal</p>
          <p className="mt-0.5 text-[13px] text-zinc-700">{m.goal}</p>
        </div>

        {/* The AI incident narrative — the "how this happened" story (generated on demand,
            cached on the mission). Falls back to the structured result card below. */}
        {incident ? (
          <IncidentNarrative report={incident} showActions={!r} />
        ) : (
          <div className="no-print mt-5 rounded-lg border border-dashed border-zinc-300 bg-zinc-50/70 p-4">
            <button
              onClick={() => genIncident.mutate()}
              disabled={genIncident.isPending}
              className="flex items-center gap-2 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-60"
            >
              {genIncident.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {genIncident.isPending ? "Ally is writing the story…" : "Explain how this happened"}
            </button>
            <p className="mt-2 text-[11px] leading-relaxed text-zinc-500">
              Ally reads the full mission and writes a plain-language story — how it started, a timeline, and how serious
              it is. Uses 1 AI action.
            </p>
            {genIncident.isError && (
              <p className="mt-1.5 text-xs text-red-600">Couldn't generate the story — please try again.</p>
            )}
          </div>
        )}

        <h2 className="mt-5 text-base font-semibold leading-snug text-zinc-900">
          {r?.headline || m.summary || "Mission outcome"}
        </h2>

        {r ? (
          <>
            <Section label="Found" items={r.found} Icon={AlertTriangle} color="text-red-500" />
            <Section label="Ally did" items={r.did} Icon={Check} color="text-emerald-600" />
            <Section label="Left for you" items={r.left} Icon={ArrowRight} color="text-amber-600" />
          </>
        ) : (
          m.summary && <p className="mt-3 text-[13px] leading-relaxed text-zinc-700">{m.summary}</p>
        )}

        {/* Technical appendix — secret-redacted, collapsible on screen, always shown in print */}
        {steps.length > 0 && (
          <div className="mt-6 border-t border-zinc-200 pt-4">
            <button
              onClick={() => setShowLog((s) => !s)}
              className="no-print flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-zinc-500 hover:text-zinc-800"
            >
              {showLog ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
              Technical log ({steps.length} steps)
            </button>
            <p className="hidden text-[11px] font-bold uppercase tracking-wider text-zinc-500 print:block">
              Technical log ({steps.length} steps)
            </p>
            <ol className={cn("mt-2 space-y-1 text-[12px] leading-relaxed text-zinc-600", !showLog && "hidden print:block")}>
              {steps.map((s, i) => (
                <li key={i} className="flex gap-2">
                  <span className="shrink-0 text-zinc-400">{i + 1}.</span>
                  <span>{redactSecrets(s.description || s.cmd || "").text}</span>
                </li>
              ))}
            </ol>
          </div>
        )}

        <footer className="mt-8 border-t border-zinc-200 pt-3 text-[10px] text-zinc-400">
          {user?.name ? <>Prepared by {user.name} · </> : null}Generated by ServerAlly · Mission {m.id}
        </footer>
      </article>

      <style>{PRINT_CSS}</style>
    </div>
  )
}

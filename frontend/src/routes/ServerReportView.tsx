import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link, useParams } from "react-router-dom"
import { AxiosError } from "axios"
import { ArrowLeft, Printer, FileDown, Copy, Check, HardDrive, Loader2, ListChecks } from "lucide-react"
import {
  generateServerReport, serverReportToMarkdown, serverReportFilename, downloadText,
} from "@/api/reports"
import { IncidentNarrative } from "@/components/reports/reportUI"
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

export default function ServerReportView() {
  const { serverId = "" } = useParams()
  const user = useAuthStore((s) => s.user)
  const [copied, setCopied] = useState(false)

  // Generate on visit (POST = 1 AI action); cached for the session so re-viewing is free.
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["server-report", serverId],
    queryFn: () => generateServerReport(serverId),
    enabled: !!serverId,
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
  })

  const btn = "flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent"

  if (isLoading) {
    return (
      <div className="mx-auto flex max-w-[880px] flex-col items-center gap-3 px-4 py-24 text-center">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
        <p className="text-sm font-medium text-foreground">Ally is writing the whole-server report…</p>
        <p className="text-xs text-muted-foreground">Reading every finished mission on this server and summarizing it into one report.</p>
      </div>
    )
  }

  if (isError || !data) {
    const status = (error as AxiosError)?.response?.status
    const detail = ((error as AxiosError<{ detail?: string }>)?.response?.data?.detail) || ""
    const msg = status === 422
      ? "This server has no finished missions yet — run a mission first, then generate its report."
      : detail || "Couldn't generate the server report. Please try again."
    return (
      <div className="mx-auto max-w-[880px] px-4 py-16 text-center">
        <p className="text-sm text-muted-foreground">{msg}</p>
        <Link to="/reports" className="mt-3 inline-flex items-center gap-1.5 text-sm text-primary hover:underline">
          <ArrowLeft className="h-4 w-4" /> Back to Reports
        </Link>
      </div>
    )
  }

  const r = data.report

  const onCopy = async () => {
    await navigator.clipboard.writeText(serverReportToMarkdown(data))
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

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
          <button onClick={() => downloadText(serverReportFilename(data.server_name, "md"), serverReportToMarkdown(data), "text/markdown")} className={btn}>
            <FileDown className="h-3.5 w-3.5" /> Markdown
          </button>
          <button onClick={onCopy} className={btn}>
            {copied ? <Check className="h-3.5 w-3.5 text-emerald-500" /> : <Copy className="h-3.5 w-3.5" />} {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>

      {/* The report "sheet" — a clean white document (same on screen + PDF) */}
      <article className="report-sheet mx-auto max-w-[820px] rounded-xl border border-zinc-200 bg-white p-8 text-zinc-900 shadow-sm">
        <header className="border-b border-zinc-200 pb-4">
          <p className="text-[11px] font-bold uppercase tracking-widest text-zinc-400">ServerAlly · Whole-server report</p>
          <h1 className="mt-1 flex items-center gap-2 text-lg font-bold text-zinc-900">
            <HardDrive className="h-4 w-4 text-zinc-400" /> {data.server_name}
          </h1>
          <p className="mt-0.5 text-xs text-zinc-500">
            Based on {data.mission_count} finished mission{data.mission_count === 1 ? "" : "s"} on this server
          </p>
        </header>

        {/* The AI narrative (headline, how it happened, timeline, impact, done/left, caveat) */}
        <IncidentNarrative report={r} showActions />

        {/* Per-site / per-mission breakdown */}
        {r.breakdown.length > 0 && (
          <div className="mt-6">
            <h3 className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-zinc-500">
              <ListChecks className="h-3.5 w-3.5" /> By site / mission
            </h3>
            <div className="overflow-hidden rounded-lg border border-zinc-200">
              <table className="w-full text-[13px]">
                <tbody>
                  {r.breakdown.map((b, i) => (
                    <tr key={i} className="border-b border-zinc-100 last:border-0">
                      <td className="w-1/3 px-3 py-2 align-top font-semibold text-zinc-800">{b.title}</td>
                      <td className="px-3 py-2 text-zinc-600">{b.outcome}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        <footer className="mt-8 border-t border-zinc-200 pt-3 text-[10px] text-zinc-400">
          {user?.name ? <>Prepared by {user.name} · </> : null}Generated by ServerAlly · Server {data.server_name}
        </footer>
      </article>

      <style>{PRINT_CSS}</style>
    </div>
  )
}

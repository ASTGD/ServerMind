import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link, useParams, useSearchParams } from "react-router-dom"
import {
  ArrowLeft, Printer, FileDown, Copy, Check, Loader2, ShieldCheck,
  Activity, Archive, ListChecks,
} from "lucide-react"
import {
  getClientReport, clientReportToMarkdown, clientReportFilename, type ClientReport,
} from "@/api/branding"
import { downloadText } from "@/api/reports"
import { cn } from "@/lib/utils"

/**
 * The client report — what an agency shows (or sends) to *their* client.
 *
 * Deliberately deterministic: every number comes from data we already store, so the same
 * period always renders the same report. It carries the AGENCY's branding, not ours.
 */
const PRINT_CSS = `
@media print {
  .no-print { display: none !important; }
  body * { visibility: hidden; }
  .report-sheet, .report-sheet * { visibility: visible; }
  .report-sheet { position: absolute; left: 0; top: 0; width: 100%; box-shadow: none; border: 0; border-radius: 0; }
  @page { margin: 18mm; }
}
`

const TONE: Record<ClientReport["tone"], string> = {
  good: "border-emerald-300 bg-emerald-50 text-emerald-800",
  warn: "border-amber-300 bg-amber-50 text-amber-800",
  bad: "border-red-300 bg-red-50 text-red-800",
}

/** One headline number. Kept plain — a client reads this, not an engineer. */
function Figure({ Icon, label, value, note }: {
  Icon: typeof Activity; label: string; value: string; note?: string
}) {
  return (
    <div className="rounded-xl border border-slate-200 p-4">
      <span className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-slate-500">
        <Icon className="h-3.5 w-3.5" /> {label}
      </span>
      <p className="mt-1.5 text-[22px] font-semibold leading-none text-slate-900">{value}</p>
      {note && <p className="mt-1 text-[11.5px] text-slate-500">{note}</p>}
    </div>
  )
}

export default function ClientReportView() {
  const { serverId = "" } = useParams()
  const [params] = useSearchParams()
  const days = Number(params.get("days")) || 30
  const [copied, setCopied] = useState(false)

  const { data, isLoading, isError } = useQuery({
    queryKey: ["client-report", serverId, days],
    queryFn: () => getClientReport(serverId, days),
    enabled: !!serverId,
    retry: false,
  })

  const btn =
    "flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent"

  if (isLoading) {
    return (
      <div className="mx-auto flex max-w-[880px] flex-col items-center gap-3 px-4 py-24 text-center">
        <Loader2 className="h-6 w-6 animate-spin text-primary" />
        <p className="text-sm text-muted-foreground">Building the report…</p>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="mx-auto max-w-[880px] px-4 py-16 text-center">
        <p className="text-sm text-muted-foreground">Couldn’t build this report.</p>
        <Link to="/reports" className="mt-3 inline-flex items-center gap-1.5 text-sm text-primary hover:underline">
          <ArrowLeft className="h-4 w-4" /> Back to Reports
        </Link>
      </div>
    )
  }

  const brand = data.branding
  const color = brand.primary_color || "#4f46e5"
  const up = data.uptime
  const sec = data.security
  const bk = data.backups

  const copy = async () => {
    await navigator.clipboard.writeText(clientReportToMarkdown(data))
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  return (
    <div className="mx-auto max-w-[880px] px-4 py-6">
      <style>{PRINT_CSS}</style>

      {/* Toolbar — the agency's controls, never part of the printed sheet. */}
      <div className="no-print mb-4 flex flex-wrap items-center justify-between gap-2">
        <Link to="/reports" className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" /> Reports
        </Link>
        <div className="flex flex-wrap items-center gap-2">
          <button onClick={() => window.print()} className={cn(btn, "border-primary/40 bg-primary/5 text-primary hover:bg-primary/10")}>
            <Printer className="h-3.5 w-3.5" /> Download PDF
          </button>
          <button
            onClick={() => downloadText(
              clientReportFilename(data.server_name, "md"), clientReportToMarkdown(data), "text/markdown",
            )}
            className={btn}
          >
            <FileDown className="h-3.5 w-3.5" /> Markdown
          </button>
          <button onClick={copy} className={btn}>
            {copied ? <><Check className="h-3.5 w-3.5 text-emerald-600" /> Copied</> : <><Copy className="h-3.5 w-3.5" /> Copy</>}
          </button>
        </div>
      </div>

      {/* The sheet — identical on screen and in the PDF. */}
      <div className="report-sheet rounded-2xl border border-slate-200 bg-white p-8 shadow-sm sm:p-10">
        <header className="mb-6 border-b border-slate-200 pb-5">
          {brand.logo_url && (
            <img
              src={brand.logo_url} alt=""
              className="mb-3 h-8 w-auto max-w-[180px] object-contain"
              onError={(e) => { (e.target as HTMLImageElement).style.display = "none" }}
            />
          )}
          {brand.company_name && (
            <p className="text-[13px] font-semibold" style={{ color }}>{brand.company_name}</p>
          )}
          <h1 className="mt-1 text-[26px] font-semibold leading-tight text-slate-900">
            {data.server_name}
          </h1>
          <p className="mt-1 text-[13px] text-slate-500">
            Your {data.period_days}-day report · {data.period_start} to {data.period_end}
          </p>
        </header>

        <div className={cn("mb-6 rounded-xl border px-4 py-3.5 text-[15px] font-medium", TONE[data.tone])}>
          {data.headline}
        </div>

        <div className="mb-7 space-y-2">
          {data.summary.map((line, i) => (
            <p key={i} className="text-[14.5px] leading-relaxed text-slate-700">{line}</p>
          ))}
        </div>

        <h2 className="mb-3 text-[13px] font-semibold uppercase tracking-wide text-slate-500">
          The numbers
        </h2>
        <div className="mb-7 grid gap-3 sm:grid-cols-3">
          <Figure
            Icon={Activity} label="Uptime"
            value={up.monitored && up.percentage !== null ? `${up.percentage}%` : "—"}
            note={up.monitored ? `${up.outages} failed check${up.outages === 1 ? "" : "s"}` : "not monitored yet"}
          />
          <Figure
            Icon={ShieldCheck} label="Security"
            value={sec.score !== null ? `${sec.score}/100` : "—"}
            note={sec.grade ? `Grade ${sec.grade}${sec.threat_verdict === "clean" ? " · scan clean" : ""}` : "no review yet"}
          />
          <Figure
            Icon={Archive} label="Backups"
            value={bk.configured ? `${bk.successful}/${bk.runs}` : "—"}
            note={bk.configured ? "completed successfully" : "not set up yet"}
          />
        </div>

        {data.work.completed.length > 0 && (
          <>
            <h2 className="mb-3 flex items-center gap-1.5 text-[13px] font-semibold uppercase tracking-wide text-slate-500">
              <ListChecks className="h-3.5 w-3.5" /> What we did
            </h2>
            <ul className="mb-7 space-y-2">
              {data.work.completed.map((w, i) => (
                <li key={i} className="flex items-start gap-2 text-[14px] text-slate-700">
                  <Check className="mt-[3px] h-3.5 w-3.5 shrink-0 text-emerald-600" />
                  <span>
                    {w.goal}
                    {w.verified && (
                      <span className="ml-1.5 rounded bg-emerald-50 px-1.5 py-px text-[10.5px] font-medium text-emerald-700">
                        verified
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}

        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 pt-4">
          <span className="text-[11.5px] text-slate-500">
            {brand.footer_text || brand.company_name || ""}
          </span>
          <span className="flex items-center gap-3 text-[11.5px] text-slate-500">
            {(brand.support_url || brand.support_email) && (
              <a
                href={brand.support_url || `mailto:${brand.support_email}`}
                className="underline hover:text-slate-700"
              >
                Get in touch
              </a>
            )}
            {/* White-label: the agency can remove our credit entirely. */}
            {brand.show_credit && <span>Monitored by {brand.app_name}</span>}
          </span>
        </footer>
      </div>
    </div>
  )
}

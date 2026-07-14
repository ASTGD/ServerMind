/** Shared report-sheet UI — used by the per-mission report (ReportView) and the
 *  whole-server report (ServerReportView). The "sheet" is intentionally light in both
 *  themes so the on-screen view matches the printed / exported PDF. */
import { AlertTriangle, Check, ArrowRight, Sparkles, Clock, DoorOpen } from "lucide-react"
import type { IncidentReport } from "@/api/missions"
import type { Verdict } from "@/api/reports"
import { cn } from "@/lib/utils"

/** Fixed light colors for the verdict badge so the printed sheet looks the same everywhere. */
export const SHEET_TONE: Record<Verdict["tone"], string> = {
  good: "bg-emerald-100 text-emerald-800",
  warn: "bg-amber-100 text-amber-800",
  bad: "bg-red-100 text-red-800",
  neutral: "bg-zinc-200 text-zinc-700",
}

/** Severity → a fixed light-mode chip. */
export const SEVERITY: Record<string, { label: string; cls: string }> = {
  critical: { label: "Critical", cls: "bg-red-100 text-red-800" },
  high: { label: "High", cls: "bg-orange-100 text-orange-800" },
  medium: { label: "Medium", cls: "bg-amber-100 text-amber-800" },
  low: { label: "Low", cls: "bg-emerald-100 text-emerald-800" },
}

export function Section({ label, items, Icon, color }: { label: string; items: string[]; Icon: typeof AlertTriangle; color: string }) {
  if (!items?.length) return null
  return (
    <div className="mt-5">
      <h3 className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-zinc-500">{label}</h3>
      <ul className="space-y-1.5">
        {items.map((it, i) => (
          <li key={i} className="flex items-start gap-2 text-[13px] leading-relaxed text-zinc-800">
            <Icon className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", color)} />
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** The AI incident narrative: how it happened, timeline, and how serious it is. done/left
 *  render only when showActions (otherwise a structured result card already covers them). */
export function IncidentNarrative({ report, showActions }: { report: IncidentReport; showActions: boolean }) {
  const sev = SEVERITY[report.severity]
  return (
    <div className="mt-5 rounded-lg border border-zinc-200 bg-zinc-50/70 p-5">
      <div className="flex items-center gap-2">
        <Sparkles className="h-3.5 w-3.5 text-primary" />
        <h2 className="text-[11px] font-bold uppercase tracking-wider text-zinc-500">How this happened</h2>
        {sev && (
          <span className={cn("ml-auto rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide", sev.cls)}>
            {sev.label}
          </span>
        )}
      </div>

      {report.headline && (
        <p className="mt-2 text-[15px] font-semibold leading-snug text-zinc-900">{report.headline}</p>
      )}

      {report.how_they_got_in && (
        <div className="mt-4">
          <h3 className="mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-zinc-500">
            <DoorOpen className="h-3.5 w-3.5" /> How they got in
          </h3>
          <p className="text-[13px] leading-relaxed text-zinc-700">{report.how_they_got_in}</p>
        </div>
      )}

      {report.timeline.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-zinc-500">
            <Clock className="h-3.5 w-3.5" /> Timeline
          </h3>
          <ol className="space-y-2 border-l-2 border-zinc-200 pl-3">
            {report.timeline.map((e, i) => (
              <li key={i} className="relative text-[13px] leading-relaxed">
                <span className="absolute -left-[15px] top-1.5 h-1.5 w-1.5 rounded-full bg-primary" />
                {e.when && <span className="font-semibold text-zinc-900">{e.when}</span>}
                {e.when && e.what && <span className="text-zinc-400"> — </span>}
                {e.what && <span className="text-zinc-700">{e.what}</span>}
              </li>
            ))}
          </ol>
        </div>
      )}

      {report.impact && (
        <div className="mt-4">
          <h3 className="mb-1 text-[11px] font-bold uppercase tracking-wider text-zinc-500">How serious</h3>
          <p className="text-[13px] leading-relaxed text-zinc-700">{report.impact}</p>
        </div>
      )}

      {showActions && (report.done.length > 0 || report.left.length > 0) && (
        <>
          <Section label="Done" items={report.done} Icon={Check} color="text-emerald-600" />
          <Section label="Still to do" items={report.left} Icon={ArrowRight} color="text-amber-600" />
        </>
      )}

      {report.caveat && (
        <p className="mt-4 flex items-start gap-2 rounded-md bg-amber-50 p-2.5 text-[12px] italic leading-relaxed text-amber-900">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {report.caveat}
        </p>
      )}
    </div>
  )
}

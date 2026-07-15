import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import { formatDistanceToNow } from "date-fns"
import { FileText, Globe, Search, ShieldCheck, ShieldAlert, Hand, Flag, Square, Sparkles } from "lucide-react"
import { listReports, reportVerdict, reportSubject, type Verdict } from "@/api/reports"
import { listServers } from "@/api/servers"
import { cn } from "@/lib/utils"
import type { MissionSummary } from "@/api/missions"
import ReportView from "./ReportView"

/** tone → tailwind classes for the verdict badge (light-surface, works in both themes). */
const TONE: Record<Verdict["tone"], string> = {
  good: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  warn: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  bad: "bg-red-500/15 text-red-700 dark:text-red-300",
  neutral: "bg-muted text-muted-foreground",
}

function VerdictIcon({ v }: { v: Verdict }) {
  const cls = "h-3.5 w-3.5 shrink-0"
  if (v.label === "Verified") return <ShieldCheck className={cls} />
  if (v.label === "Not confirmed") return <ShieldAlert className={cls} />
  if (v.label === "Needs your OK") return <Hand className={cls} />
  if (v.label === "Stopped") return <Square className={cls} />
  return <Flag className={cls} />
}

/** A selectable report row in the left list. */
function ReportRow({ m, selected, onClick }: { m: MissionSummary; selected: boolean; onClick: () => void }) {
  const v = reportVerdict(m)
  const r = m.result
  const counts = [
    r?.found?.length ? `${r.found.length} found` : null,
    r?.did?.length ? `${r.did.length} done` : null,
    r?.left?.length ? `${r.left.length} for you` : null,
  ].filter(Boolean)
  const when = m.updated_at || m.created_at
  return (
    <button
      onClick={onClick}
      className={cn(
        "block w-full rounded-xl border bg-card px-3 py-2.5 text-left transition-colors",
        selected ? "border-primary ring-1 ring-primary/40" : "border-border hover:border-primary/40 hover:bg-accent/40",
      )}
    >
      <div className="flex items-center gap-2">
        <span className={cn("flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold", TONE[v.tone])}>
          <VerdictIcon v={v} /> {v.label}
        </span>
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-foreground">
          <Globe className="mr-1 inline h-3 w-3 text-muted-foreground" />
          {reportSubject(m)}
        </span>
      </div>
      <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{r?.headline || m.summary || m.goal}</p>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground">
        {m.server_name && m.result?.subject && <span className="truncate">{m.server_name}</span>}
        {counts.map((c) => (
          <span key={c}>· {c}</span>
        ))}
        <span>· {when ? formatDistanceToNow(new Date(when), { addSuffix: true }) : "—"}</span>
      </div>
    </button>
  )
}

export default function Reports() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: reports = [], isLoading } = useQuery({ queryKey: ["reports"], queryFn: () => listReports() })
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers })
  const [q, setQ] = useState("")
  const [serverId, setServerId] = useState("")

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return reports.filter((m) => {
      if (serverId && m.server_id !== serverId) return false
      if (!needle) return true
      return (
        reportSubject(m).toLowerCase().includes(needle) ||
        (m.goal || "").toLowerCase().includes(needle) ||
        (m.result?.headline || m.summary || "").toLowerCase().includes(needle)
      )
    })
  }, [reports, serverId, q])

  // Default to the first report so the detail pane is never empty.
  const shownId = id ?? filtered[0]?.id

  return (
    <div>
      <header className="mb-4">
        <h1 className="flex items-center gap-2 text-xl font-semibold text-foreground">
          <FileText className="h-5 w-5 text-primary" /> Reports
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Every finished mission, ready to review, share, or export as a PDF for your client.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3 lg:items-start">
        {/* LEFT — filters + the report list. Search + filter share one row so the first
            list card lines up with the report sheet's top (single-row toolbar) on the right. */}
        <aside className="min-w-0 lg:col-span-1">
          <div className="mb-3 flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Search reports…"
                className="w-full rounded-lg border border-border bg-background py-1.5 pl-8 pr-3 text-sm outline-none focus:border-primary"
              />
            </div>
            <select
              value={serverId}
              onChange={(e) => setServerId(e.target.value)}
              className="shrink-0 rounded-lg border border-border bg-background px-2 py-1.5 text-sm outline-none focus:border-primary"
            >
              <option value="">All servers</option>
              {servers.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
          {serverId && (
            <Link
              to={`/reports/server/${serverId}`}
              className="mb-3 flex items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
            >
              <Sparkles className="h-4 w-4" /> Whole-server report
            </Link>
          )}

          {isLoading ? (
            <p className="px-1 py-6 text-sm text-muted-foreground">Loading reports…</p>
          ) : filtered.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border px-4 py-8 text-center">
              <FileText className="mx-auto mb-2 h-7 w-7 text-muted-foreground/50" />
              <p className="text-sm font-medium text-foreground">No reports yet</p>
              <p className="mt-1 text-xs text-muted-foreground">
                When Ally finishes a mission, its report shows up here to export and share.
              </p>
            </div>
          ) : (
            <div className="max-h-[calc(100vh-16rem)] space-y-1.5 overflow-y-auto pr-1">
              {filtered.map((m) => (
                <ReportRow key={m.id} m={m} selected={m.id === shownId} onClick={() => navigate(`/reports/${m.id}`)} />
              ))}
            </div>
          )}
        </aside>

        {/* RIGHT — the selected report's document (first report by default) */}
        <section className="min-w-0 lg:col-span-2">
          {shownId ? (
            <ReportView embedded reportId={shownId} />
          ) : (
            <div className="flex h-40 items-center justify-center rounded-2xl border border-border bg-card/40 text-sm text-muted-foreground">
              Select a report to view it here.
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

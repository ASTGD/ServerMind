import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { formatDistanceToNow } from "date-fns"
import { FileText, Globe, ArrowRight, Search, ShieldCheck, ShieldAlert, Hand, Flag, Square, Sparkles } from "lucide-react"
import { listReports, reportVerdict, reportSubject, type Verdict } from "@/api/reports"
import { listServers } from "@/api/servers"
import { cn } from "@/lib/utils"
import type { MissionSummary } from "@/api/missions"

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
  if (v.label === "Failed") return <Flag className={cls} />
  return <Flag className={cls} />
}

function ReportRow({ m }: { m: MissionSummary }) {
  const v = reportVerdict(m)
  const r = m.result
  const counts = [
    r?.found?.length ? `${r.found.length} found` : null,
    r?.did?.length ? `${r.did.length} done` : null,
    r?.left?.length ? `${r.left.length} for you` : null,
  ].filter(Boolean)
  const when = m.updated_at || m.created_at
  return (
    <Link
      to={`/reports/${m.id}`}
      className="group flex items-start gap-3 rounded-xl border border-border bg-card px-4 py-3 transition-colors hover:border-primary/40 hover:bg-accent/40"
    >
      <span className={cn("mt-0.5 flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold", TONE[v.tone])}>
        <VerdictIcon v={v} /> {v.label}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <Globe className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <span className="truncate">{reportSubject(m)}</span>
          {m.server_name && m.result?.subject && (
            <span className="truncate text-xs font-normal text-muted-foreground">on {m.server_name}</span>
          )}
        </div>
        <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
          {r?.headline || m.summary || m.goal}
        </p>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-muted-foreground">
          {counts.map((c) => (
            <span key={c}>{c}</span>
          ))}
          {counts.length > 0 && <span className="text-border">·</span>}
          <span>{when ? formatDistanceToNow(new Date(when), { addSuffix: true }) : "—"}</span>
        </div>
      </div>
      <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
    </Link>
  )
}

export default function Reports() {
  const { data: reports = [], isLoading } = useQuery({ queryKey: ["reports"], queryFn: () => listReports() })
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers })
  const [serverId, setServerId] = useState("")
  const [q, setQ] = useState("")

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

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search site, goal, outcome…"
            className="w-full rounded-lg border border-border bg-background py-1.5 pl-8 pr-3 text-sm outline-none focus:border-primary"
          />
        </div>
        <select
          value={serverId}
          onChange={(e) => setServerId(e.target.value)}
          className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-sm outline-none focus:border-primary"
        >
          <option value="">All servers</option>
          {servers.map((s) => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>
        {serverId && (
          <Link
            to={`/reports/server/${serverId}`}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <Sparkles className="h-4 w-4" /> Whole-server report
          </Link>
        )}
      </div>
      {serverId && (
        <p className="no-print -mt-2 mb-4 text-xs text-muted-foreground">
          One report summarizing every finished mission on this server — download or share it. Uses 1 AI action.
        </p>
      )}

      {isLoading ? (
        <p className="px-1 py-6 text-sm text-muted-foreground">Loading reports…</p>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center">
          <FileText className="mx-auto mb-2 h-8 w-8 text-muted-foreground/50" />
          <p className="text-sm font-medium text-foreground">No reports yet</p>
          <p className="mt-1 text-xs text-muted-foreground">
            When Ally finishes a mission, its report shows up here to export and share.
          </p>
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {filtered.map((m) => (
            <ReportRow key={m.id} m={m} />
          ))}
        </div>
      )}
    </div>
  )
}

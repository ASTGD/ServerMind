import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { formatDistanceToNow } from "date-fns"
import {
  Rocket, CheckCircle2, XCircle, ShieldCheck, ShieldAlert, Hand, Square, Loader2,
  PlayCircle, Eye, FileText, ScrollText,
} from "lucide-react"
import { listMissions, type MissionSummary, type MissionStatus } from "@/api/missions"
import { isReport } from "@/api/reports"
import { listServers } from "@/api/servers"
import { useAssistantStore, type AssistantTarget } from "@/store/assistantStore"
import RecipeLibrary from "@/components/recipes/RecipeLibrary"

const STATUS: Record<MissionStatus, { label: string; cls: string }> = {
  running: { label: "Running", cls: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
  awaiting_approval: { label: "Awaiting approval", cls: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
  interrupted: { label: "Interrupted", cls: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400" },
  complete: { label: "Complete", cls: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
  blocked: { label: "Blocked", cls: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  failed: { label: "Failed", cls: "bg-red-500/10 text-red-600 dark:text-red-400" },
  stopped: { label: "Stopped", cls: "bg-zinc-500/10 text-zinc-500 dark:text-zinc-400" },
}

/** The status chip — a completed mission also reflects its verification-gate outcome. */
function statusChip(m: MissionSummary) {
  if (m.status === "complete" && m.verified === true)
    return { label: "Verified", cls: STATUS.complete.cls, Icon: ShieldCheck }
  if (m.status === "complete" && m.verified === false)
    return { label: "Unconfirmed", cls: STATUS.blocked.cls, Icon: ShieldAlert }
  const s = STATUS[m.status]
  const Icon =
    m.status === "complete" ? CheckCircle2
    : m.status === "blocked" ? Hand
    : m.status === "failed" ? XCircle
    : m.status === "stopped" ? Square
    : m.status === "interrupted" ? PlayCircle
    : Loader2
  return { label: s.label, cls: s.cls, Icon }
}

export default function Missions() {
  // Poll so a background (running) mission's status updates live on this page.
  const { data: missions = [], isLoading } = useQuery({
    queryKey: ["missions"], queryFn: () => listMissions(), refetchInterval: 5000,
  })
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers })
  const resumeMission = useAssistantStore((s) => s.resumeMission)
  const attachMission = useAssistantStore((s) => s.attachMission)
  const serverById = useMemo(() => new Map(servers.map((s) => [s.id, s])), [servers])

  function targetFor(m: MissionSummary): AssistantTarget | null {
    if (!m.server_id) return { kind: "fleet" }
    const s = serverById.get(m.server_id)
    return s ? { kind: "server", server: s } : null
  }
  function resume(m: MissionSummary) {
    const t = targetFor(m)
    if (t) resumeMission(t, m.id)
  }
  function view(m: MissionSummary) {
    const t = targetFor(m)
    if (t) attachMission(t, m.id)
  }

  const link = "flex items-center gap-1 text-[11px] font-medium text-muted-foreground hover:text-foreground"

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-2 flex items-center gap-2">
        <Rocket size={22} className="text-primary" />
        <h1 className="text-2xl font-semibold text-foreground">Missions</h1>
      </div>
      <p className="mb-6 text-sm text-muted-foreground">
        Every guided mission Ally has run. Open a mission's <span className="text-foreground">Report</span> for the
        shareable outcome, or its <span className="text-foreground">Log</span> for the step-by-step detail. An
        interrupted mission can be resumed from where it left off.
      </p>

      <RecipeLibrary />

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : missions.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card p-10 text-center">
          <Rocket size={28} className="mx-auto mb-3 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">No missions yet. Ask Ally to do a multi-step job and it'll show up here.</p>
        </div>
      ) : (
        <div className="space-y-2.5">
          {missions.map((m) => {
            const chip = statusChip(m)
            return (
              <div key={m.id} className="rounded-xl border border-border bg-card p-4">
                <div className="flex items-start gap-3">
                  <Rocket size={15} className="mt-0.5 shrink-0 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-foreground">{m.goal}</p>
                    <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                      {m.server_name && <span>{m.server_name}</span>}
                      {m.skill && <span>· {m.skill}</span>}
                      <span>· {m.steps_used} step{m.steps_used === 1 ? "" : "s"}</span>
                      {m.created_at && <span>· {formatDistanceToNow(new Date(m.created_at), { addSuffix: true })}</span>}
                    </div>
                    {/* Cross-links — Missions stays high-level; detail lives in Report + Log. */}
                    <div className="mt-2 flex flex-wrap items-center gap-3">
                      {isReport(m) && (
                        <Link to={`/reports/${m.id}`} className={link}>
                          <FileText size={12} /> Report
                        </Link>
                      )}
                      <Link to={`/logs/mission/${m.id}`} className={link}>
                        <ScrollText size={12} /> Log
                      </Link>
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-2">
                    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-medium ${chip.cls}`}>
                      <chip.Icon size={11} /> {chip.label}
                    </span>
                    <div className="flex items-center gap-2">
                      {(m.status === "running" || m.status === "awaiting_approval") && (
                        <button
                          onClick={() => view(m)}
                          disabled={m.server_id ? !serverById.has(m.server_id) : false}
                          title="Watch this background mission live"
                          className="flex items-center gap-1 rounded-lg bg-gradient-to-r from-blue-500 to-indigo-500 px-2.5 py-1 text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-50"
                        >
                          <Eye size={12} /> View
                        </button>
                      )}
                      {m.resumable && (
                        <button
                          onClick={() => resume(m)}
                          disabled={m.server_id ? !serverById.has(m.server_id) : false}
                          title={m.server_id && !serverById.has(m.server_id) ? "Server no longer available" : "Resume this mission"}
                          className="flex items-center gap-1 rounded-lg bg-gradient-to-r from-indigo-500 to-violet-500 px-2.5 py-1 text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-50"
                        >
                          <PlayCircle size={12} /> Resume
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

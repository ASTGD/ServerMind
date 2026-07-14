import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link, useNavigate, useParams } from "react-router-dom"
import { formatDistanceToNow } from "date-fns"
import {
  Rocket, CheckCircle2, XCircle, ShieldCheck, ShieldAlert, Hand, Square, Loader2,
  PlayCircle, FileText, Search, PanelRightOpen, Plus, ArrowLeft, Globe,
} from "lucide-react"
import { listMissions, getMission, type MissionSummary, type MissionStatus } from "@/api/missions"
import { isReport, reportVerdict, reportSubject } from "@/api/reports"
import { listServers } from "@/api/servers"
import { useAssistantStore, type AssistantTarget } from "@/store/assistantStore"
import RecipeLibrary from "@/components/recipes/RecipeLibrary"
import MissionStepList from "@/components/missions/MissionStepList"

const STATUS: Record<MissionStatus, { label: string; cls: string }> = {
  running: { label: "Running", cls: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
  awaiting_approval: { label: "Awaiting approval", cls: "bg-blue-500/10 text-blue-600 dark:text-blue-400" },
  interrupted: { label: "Interrupted", cls: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400" },
  complete: { label: "Complete", cls: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" },
  blocked: { label: "Blocked", cls: "bg-amber-500/10 text-amber-600 dark:text-amber-400" },
  failed: { label: "Failed", cls: "bg-red-500/10 text-red-600 dark:text-red-400" },
  stopped: { label: "Stopped", cls: "bg-zinc-500/10 text-zinc-500 dark:text-zinc-400" },
}

/** Missions that still want the user's attention sit above finished ones. */
const ACTIVE: MissionStatus[] = ["running", "awaiting_approval", "blocked", "interrupted"]

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

/** A selectable receipt row in the left list. */
function MissionRow({ m, selected, onClick }: { m: MissionSummary; selected: boolean; onClick: () => void }) {
  const chip = statusChip(m)
  return (
    <button
      onClick={onClick}
      className={`block w-full rounded-lg border bg-card p-2.5 text-left transition hover:border-primary/40 ${
        selected ? "border-primary ring-1 ring-primary/40" : "border-border"
      }`}
    >
      <div className="flex items-center gap-2">
        <chip.Icon size={14} className="shrink-0 text-muted-foreground" />
        <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-foreground">{m.goal}</span>
      </div>
      <div className="mt-1.5 flex items-center justify-between gap-2 pl-6">
        <span className="truncate text-[11px] text-muted-foreground">
          {m.server_name ? `${m.server_name} · ` : ""}{m.steps_used} step{m.steps_used === 1 ? "" : "s"}
          {m.created_at ? ` · ${formatDistanceToNow(new Date(m.created_at), { addSuffix: true })}` : ""}
        </span>
        <span className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium ${chip.cls}`}>
          {chip.label}
        </span>
      </div>
    </button>
  )
}

const TONE: Record<string, { chip: string; head: string; bar: string }> = {
  good: { chip: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400", head: "text-emerald-600 dark:text-emerald-400", bar: "border-emerald-500/40" },
  warn: { chip: "bg-amber-500/10 text-amber-600 dark:text-amber-400", head: "text-amber-600 dark:text-amber-400", bar: "border-amber-500/40" },
  bad: { chip: "bg-red-500/10 text-red-600 dark:text-red-400", head: "text-red-600 dark:text-red-400", bar: "border-red-500/40" },
  neutral: { chip: "bg-zinc-500/10 text-zinc-500 dark:text-zinc-400", head: "text-zinc-500", bar: "border-zinc-500/40" },
}

function ResultBlock({ label, items, color }: { label: string; items: string[]; color: string }) {
  if (!items?.length) return null
  return (
    <div className="mt-3">
      <p className="mb-1 text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <ul className="space-y-1">
        {items.map((it, i) => (
          <li key={i} className="flex items-start gap-1.5 text-[13px] text-foreground">
            <span className={color}>•</span>
            <span>{it}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** The right-hand detail: header + result receipt + step log + actions. */
function MissionDetail({ id, onServerFor }: { id: string; onServerFor: (m: MissionSummary) => AssistantTarget | null }) {
  const navigate = useNavigate()
  const resumeMission = useAssistantStore((s) => s.resumeMission)
  const attachMission = useAssistantStore((s) => s.attachMission)
  const { data: m, isLoading, isError } = useQuery({
    queryKey: ["mission", id],
    queryFn: () => getMission(id),
    // Keep a running mission's transcript fresh while it's open.
    refetchInterval: (q) => (["running", "awaiting_approval"].includes((q.state.data?.status ?? "")) ? 4000 : false),
  })

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading mission…</p>
  if (isError || !m) return <p className="text-sm text-muted-foreground">Mission not found.</p>

  const target = onServerFor(m)
  const serverGone = m.server_id != null && target == null
  const v = reportVerdict(m)
  const tone = TONE[v.tone]
  const r = m.result

  return (
    <div>
      <button onClick={() => navigate("/missions")} className="mb-3 inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft size={13} /> Recipes
      </button>

      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="line-clamp-3 text-base font-semibold leading-snug text-foreground" title={m.goal}>{m.goal}</h2>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
            {(r?.subject || m.server_name) && (
              <span className="inline-flex items-center gap-1">
                <Globe size={11} /> {reportSubject(m)}
              </span>
            )}
            {m.skill && <span>· {m.skill}</span>}
            <span>· {(m.steps ?? []).length} step{(m.steps ?? []).length === 1 ? "" : "s"}</span>
            {m.created_at && <span>· {formatDistanceToNow(new Date(m.created_at), { addSuffix: true })}</span>}
          </div>
        </div>
        <span className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-medium ${tone.chip}`}>
          {v.label}
        </span>
      </div>

      {/* Result receipt */}
      {(r || m.summary) && (
        <div className={`mt-3 rounded-xl border border-l-4 bg-card p-3.5 ${tone.bar}`}>
          <p className={`text-[11px] font-semibold uppercase tracking-wide ${tone.head}`}>Result</p>
          {r?.headline && <p className="mt-1 text-[13px] font-medium text-foreground">{r.headline}</p>}
          {!r && m.summary && <p className="mt-1 text-[13px] text-foreground">{m.summary}</p>}
          {r && (
            <>
              <ResultBlock label="Found" items={r.found} color="text-red-500" />
              <ResultBlock label="Ally did" items={r.did} color="text-emerald-500" />
              <ResultBlock label="Left for you" items={r.left} color="text-amber-500" />
            </>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          onClick={() => target && attachMission(target, m.id)}
          disabled={serverGone}
          title={serverGone ? "Server no longer available" : "Open this session in the Ally workspace"}
          className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-blue-500 to-indigo-500 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          <PanelRightOpen size={13} /> Open in Ally workspace
        </button>
        {m.resumable && (
          <button
            onClick={() => target && resumeMission(target, m.id)}
            disabled={serverGone}
            className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-indigo-500 to-violet-500 px-3 py-1.5 text-xs font-medium text-white hover:opacity-90 disabled:opacity-50"
          >
            <PlayCircle size={13} /> Resume
          </button>
        )}
        {isReport(m) && (
          <Link
            to={`/reports/${m.id}`}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent"
          >
            <FileText size={13} /> Report
          </Link>
        )}
      </div>

      {/* Step log */}
      <p className="mb-1.5 mt-5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Log</p>
      <MissionStepList steps={m.steps ?? []} />
      <p className="mt-2 px-1 text-[11px] text-muted-foreground">Secrets in commands and output are masked.</p>
    </div>
  )
}

export default function Missions() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [q, setQ] = useState("")

  // Poll so a background (running) mission's status updates live in the list.
  const { data: missions = [], isLoading } = useQuery({
    queryKey: ["missions"], queryFn: () => listMissions(), refetchInterval: 5000,
  })
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers })
  const serverById = useMemo(() => new Map(servers.map((s) => [s.id, s])), [servers])

  function targetFor(m: MissionSummary): AssistantTarget | null {
    if (!m.server_id) return { kind: "fleet" }
    const s = serverById.get(m.server_id)
    return s ? { kind: "server", server: s } : null
  }

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    if (!needle) return missions
    return missions.filter(
      (m) => m.goal.toLowerCase().includes(needle) || (m.server_name ?? "").toLowerCase().includes(needle),
    )
  }, [missions, q])
  const active = filtered.filter((m) => ACTIVE.includes(m.status))
  const history = filtered.filter((m) => !ACTIVE.includes(m.status))

  return (
    <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6">
      <div className="mb-4 flex items-center gap-2">
        <Rocket size={20} className="text-primary" />
        <h1 className="text-xl font-semibold text-foreground">Missions</h1>
      </div>

      <div className="flex flex-col gap-4 md:flex-row md:items-start">
        {/* LEFT — the mission list (receipts) */}
        <aside className="w-full shrink-0 md:w-[288px]">
          <button
            onClick={() => navigate("/missions")}
            className="mb-2.5 flex w-full items-center justify-center gap-1.5 rounded-lg bg-gradient-to-r from-blue-500 to-indigo-500 px-3 py-2 text-[13px] font-medium text-white hover:opacity-90"
          >
            <Plus size={14} /> New mission
          </button>
          <div className="relative mb-3">
            <Search size={14} className="absolute left-2.5 top-2.5 text-muted-foreground" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search missions"
              className="w-full rounded-lg border border-border bg-card py-2 pl-8 pr-2 text-xs text-foreground placeholder:text-muted-foreground focus:border-primary/50 focus:outline-none"
            />
          </div>

          {isLoading ? (
            <p className="px-1 text-xs text-muted-foreground">Loading…</p>
          ) : missions.length === 0 ? (
            <p className="px-1 text-xs text-muted-foreground">No missions yet. Pick a recipe to start.</p>
          ) : (
            <div className="max-h-[calc(100vh-14rem)] space-y-3 overflow-y-auto pr-1">
              {active.length > 0 && (
                <div>
                  <p className="mb-1.5 px-1 text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">Needs you</p>
                  <div className="space-y-1.5">
                    {active.map((m) => (
                      <MissionRow key={m.id} m={m} selected={m.id === id} onClick={() => navigate(`/missions/${m.id}`)} />
                    ))}
                  </div>
                </div>
              )}
              {history.length > 0 && (
                <div>
                  <p className="mb-1.5 px-1 text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">History</p>
                  <div className="space-y-1.5">
                    {history.map((m) => (
                      <MissionRow key={m.id} m={m} selected={m.id === id} onClick={() => navigate(`/missions/${m.id}`)} />
                    ))}
                  </div>
                </div>
              )}
              {active.length === 0 && history.length === 0 && (
                <p className="px-1 text-xs text-muted-foreground">No missions match “{q}”.</p>
              )}
            </div>
          )}
        </aside>

        {/* RIGHT — recipes by default, mission detail when one is selected */}
        <section className="min-w-0 flex-1 rounded-2xl border border-border bg-card/40 p-4 sm:p-5">
          {id ? <MissionDetail id={id} onServerFor={targetFor} /> : <RecipeLibrary />}
        </section>
      </div>
    </div>
  )
}

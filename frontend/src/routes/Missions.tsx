import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import {
  Rocket, CheckCircle2, XCircle, ShieldCheck, ShieldAlert, Hand, Square, Loader2,
  PlayCircle, ChevronDown, ChevronRight,
} from "lucide-react"
import { listMissions, getMission, type MissionSummary, type MissionStatus } from "@/api/missions"
import { listServers } from "@/api/servers"
import { useAssistantStore } from "@/store/assistantStore"

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

function StepList({ missionId }: { missionId: string }) {
  const { data, isLoading } = useQuery({ queryKey: ["mission", missionId], queryFn: () => getMission(missionId) })
  const [openIdx, setOpenIdx] = useState<number | null>(null)
  if (isLoading) return <p className="px-4 py-3 text-xs text-muted-foreground">Loading steps…</p>
  const steps = data?.steps ?? []
  return (
    <div className="space-y-1 border-t border-border bg-muted/30 px-4 py-3">
      {data?.summary && <p className="mb-2 text-xs text-muted-foreground">{data.summary}</p>}
      {steps.length === 0 && <p className="text-xs text-muted-foreground">No steps recorded.</p>}
      {steps.map((s, i) => {
        const ok = (s.exit_code ?? 0) === 0
        const hasDetail = Boolean(s.output_tail || s.cmd)
        return (
          <div key={i} className="text-xs">
            <button
              onClick={() => hasDetail && setOpenIdx(openIdx === i ? null : i)}
              className={`flex w-full items-start gap-1.5 text-left ${hasDetail ? "cursor-pointer" : "cursor-default"}`}
            >
              <span className="mt-0.5">
                {ok ? <CheckCircle2 size={12} className="text-emerald-500" /> : <XCircle size={12} className="text-red-500" />}
              </span>
              <span className="min-w-0 flex-1">
                {s.verify && <span className="mr-1.5 rounded bg-violet-500/10 px-1 py-px text-[10px] font-medium text-violet-600 dark:text-violet-400">verify</span>}
                {s.server && <span className="mr-1.5 rounded bg-indigo-500/10 px-1 py-px text-[10px] font-medium text-indigo-600 dark:text-indigo-400">{s.server}</span>}
                <span className="text-foreground">{s.description || s.cmd}</span>
                {s.note && <span className="ml-1 text-amber-600 dark:text-amber-400">({s.note})</span>}
              </span>
              {hasDetail && <span className="mt-0.5 shrink-0 text-muted-foreground">{openIdx === i ? <ChevronDown size={11} /> : <ChevronRight size={11} />}</span>}
            </button>
            {openIdx === i && (
              <div className="ml-4 mt-1 space-y-1">
                {s.cmd && <pre className="overflow-x-auto rounded bg-[#0d0d0d] px-2 py-1 font-mono text-[11px] text-zinc-300">$ {s.cmd}</pre>}
                {s.output_tail && <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all rounded bg-[#0d0d0d] px-2 py-1 font-mono text-[11px] text-zinc-400">{s.output_tail}</pre>}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function Missions() {
  const { data: missions = [], isLoading } = useQuery({ queryKey: ["missions"], queryFn: () => listMissions() })
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers })
  const resumeMission = useAssistantStore((s) => s.resumeMission)
  const [expanded, setExpanded] = useState<string | null>(null)
  const serverById = useMemo(() => new Map(servers.map((s) => [s.id, s])), [servers])

  function resume(m: MissionSummary) {
    if (m.server_id) {
      const s = serverById.get(m.server_id)
      if (s) resumeMission({ kind: "server", server: s }, m.id)
    } else {
      resumeMission({ kind: "fleet" }, m.id)
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-6 flex items-center gap-2">
        <Rocket size={22} className="text-primary" />
        <h1 className="text-2xl font-semibold text-foreground">Missions</h1>
      </div>
      <p className="mb-6 text-sm text-muted-foreground">
        Every guided mission Ally has run — what it did, and how it ended. An interrupted
        mission (a dropped connection) can be resumed from where it left off.
      </p>

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
            const isOpen = expanded === m.id
            return (
              <div key={m.id} className="overflow-hidden rounded-xl border border-border bg-card">
                <div className="flex items-start gap-3 p-4">
                  <button onClick={() => setExpanded(isOpen ? null : m.id)} className="mt-0.5 shrink-0 text-muted-foreground">
                    {isOpen ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
                  </button>
                  <div className="min-w-0 flex-1">
                    <button onClick={() => setExpanded(isOpen ? null : m.id)} className="block text-left">
                      <span className="text-sm font-medium text-foreground">{m.goal}</span>
                    </button>
                    <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                      {m.server_name && <span>{m.server_name}</span>}
                      {m.skill && <span>· {m.skill}</span>}
                      <span>· {m.steps_used} step{m.steps_used === 1 ? "" : "s"}</span>
                      {m.created_at && <span>· {formatDistanceToNow(new Date(m.created_at), { addSuffix: true })}</span>}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-medium ${chip.cls}`}>
                      <chip.Icon size={11} /> {chip.label}
                    </span>
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
                {isOpen && <StepList missionId={m.id} />}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { Sparkles, ShieldCheck, ArrowRight, CircleAlert, MessageSquare } from "lucide-react"
import { getFleetHealth, type ServerHealth, type FleetFinding } from "@/api/fleet"
import { listServers } from "@/api/servers"
import { useAssistantStore } from "@/store/assistantStore"

const SEV: Record<string, string> = {
  critical: "bg-red-500",
  high: "bg-orange-500",
  medium: "bg-amber-500",
  low: "bg-blue-500",
  info: "bg-zinc-400",
}

function gradeCls(grade: string): string {
  return grade === "A" || grade === "B"
    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
    : grade === "C"
      ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
      : "bg-red-500/10 text-red-600 dark:text-red-400"
}

/**
 * Proactive fleet intelligence: Ally's at-a-glance take on what needs attention across
 * the whole fleet, each item with a one-click fix (open Ally with a prompt, or jump to
 * the right page). Deterministic + cheap — refreshed from the existing signals.
 */
export default function FleetReport() {
  const navigate = useNavigate()
  const openServer = useAssistantStore((s) => s.openServer)
  const { data, isLoading } = useQuery({
    queryKey: ["fleet-health"],
    queryFn: getFleetHealth,
    refetchInterval: 30_000,
  })
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers })
  const serverById = useMemo(() => new Map(servers.map((s) => [s.id, s])), [servers])

  if (isLoading || !data) return null
  // Show every server with something worth doing, worst-first (the backend sorts it);
  // the header chip surfaces the count that's genuinely urgent.
  const withFindings = data.servers.filter((s) => s.findings.length > 0)
  const healthy = data.servers.length - withFindings.length
  const urgent = data.summary.needs_attention

  function act(finding: FleetFinding, serverId: string) {
    const a = finding.action
    if (a.kind === "chat" && a.seed) {
      const s = serverById.get(serverId)
      if (s) openServer(s, a.seed)
    } else if (a.kind === "page" && a.path) {
      navigate(a.path)
    }
  }

  return (
    <div className="rounded-2xl border border-border bg-card p-5">
      <div className="mb-4 flex items-center gap-2">
        <Sparkles size={17} className="text-primary" />
        <h2 className="text-sm font-semibold text-foreground">Ally's fleet report</h2>
        {urgent > 0 && (
          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">
            {urgent} need{urgent === 1 ? "s" : ""} attention
          </span>
        )}
      </div>

      {withFindings.length === 0 ? (
        <div className="flex items-center gap-2.5 rounded-xl bg-emerald-500/5 px-4 py-3 text-sm text-emerald-700 dark:text-emerald-400">
          <ShieldCheck size={18} className="shrink-0" />
          <span>Everything looks healthy — nothing needs your attention right now.</span>
        </div>
      ) : (
        <>
          <div className="space-y-3">
            {withFindings.map((s) => (
              <ServerCard key={s.server_id} s={s} onAct={(f) => act(f, s.server_id)} />
            ))}
          </div>
          {healthy > 0 && (
            <p className="mt-3 flex items-center gap-1.5 text-xs text-muted-foreground">
              <ShieldCheck size={13} className="text-emerald-500" />
              {healthy} other server{healthy === 1 ? "" : "s"} look{healthy === 1 ? "s" : ""} healthy.
            </p>
          )}
        </>
      )}
    </div>
  )
}

function ServerCard({ s, onAct }: { s: ServerHealth; onAct: (f: FleetFinding) => void }) {
  return (
    <div className="rounded-xl border border-border p-3.5">
      <div className="mb-2.5 flex items-center gap-2">
        <span className={`flex h-7 w-9 items-center justify-center rounded-md text-xs font-bold ${gradeCls(s.grade)}`}>
          {s.grade}
        </span>
        <span className="text-sm font-medium text-foreground">{s.name}</span>
        <span className="text-xs text-muted-foreground">· {s.score}/100</span>
        {s.status === "offline" && (
          <span className="rounded bg-red-500/10 px-1.5 py-0.5 text-[10px] font-medium text-red-600 dark:text-red-400">offline</span>
        )}
      </div>
      <div className="space-y-2">
        {s.findings.map((f) => (
          <div key={f.id} className="flex items-start gap-2.5">
            <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${SEV[f.severity] ?? SEV.info}`} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground">{f.title}</p>
              <p className="text-xs text-muted-foreground">{f.detail}</p>
            </div>
            <button
              onClick={() => onAct(f)}
              className="flex shrink-0 items-center gap-1 rounded-lg border border-border px-2.5 py-1 text-[11px] font-medium text-foreground hover:bg-accent"
            >
              {f.action.kind === "chat" ? <MessageSquare size={11} /> : <CircleAlert size={11} />}
              {f.action.label}
              <ArrowRight size={11} className="text-muted-foreground" />
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

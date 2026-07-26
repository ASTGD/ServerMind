import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import { Siren, CircleCheck, Hand, Loader2, BellOff } from "lucide-react"
import {
  listIncidents, acknowledgeIncident, resolveIncident, type Incident,
} from "@/api/escalation"
import { Button } from "@/components/ui"
import { cn } from "@/lib/utils"

const SEVERITY: Record<string, string> = {
  critical: "bg-red-500/15 text-red-700 dark:text-red-300",
  high: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  warning: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  info: "bg-muted text-muted-foreground",
}

const SOURCE_LABEL: Record<string, string> = {
  uptime: "Site down",
  threat: "Security",
  metric: "Resources",
  ssl: "Certificate",
  manual: "Manual",
}

function ago(iso: string | null): string {
  if (!iso) return "—"
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true })
  } catch {
    return "—"
  }
}

function Row({ incident, onAck, onResolve, busy }: {
  incident: Incident
  onAck: () => void
  onResolve: () => void
  busy: boolean
}) {
  const open = incident.status === "open"
  return (
    <li className={cn(
      "rounded-xl border p-3",
      open ? "border-red-500/40 bg-red-500/[0.04]" : "border-border",
    )}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-1.5">
            <span className={cn("rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase",
              SEVERITY[incident.severity] ?? SEVERITY.info)}>
              {incident.severity}
            </span>
            <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
              {SOURCE_LABEL[incident.source] ?? incident.source}
            </span>
            <span className="text-[13px] font-medium">{incident.title}</span>
          </p>
          <p className="mt-1 text-[11.5px] text-muted-foreground">
            Started {ago(incident.created_at)}
            {incident.server_name && ` · ${incident.server_name}`}
            {incident.notifications_sent > 0 &&
              ` · ${incident.notifications_sent} alert${incident.notifications_sent === 1 ? "" : "s"} sent`}
            {incident.status === "acknowledged" && incident.acknowledged_by &&
              ` · ${incident.acknowledged_by} is on it`}
            {incident.status === "resolved" &&
              ` · ${incident.auto_resolved ? "fixed itself" : "resolved"} ${ago(incident.resolved_at)}`}
          </p>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          {open && (
            <Button size="sm" variant="outline" disabled={busy} onClick={onAck}>
              {busy ? <Loader2 size={13} className="animate-spin" /> : <Hand size={13} />}
              I’ve got it
            </Button>
          )}
          {incident.status !== "resolved" && (
            <Button size="sm" variant="ghost" disabled={busy} onClick={onResolve}>
              <CircleCheck size={13} /> Resolved
            </Button>
          )}
          {incident.status === "resolved" && (
            <span className="flex items-center gap-1 text-[11px] text-emerald-700 dark:text-emerald-400">
              <CircleCheck size={13} /> Closed
            </span>
          )}
        </div>
      </div>

      {open && incident.next_action_at && (
        <p className="mt-2 flex items-center gap-1.5 text-[11px] text-red-700 dark:text-red-400">
          <Siren size={11} /> Next alert {ago(incident.next_action_at)} — acknowledging stops it
        </p>
      )}
      {open && !incident.next_action_at && incident.notifications_sent > 0 && (
        <p className="mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <BellOff size={11} /> Everyone in the policy has been alerted; no more will be sent
        </p>
      )}
    </li>
  )
}

/**
 * Live incidents. Shows what is escalating right now, and gives the one button that
 * stops it.
 */
export default function IncidentsPanel({ compact = false }: { compact?: boolean }) {
  const qc = useQueryClient()
  const { data: incidents = [], isLoading } = useQuery({
    queryKey: ["incidents", "active"],
    queryFn: () => listIncidents("active"),
    // Something escalating changes minute by minute; the panel should keep up.
    refetchInterval: 30_000,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ["incidents"] })
  const ack = useMutation({ mutationFn: acknowledgeIncident, onSuccess: invalidate })
  const resolve = useMutation({ mutationFn: resolveIncident, onSuccess: invalidate })
  const busyId = ack.variables ?? resolve.variables

  const shown = compact ? incidents.slice(0, 3) : incidents

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <Siren size={15} className={incidents.some((i) => i.status === "open")
          ? "text-red-600 dark:text-red-400" : "text-primary"} />
        <h3 className="text-sm font-semibold">Live incidents</h3>
        {incidents.length > 0 && (
          <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
            {incidents.length}
          </span>
        )}
      </div>

      {isLoading ? (
        <p className="py-4 text-center text-xs text-muted-foreground">Loading…</p>
      ) : shown.length === 0 ? (
        <p className="rounded-lg border border-dashed border-border px-3 py-5 text-center text-xs text-muted-foreground">
          Nothing needs your attention right now.
        </p>
      ) : (
        <ul className="space-y-2">
          {shown.map((incident) => (
            <Row
              key={incident.id} incident={incident}
              busy={(ack.isPending || resolve.isPending) && busyId === incident.id}
              onAck={() => ack.mutate(incident.id)}
              onResolve={() => resolve.mutate(incident.id)}
            />
          ))}
        </ul>
      )}
    </div>
  )
}

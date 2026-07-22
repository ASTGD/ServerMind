import { Rocket, Play, ShieldCheck, ListChecks, Server as ServerIcon } from "lucide-react"

export interface MissionOffer {
  goal: string
  skill: string | null
  message: string
  /** The server the mission starts on — null for a fleet mission that may span servers. */
  serverId?: string | null
  serverName?: string | null
  started?: boolean
}

/** A mission offer from Ally — a multi-step job the user starts with ONE click.
 *  Risky steps still pause for approval during the mission (docs/ALLY-MISSIONS.md). */
export default function MissionCard({
  offer,
  onStart,
}: {
  offer: MissionOffer
  onStart: (offer: MissionOffer) => void
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-indigo-500/25 bg-indigo-500/5">
      <div className="flex items-center gap-2 border-b border-indigo-500/15 px-3.5 py-2.5">
        <Rocket size={16} className="shrink-0 text-primary" />
        <span className="text-sm font-medium text-foreground">Mission</span>
        <span className="flex items-center gap-1 rounded border border-border bg-background px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
          <ServerIcon size={10} />
          {offer.serverName ?? "across your servers"}
        </span>
        {offer.skill && (
          <span className="rounded border border-border bg-background px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
            runbook: {offer.skill}
          </span>
        )}
      </div>
      <div className="space-y-3 px-3.5 py-3">
        <p className="rounded-lg bg-background px-3 py-2 text-sm text-muted-foreground">
          Goal: <span className="text-foreground">{offer.goal}</span>
        </p>
        <div className="flex items-center gap-3.5 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <ListChecks size={12} /> step-by-step, adapts as it goes
          </span>
          <span className="flex items-center gap-1">
            <ShieldCheck size={12} /> risky steps still ask you first
          </span>
        </div>
        <button
          onClick={() => onStart(offer)}
          disabled={offer.started}
          className="flex items-center gap-1.5 rounded-lg bg-brand-gradient-r px-3.5 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          <Play size={14} />
          {offer.started ? "Mission started" : "Start mission"}
        </button>
      </div>
    </div>
  )
}

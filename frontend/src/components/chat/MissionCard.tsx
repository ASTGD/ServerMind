import { Rocket, Play, ShieldCheck, ListChecks } from "lucide-react"

export interface MissionOffer {
  goal: string
  skill: string | null
  message: string
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
      <div className="flex items-center gap-2 border-b border-indigo-500/15 px-3 py-2">
        <Rocket size={15} className="shrink-0 text-primary" />
        <span className="text-sm font-medium text-foreground">Mission</span>
        {offer.skill && (
          <span className="rounded border border-border bg-background px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
            runbook: {offer.skill}
          </span>
        )}
      </div>
      <div className="space-y-2.5 px-3 py-2.5">
        {offer.message && <p className="text-sm text-foreground">{offer.message}</p>}
        <p className="rounded-lg bg-background px-2.5 py-1.5 text-xs text-muted-foreground">
          Goal: <span className="text-foreground">{offer.goal}</span>
        </p>
        <div className="flex items-center gap-3 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <ListChecks size={11} /> step-by-step, adapts as it goes
          </span>
          <span className="flex items-center gap-1">
            <ShieldCheck size={11} /> risky steps still ask you first
          </span>
        </div>
        <button
          onClick={() => onStart(offer)}
          disabled={offer.started}
          className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-indigo-500 to-violet-500 px-3 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          <Play size={13} />
          {offer.started ? "Mission started" : "Start mission"}
        </button>
      </div>
    </div>
  )
}

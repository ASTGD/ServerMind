import { Shield, ShieldAlert, ShieldCheck, Clock, ChevronRight } from "lucide-react"
import { cn } from "@/lib/utils"
import { useTranslation } from "react-i18next"
import ServerTag from "./ServerTag"
import type { CommandItem } from "@/types"

interface Props {
  planSummary: string
  commands: CommandItem[]
  requiresApproval: boolean
  riskLevel: string
  estimatedSeconds: number
  /** Which server this plan will run on — shown so an approval can never be
   *  mistaken for another server (the unified socket keeps plans alive across
   *  target switches; the backend binds the approval to this server anyway). */
  serverName?: string | null
  onApprove: () => void
  onCancel: () => void
}

const riskIcon = {
  low: <ShieldCheck size={14} className="text-green-500" />,
  medium: <Shield size={14} className="text-yellow-500" />,
  high: <ShieldAlert size={14} className="text-red-500" />,
}

const riskColor = {
  low: "border-green-500/20 bg-green-500/5",
  medium: "border-yellow-500/20 bg-yellow-500/5",
  high: "border-red-500/20 bg-red-500/5",
}

function formatDuration(s: number): string {
  if (s < 60) return `~${s}s`
  return `~${Math.round(s / 60)}m`
}

export default function CommandPlan({
  planSummary,
  commands,
  requiresApproval,
  riskLevel,
  estimatedSeconds,
  serverName,
  onApprove,
  onCancel,
}: Props) {
  const { t } = useTranslation()
  const risk = (riskLevel as keyof typeof riskIcon) in riskIcon ? riskLevel as keyof typeof riskIcon : "low"

  return (
    <div className={cn("rounded-xl border p-4 space-y-3", riskColor[risk])}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {serverName && <div className="mb-1"><ServerTag name={serverName} /></div>}
          <p className="text-sm font-medium text-foreground">{planSummary}</p>
        </div>
        <div className="flex items-center gap-3 shrink-0 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Clock size={12} />
            {formatDuration(estimatedSeconds)}
          </span>
          <span className="flex items-center gap-1">
            {riskIcon[risk]}
            <span className="capitalize">{risk} risk</span>
          </span>
        </div>
      </div>

      {/* Commands */}
      <ol className="space-y-1.5">
        {commands.map((cmd, idx) => (
          <li key={idx} className="flex items-start gap-2 text-xs">
            <ChevronRight size={12} className="mt-0.5 shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <code className="block break-all rounded bg-background/60 px-1.5 py-0.5 font-mono text-foreground">
                {cmd.cmd}
              </code>
              <span className="text-muted-foreground">{cmd.description}</span>
            </div>
          </li>
        ))}
      </ol>

      {/* Actions */}
      {requiresApproval && (
        <div className="flex items-center gap-2 pt-1">
          <button
            onClick={onApprove}
            className="flex-1 rounded-lg bg-primary py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
          >
            {t("chat.approve")}
          </button>
          <button
            onClick={onCancel}
            className="flex-1 rounded-lg border border-border py-1.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            {t("chat.cancel")}
          </button>
        </div>
      )}
    </div>
  )
}

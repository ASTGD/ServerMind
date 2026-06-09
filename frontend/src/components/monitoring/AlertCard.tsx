import { Bell, BellOff, Trash2, Play, Mail, Globe, Slack } from "lucide-react"
import type { Alert } from "@/types"
import { formatDistanceToNow } from "date-fns"

interface Props {
  alert: Alert
  onToggle: (id: string) => void
  onDelete: (id: string) => void
  onTest: (id: string) => void
  isTestPending?: boolean
}

const METRIC_LABEL: Record<string, string> = {
  cpu: "CPU Usage",
  ram: "RAM Usage",
  disk: "Disk Usage",
}

const CONDITION_LABEL: Record<string, string> = {
  gt: "above",
  gte: "at or above",
  lt: "below",
  lte: "at or below",
}

const CHANNEL_ICON: Record<string, React.ReactNode> = {
  email: <Mail className="h-3.5 w-3.5" />,
  webhook: <Globe className="h-3.5 w-3.5" />,
  slack: <Slack className="h-3.5 w-3.5" />,
}

function metricColor(metric: string | null): string {
  if (metric === "cpu") return "text-emerald-400"
  if (metric === "ram") return "text-blue-400"
  if (metric === "disk") return "text-violet-400"
  return "text-foreground"
}

export default function AlertCard({
  alert,
  onToggle,
  onDelete,
  onTest,
  isTestPending = false,
}: Props) {
  return (
    <div
      className={`rounded-xl border bg-card p-4 flex flex-col gap-3 transition-all ${
        alert.is_active ? "border-border" : "border-border/40 opacity-60"
      }`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1">
            <span className={`text-xs font-semibold ${metricColor(alert.metric)}`}>
              {METRIC_LABEL[alert.metric ?? ""] ?? alert.metric}
            </span>
            {!alert.is_active && (
              <span className="text-[10px] text-muted-foreground border border-border rounded px-1.5 py-0.5">
                Paused
              </span>
            )}
          </div>
          <p className="text-sm text-foreground font-medium">
            Alert when{" "}
            <span className={metricColor(alert.metric)}>
              {METRIC_LABEL[alert.metric ?? ""] ?? alert.metric}
            </span>{" "}
            is{" "}
            <span className="text-foreground">
              {CONDITION_LABEL[alert.condition ?? ""] ?? alert.condition}{" "}
              {alert.threshold != null ? `${alert.threshold}%` : "—"}
            </span>
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => onTest(alert.id)}
            disabled={isTestPending}
            title="Send test notification"
            className="p-1.5 rounded text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors disabled:opacity-40"
          >
            <Play className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => onToggle(alert.id)}
            title={alert.is_active ? "Pause alert" : "Resume alert"}
            className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
          >
            {alert.is_active ? (
              <BellOff className="h-3.5 w-3.5" />
            ) : (
              <Bell className="h-3.5 w-3.5" />
            )}
          </button>
          <button
            onClick={() => onDelete(alert.id)}
            title="Delete alert"
            className="p-1.5 rounded text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Channel & last triggered */}
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5 text-muted-foreground">
          {CHANNEL_ICON[alert.channel ?? ""] ?? <Bell className="h-3.5 w-3.5" />}
          <span className="truncate max-w-[180px]">{alert.channel_target}</span>
        </div>
        {alert.last_triggered ? (
          <span className="text-muted-foreground/60 shrink-0">
            Last fired {formatDistanceToNow(new Date(alert.last_triggered), { addSuffix: true })}
          </span>
        ) : (
          <span className="text-muted-foreground/40 shrink-0">Never fired</span>
        )}
      </div>
    </div>
  )
}

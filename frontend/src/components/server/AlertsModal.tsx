import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { X, Bell, Plus, Loader2, AlertTriangle, ChevronDown } from "lucide-react"
import {
  listAlerts,
  createAlert,
  deleteAlert,
  toggleAlert,
  testAlert,
  type AlertCreateBody,
} from "@/api/monitoring"
import AlertCard from "@/components/monitoring/AlertCard"

type AlertMetric = "cpu" | "ram" | "disk"
type AlertCondition = "gt" | "gte" | "lt" | "lte"
type AlertChannel = "email" | "webhook" | "slack"

const METRIC_OPTIONS: { value: AlertMetric; label: string }[] = [
  { value: "cpu", label: "CPU usage" },
  { value: "ram", label: "RAM usage" },
  { value: "disk", label: "Disk usage" },
]
const CONDITION_OPTIONS: { value: AlertCondition; label: string }[] = [
  { value: "gt", label: "is above" },
  { value: "gte", label: "is at or above" },
  { value: "lt", label: "is below" },
  { value: "lte", label: "is at or below" },
]
const CHANNEL_OPTIONS: { value: AlertChannel; label: string; placeholder: string }[] = [
  { value: "email", label: "Email", placeholder: "you@example.com" },
  { value: "webhook", label: "Webhook", placeholder: "https://hooks.example.com/..." },
  { value: "slack", label: "Slack", placeholder: "https://hooks.slack.com/services/..." },
]

const selectCls =
  "w-full appearance-none rounded-lg border border-border bg-background px-3 py-2 pr-7 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"

/** Manage threshold alert rules for a server (folded out of the old Monitoring page). */
export default function AlertsModal({ serverId, onClose }: { serverId: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)
  const [metric, setMetric] = useState<AlertMetric>("cpu")
  const [condition, setCondition] = useState<AlertCondition>("gt")
  const [threshold, setThreshold] = useState("85")
  const [channel, setChannel] = useState<AlertChannel>("email")
  const [target, setTarget] = useState("")

  const { data: alerts = [], isLoading } = useQuery({
    queryKey: ["alerts", serverId],
    queryFn: () => listAlerts(serverId),
  })
  const createMut = useMutation({
    mutationFn: (body: AlertCreateBody) => createAlert(serverId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts", serverId] })
      setAdding(false)
      setTarget("")
    },
  })
  const deleteMut = useMutation({
    mutationFn: deleteAlert,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts", serverId] }),
  })
  const toggleMut = useMutation({
    mutationFn: toggleAlert,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts", serverId] }),
  })
  async function handleTest(id: string) {
    setTestingId(id)
    try {
      await testAlert(id)
    } finally {
      setTestingId(null)
    }
  }

  const channelMeta = CHANNEL_OPTIONS.find((c) => c.value === channel)!
  const canSubmit = target.trim() !== "" && +threshold >= 0 && +threshold <= 100

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl border border-border bg-card shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-2">
            <Bell className="h-4 w-4 text-foreground" />
            <h2 className="font-semibold text-foreground">Alerts</h2>
            {alerts.length > 0 && (
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">{alerts.length}</span>
            )}
          </div>
          <button onClick={onClose} aria-label="Close" className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4 overflow-y-auto px-6 py-4">
          <p className="text-sm text-muted-foreground">
            Get notified when CPU, RAM, or disk crosses a threshold.
          </p>

          {isLoading ? (
            <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading alerts…
            </div>
          ) : alerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-10 text-center">
              <Bell className="mb-2 h-7 w-7 text-muted-foreground/30" />
              <p className="text-sm text-muted-foreground">No alert rules yet</p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {alerts.map((alert) => (
                <AlertCard
                  key={alert.id}
                  alert={alert}
                  onToggle={(id) => toggleMut.mutate(id)}
                  onDelete={(id) => deleteMut.mutate(id)}
                  onTest={handleTest}
                  isTestPending={testingId === alert.id}
                />
              ))}
            </div>
          )}

          {adding ? (
            <div className="space-y-4 rounded-xl border border-border p-4">
              <div>
                <label className="mb-2 block text-sm font-medium text-foreground">Trigger when…</label>
                <div className="flex items-center gap-2">
                  <div className="relative flex-1">
                    <select value={metric} onChange={(e) => setMetric(e.target.value as AlertMetric)} className={selectCls}>
                      {METRIC_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  </div>
                  <div className="relative flex-1">
                    <select value={condition} onChange={(e) => setCondition(e.target.value as AlertCondition)} className={selectCls}>
                      {CONDITION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <input type="number" min={0} max={100} value={threshold} onChange={(e) => setThreshold(e.target.value)}
                      className="w-16 rounded-lg border border-border bg-background px-2 py-2 text-center text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40" />
                    <span className="text-sm text-muted-foreground">%</span>
                  </div>
                </div>
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-foreground">Notify via</label>
                <div className="mb-3 flex gap-2">
                  {CHANNEL_OPTIONS.map((c) => (
                    <button key={c.value} onClick={() => setChannel(c.value)}
                      className={`flex-1 rounded-lg border py-2 text-xs font-medium transition-all ${channel === c.value ? "border-primary/60 bg-primary/5 text-foreground" : "border-border text-muted-foreground hover:text-foreground"}`}>
                      {c.label}
                    </button>
                  ))}
                </div>
                <input type={channel === "email" ? "email" : "url"} value={target} onChange={(e) => setTarget(e.target.value)} placeholder={channelMeta.placeholder}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-primary/40" />
              </div>
              {createMut.isError && (
                <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-400">
                  <AlertTriangle className="h-4 w-4 shrink-0" />
                  {(createMut.error as Error).message}
                </div>
              )}
              <div className="flex justify-end gap-2">
                <button onClick={() => setAdding(false)} className="rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted/50">
                  Cancel
                </button>
                <button
                  onClick={() => createMut.mutate({ metric, condition, threshold: +threshold, channel, channel_target: target.trim() })}
                  disabled={!canSubmit || createMut.isPending}
                  className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {createMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Bell className="h-4 w-4" />}
                  Create alert
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setAdding(true)}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-border py-2.5 text-sm font-medium text-muted-foreground hover:bg-muted/40 hover:text-foreground"
            >
              <Plus className="h-4 w-4" />
              Add alert
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

import { useState } from "react"
import { useParams } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Activity,
  Bell,
  Plus,
  Loader2,
  AlertTriangle,
  X,
  Cpu,
  MemoryStick,
  HardDrive,
  Clock,
  ChevronDown,
} from "lucide-react"
import {
  getMetricsHistory,
  listAlerts,
  createAlert,
  deleteAlert,
  toggleAlert,
  testAlert,
  type AlertCreateBody,
} from "@/api/monitoring"
import { getServer } from "@/api/servers"
import CpuChart from "@/components/monitoring/CpuChart"
import RamChart from "@/components/monitoring/RamChart"
import DiskChart from "@/components/monitoring/DiskChart"
import AlertCard from "@/components/monitoring/AlertCard"

// ── Helpers ────────────────────────────────────────────────────────────────

type HistoryWindow = 6 | 24 | 48 | 168

function fmtUptime(seconds: number | null): string {
  if (!seconds) return "—"
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function gaugeColor(v: number | null): string {
  if (v == null) return "text-muted-foreground"
  if (v >= 90) return "text-red-400"
  if (v >= 75) return "text-orange-400"
  return "text-emerald-400"
}

function gaugeBg(v: number | null): string {
  if (v == null) return "bg-muted"
  if (v >= 90) return "bg-red-500"
  if (v >= 75) return "bg-orange-500"
  return "bg-emerald-500"
}

// ── Stat card ──────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  subValue,
  icon,
}: {
  label: string
  value: number | null
  subValue?: string
  icon: React.ReactNode
}) {
  const pct = value != null ? Math.min(100, Math.max(0, value)) : 0
  return (
    <div className="rounded-xl border border-border bg-card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-muted-foreground">
          {icon}
          <span className="text-xs font-medium">{label}</span>
        </div>
        <span className={`text-2xl font-bold tabular-nums ${gaugeColor(value)}`}>
          {value != null ? `${Number(value).toFixed(1)}%` : "—"}
        </span>
      </div>
      {/* Progress bar */}
      <div className="h-1.5 rounded-full bg-muted overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${gaugeBg(value)}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {subValue && (
        <p className="text-xs text-muted-foreground">{subValue}</p>
      )}
    </div>
  )
}

// ── Add alert modal ────────────────────────────────────────────────────────

type AlertMetric = "cpu" | "ram" | "disk"
type AlertCondition = "gt" | "gte" | "lt" | "lte"
type AlertChannel = "email" | "webhook" | "slack"

const METRIC_OPTIONS: { value: AlertMetric; label: string }[] = [
  { value: "cpu", label: "CPU Usage" },
  { value: "ram", label: "RAM Usage" },
  { value: "disk", label: "Disk Usage" },
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

function AddAlertModal({
  onClose,
  onCreate,
  isCreating,
}: {
  onClose: () => void
  onCreate: (body: AlertCreateBody) => Promise<void>
  isCreating: boolean
}) {
  const [metric, setMetric] = useState<AlertMetric>("cpu")
  const [condition, setCondition] = useState<AlertCondition>("gt")
  const [threshold, setThreshold] = useState("85")
  const [channel, setChannel] = useState<AlertChannel>("email")
  const [target, setTarget] = useState("")

  const channelMeta = CHANNEL_OPTIONS.find((c) => c.value === channel)!
  const canSubmit = target.trim() && +threshold >= 0 && +threshold <= 100

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-md">
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <h2 className="font-semibold text-foreground">New Alert Rule</h2>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {/* Condition builder */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Trigger when…
            </label>
            <div className="flex items-center gap-2">
              {/* Metric */}
              <div className="relative flex-1">
                <select
                  value={metric}
                  onChange={(e) => setMetric(e.target.value as AlertMetric)}
                  className="w-full appearance-none rounded-lg border border-border bg-background text-sm text-foreground px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/40 pr-7"
                >
                  {METRIC_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
              </div>

              {/* Condition */}
              <div className="relative flex-1">
                <select
                  value={condition}
                  onChange={(e) => setCondition(e.target.value as AlertCondition)}
                  className="w-full appearance-none rounded-lg border border-border bg-background text-sm text-foreground px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/40 pr-7"
                >
                  {CONDITION_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
              </div>

              {/* Threshold */}
              <div className="flex items-center gap-1 shrink-0">
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={threshold}
                  onChange={(e) => setThreshold(e.target.value)}
                  className="w-16 rounded-lg border border-border bg-background text-sm text-foreground px-2 py-2 text-center focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
                <span className="text-sm text-muted-foreground">%</span>
              </div>
            </div>
          </div>

          {/* Channel */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Notify via
            </label>
            <div className="flex gap-2 mb-3">
              {CHANNEL_OPTIONS.map((c) => (
                <button
                  key={c.value}
                  onClick={() => setChannel(c.value)}
                  className={`flex-1 py-2 rounded-lg border text-xs font-medium transition-all ${
                    channel === c.value
                      ? "border-primary/60 bg-primary/5 text-foreground"
                      : "border-border text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </div>
            <input
              type={channel === "email" ? "email" : "url"}
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder={channelMeta.placeholder}
              className="w-full rounded-lg border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground/50 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm text-muted-foreground hover:text-foreground border border-border hover:bg-muted/50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={() =>
              onCreate({ metric, condition, threshold: +threshold, channel, channel_target: target.trim() })
            }
            disabled={!canSubmit || isCreating}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {isCreating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Bell className="h-4 w-4" />}
            Create Alert
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────

export default function Monitoring() {
  const { id: serverId } = useParams<{ id: string }>()
  const qc = useQueryClient()
  const [window, setWindow] = useState<HistoryWindow>(24)
  const [showAddAlert, setShowAddAlert] = useState(false)
  const [testingId, setTestingId] = useState<string | null>(null)

  const { data: server } = useQuery({
    queryKey: ["server", serverId],
    queryFn: () => getServer(serverId!),
    enabled: !!serverId,
  })

  const { data: history = [], isLoading: histLoading } = useQuery({
    queryKey: ["metrics-history", serverId, window],
    queryFn: () => getMetricsHistory(serverId!, window),
    enabled: !!serverId,
    refetchInterval: 60_000, // refresh every minute
  })

  const { data: alerts = [], isLoading: alertsLoading } = useQuery({
    queryKey: ["alerts", serverId],
    queryFn: () => listAlerts(serverId!),
    enabled: !!serverId,
  })

  const createMut = useMutation({
    mutationFn: (body: AlertCreateBody) => createAlert(serverId!, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["alerts", serverId] })
      setShowAddAlert(false)
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

  const handleTest = async (id: string) => {
    setTestingId(id)
    try { await testAlert(id) } finally { setTestingId(null) }
  }

  // Derive current values from the latest data point
  const latest = history.length ? history[history.length - 1] : null

  const ramSubValue = latest?.ram_used_mb && latest?.ram_total_mb
    ? `${(latest.ram_used_mb / 1024).toFixed(1)} / ${(latest.ram_total_mb / 1024).toFixed(1)} GB`
    : undefined

  const diskSubValue = latest?.disk_used_gb && latest?.disk_total_gb
    ? `${latest.disk_used_gb.toFixed(1)} / ${latest.disk_total_gb.toFixed(1)} GB`
    : undefined

  const WINDOW_OPTIONS: { value: HistoryWindow; label: string }[] = [
    { value: 6, label: "6h" },
    { value: 24, label: "24h" },
    { value: 48, label: "48h" },
    { value: 168, label: "7d" },
  ]

  return (
    <>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-foreground flex items-center gap-2">
              <Activity className="h-6 w-6 text-primary" />
              Monitoring
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              {server?.name ?? "Server"} — collected every 5 minutes
            </p>
          </div>

          {/* Uptime chip */}
          {latest?.uptime_seconds && (
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground border border-border rounded-full px-3 py-1.5">
              <Clock className="h-3.5 w-3.5" />
              Up {fmtUptime(latest.uptime_seconds)}
            </div>
          )}
        </div>

        {/* No data yet */}
        {!histLoading && history.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-center rounded-xl border border-dashed border-border">
            <Activity className="h-10 w-10 text-muted-foreground/30 mb-3" />
            <p className="font-medium text-muted-foreground">No metrics collected yet</p>
            <p className="text-sm text-muted-foreground/60 mt-1">
              The first data point arrives within 5 minutes of adding this server
            </p>
          </div>
        )}

        {/* Current stats */}
        {latest && (
          <div className="grid grid-cols-3 gap-4">
            <StatCard
              label="CPU"
              value={latest.cpu_percent}
              subValue={latest.load_1 != null ? `Load: ${latest.load_1.toFixed(2)}` : undefined}
              icon={<Cpu className="h-4 w-4" />}
            />
            <StatCard
              label="RAM"
              value={latest.ram_percent}
              subValue={ramSubValue}
              icon={<MemoryStick className="h-4 w-4" />}
            />
            <StatCard
              label="Disk"
              value={latest.disk_percent}
              subValue={diskSubValue}
              icon={<HardDrive className="h-4 w-4" />}
            />
          </div>
        )}

        {/* History charts */}
        {history.length > 0 && (
          <div className="space-y-4">
            {/* Window selector */}
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-medium text-foreground">History</h2>
              <div className="flex rounded-lg border border-border overflow-hidden">
                {WINDOW_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setWindow(opt.value)}
                    className={`px-3 py-1.5 text-xs font-medium transition-colors ${
                      window === opt.value
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-3">
              {/* CPU */}
              <div className="rounded-xl border border-border bg-card p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Cpu className="h-3.5 w-3.5 text-emerald-400" />
                  <span className="text-xs font-medium text-foreground">CPU</span>
                </div>
                <CpuChart data={history} />
              </div>

              {/* RAM */}
              <div className="rounded-xl border border-border bg-card p-4">
                <div className="flex items-center gap-2 mb-3">
                  <MemoryStick className="h-3.5 w-3.5 text-blue-400" />
                  <span className="text-xs font-medium text-foreground">RAM</span>
                </div>
                <RamChart data={history} />
              </div>

              {/* Disk */}
              <div className="rounded-xl border border-border bg-card p-4">
                <div className="flex items-center gap-2 mb-3">
                  <HardDrive className="h-3.5 w-3.5 text-violet-400" />
                  <span className="text-xs font-medium text-foreground">Disk</span>
                </div>
                <DiskChart data={history} />
              </div>
            </div>
          </div>
        )}

        {/* Alert rules */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-medium text-foreground">Alert Rules</h2>
              {alerts.length > 0 && (
                <span className="text-xs text-muted-foreground bg-muted rounded-full px-2 py-0.5">
                  {alerts.length}
                </span>
              )}
            </div>
            <button
              onClick={() => setShowAddAlert(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Alert
            </button>
          </div>

          {alertsLoading && (
            <div className="flex items-center gap-2 py-6 text-muted-foreground text-sm">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading alerts…
            </div>
          )}

          {!alertsLoading && alerts.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 text-center rounded-xl border border-dashed border-border">
              <Bell className="h-8 w-8 text-muted-foreground/30 mb-2" />
              <p className="text-sm text-muted-foreground">No alert rules yet</p>
              <p className="text-xs text-muted-foreground/60 mt-1">
                Get notified when CPU, RAM, or disk exceeds a threshold
              </p>
            </div>
          )}

          {alerts.length > 0 && (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
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

          {createMut.isError && (
            <div className="mt-3 flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {(createMut.error as Error).message}
            </div>
          )}
        </div>
      </div>

      {showAddAlert && (
        <AddAlertModal
          onClose={() => setShowAddAlert(false)}
          onCreate={async (body) => { await createMut.mutateAsync(body) }}
          isCreating={createMut.isPending}
        />
      )}
    </>
  )
}

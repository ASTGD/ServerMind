import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import { Globe, Plus, Trash2, RefreshCw, Loader2, X, CircleCheck, CircleAlert, CircleDashed, ShieldAlert, ShieldCheck } from "lucide-react"
import {
  listMonitors, createMonitor, deleteMonitor, checkMonitorNow,
  type UptimeMonitor, type MonitorBody,
} from "@/api/uptime"
import { Button } from "@/components/ui"

const input =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
const label = "mb-1 block text-xs font-medium text-muted-foreground"

const INTERVALS = [
  { value: 60, label: "Every minute" },
  { value: 300, label: "Every 5 minutes" },
  { value: 900, label: "Every 15 minutes" },
  { value: 1800, label: "Every 30 minutes" },
  { value: 3600, label: "Every hour" },
]

function StatusIcon({ status }: { status: UptimeMonitor["current_status"] }) {
  if (status === "up") return <CircleCheck size={16} className="shrink-0 text-emerald-600 dark:text-emerald-400" />
  if (status === "down") return <CircleAlert size={16} className="shrink-0 text-red-600 dark:text-red-400" />
  return <CircleDashed size={16} className="shrink-0 text-muted-foreground" />
}

function AddMonitorForm({ serverId, onClose }: { serverId?: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState<MonitorBody>({
    name: "", url: "", server_id: serverId ?? null,
    expected_status: 200, expected_keyword: "", interval_seconds: 300,
    failure_threshold: 2, channel: "email", channel_target: "",
  })
  const [error, setError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: () =>
      createMonitor({
        ...form,
        expected_keyword: form.expected_keyword?.trim() || null,
        channel_target: form.channel_target?.trim() || null,
        channel: form.channel_target?.trim() ? form.channel : null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["uptime-monitors"] })
      onClose()
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(typeof detail === "string" ? detail : "Could not create this monitor.")
    },
  })

  return (
    <div className="rounded-xl border border-border bg-muted/30 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="text-sm font-semibold">Watch a site</h4>
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-accent">
          <X size={15} />
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={label}>Name</label>
          <input className={input} placeholder="My shop" value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div>
          <label className={label}>How often</label>
          <select className={input} value={form.interval_seconds}
            onChange={(e) => setForm({ ...form, interval_seconds: Number(e.target.value) })}>
            {INTERVALS.map((i) => <option key={i.value} value={i.value}>{i.label}</option>)}
          </select>
        </div>
        <div className="sm:col-span-2">
          <label className={label}>Address</label>
          <input className={`${input} font-mono text-xs`} placeholder="https://myshop.com"
            value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
        </div>
        <div className="sm:col-span-2">
          <label className={label}>
            Text that must appear on the page <span className="text-muted-foreground/70">(optional, recommended)</span>
          </label>
          <input className={input} placeholder="Welcome to my shop"
            value={form.expected_keyword ?? ""}
            onChange={(e) => setForm({ ...form, expected_keyword: e.target.value })} />
          <p className="mt-1 text-[11px] text-muted-foreground">
            A hacked or broken site often still answers “OK”. If you give some text from your real page,
            we can tell the difference.
          </p>
        </div>
        <div>
          <label className={label}>Tell me at (email)</label>
          <input className={input} type="email" placeholder="you@example.com"
            value={form.channel_target ?? ""}
            onChange={(e) => setForm({ ...form, channel_target: e.target.value })} />
        </div>
        <div>
          <label className={label}>Say it's down after</label>
          <select className={input} value={form.failure_threshold}
            onChange={(e) => setForm({ ...form, failure_threshold: Number(e.target.value) })}>
            <option value={1}>1 failed check</option>
            <option value={2}>2 failed checks in a row</option>
            <option value={3}>3 failed checks in a row</option>
          </select>
        </div>
      </div>

      {error && (
        <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      <div className="mt-3 flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
        <Button size="sm" disabled={!form.name || !form.url || save.isPending}
          onClick={() => { setError(null); save.mutate() }}>
          {save.isPending ? <><Loader2 size={14} className="animate-spin" /> Checking…</> : "Start watching"}
        </Button>
      </div>
    </div>
  )
}

/** HTTPS certificate expiry. Quiet when healthy — an owner only needs to know when it
 *  is close, because that means automatic renewal has already failed. */
function CertBadge({ monitor }: { monitor: UptimeMonitor }) {
  const state = monitor.cert_state
  const days = monitor.cert_days_left
  if (!state || state === "unknown") return null
  if (state === "ok") {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground"
        title={`HTTPS certificate valid${monitor.cert_issuer ? ` — issued by ${monitor.cert_issuer}` : ""}`}>
        <ShieldCheck size={11} /> {days}d
      </span>
    )
  }
  const urgent = state === "expired" || state === "critical"
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium ${
        urgent
          ? "bg-red-500/10 text-red-600 dark:text-red-400"
          : "bg-amber-500/10 text-amber-600 dark:text-amber-400"
      }`}
      title={monitor.cert_expires_at ? `Expires ${new Date(monitor.cert_expires_at).toLocaleDateString()}` : undefined}
    >
      <ShieldAlert size={11} />
      {state === "expired" ? "certificate expired" : `certificate expires in ${days}d`}
    </span>
  )
}

function MonitorRow({ monitor }: { monitor: UptimeMonitor }) {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: ["uptime-monitors"] })
  const check = useMutation({ mutationFn: () => checkMonitorNow(monitor.id), onSuccess: refresh })
  const remove = useMutation({ mutationFn: () => deleteMonitor(monitor.id), onSuccess: refresh })

  // A paused check is not reporting anything, so it must not read as a verdict. Its last
  // words are frozen at whatever it saw before we stopped — showing those in red says the
  // site is down right now, which we have no idea about and are no longer asking.
  const paused = !monitor.is_active
  const down = !paused && monitor.current_status === "down"
  return (
    <li className={`rounded-lg border px-3 py-2.5 ${down ? "border-red-500/40 bg-red-500/5" : "border-border bg-background"} ${paused ? "opacity-60" : ""}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusIcon status={paused ? "unknown" : monitor.current_status} />
            <span className="truncate text-sm font-medium">{monitor.name}</span>
            {paused ? (
              <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                paused — this site is not on the server
              </span>
            ) : monitor.current_status !== "unknown" && (
              <span className={`text-[11px] font-medium ${down ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                {down ? "DOWN" : "up"}
              </span>
            )}
            {monitor.last_response_ms != null && !down && (
              <span className="text-[11px] text-muted-foreground">{monitor.last_response_ms} ms</span>
            )}
          </div>
          <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">{monitor.url}</p>
          <div className="mt-1"><CertBadge monitor={monitor} /></div>
          {down && monitor.last_error && (
            <p className="mt-1 text-[11px] text-red-600 dark:text-red-400">{monitor.last_error}</p>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
            <span>24h {monitor.uptime_24h}%</span>
            <span>·</span>
            <span>30d {monitor.uptime_30d}%</span>
            {monitor.last_checked && (
              <>
                <span>·</span>
                <span>checked {formatDistanceToNow(new Date(monitor.last_checked), { addSuffix: true })}</span>
              </>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button size="sm" variant="ghost" title="Check now"
            disabled={check.isPending} onClick={() => check.mutate()}>
            {check.isPending ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          </Button>
          <Button size="sm" variant="ghost" disabled={remove.isPending}
            onClick={() => { if (window.confirm(`Stop watching "${monitor.name}"?`)) remove.mutate() }}
            className="text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-400 dark:hover:bg-red-950/30">
            <Trash2 size={14} />
          </Button>
        </div>
      </div>
    </li>
  )
}

/** "Is my site up?" — checked from ServerAlly, so it sees what a visitor sees. */
export default function UptimePanel({ serverId }: { serverId?: string }) {
  const [adding, setAdding] = useState(false)
  const { data: monitors = [], isLoading } = useQuery({
    queryKey: ["uptime-monitors", serverId ?? "all"],
    queryFn: () => listMonitors(serverId),
    refetchInterval: 30_000,
  })
  const downCount = monitors.filter(
    (m) => m.is_active && m.current_status === "down").length
  const pausedCount = monitors.filter((m) => !m.is_active).length

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Globe size={15} className="text-primary" />
          Site uptime
          {downCount > 0 && (
            <span className="rounded-full bg-red-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-red-600 dark:text-red-400">
              {downCount} down
            </span>
          )}
          {pausedCount > 0 && (
            <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">
              {pausedCount} paused
            </span>
          )}
        </h3>
        {!adding && (
          <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
            <Plus size={14} /> Watch a site
          </Button>
        )}
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        We check from outside your server, so this is what a visitor actually sees.
      </p>

      {adding && <div className="mb-3"><AddMonitorForm serverId={serverId} onClose={() => setAdding(false)} /></div>}

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : monitors.length === 0 && !adding ? (
        <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
          Nothing is being watched yet. Alerts today only cover CPU, memory and disk — not whether your site loads.
        </div>
      ) : (
        <ul className="space-y-2">{monitors.map((m) => <MonitorRow key={m.id} monitor={m} />)}</ul>
      )}
    </div>
  )
}

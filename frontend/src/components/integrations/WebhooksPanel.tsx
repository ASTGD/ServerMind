import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import {
  Webhook, Plus, Loader2, Trash2, Send, Check, Eye, EyeOff, Power, History,
} from "lucide-react"
import {
  listWebhooks, createWebhook, updateWebhook, deleteWebhook, testWebhook,
  webhookSecret, webhookDeliveries, webhookInfo, EVENT_LABEL,
  type WebhookEndpoint,
} from "@/api/integrations"
import { Button } from "@/components/ui"
import { cn } from "@/lib/utils"

const input =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
const label = "mb-1 block text-xs font-medium text-muted-foreground"

function ago(iso: string | null): string {
  if (!iso) return "—"
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true })
  } catch {
    return "—"
  }
}

function detail(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === "string" ? d : fallback
}

function Deliveries({ id }: { id: string }) {
  const { data = [], isLoading } = useQuery({
    queryKey: ["webhook-deliveries", id],
    queryFn: () => webhookDeliveries(id),
  })
  if (isLoading) return <p className="py-2 text-[11.5px] text-muted-foreground">Loading…</p>
  if (data.length === 0)
    return <p className="py-2 text-[11.5px] text-muted-foreground">Nothing sent yet.</p>
  return (
    <ul className="mt-2 space-y-1">
      {data.map((d) => (
        <li key={d.id} className="flex flex-wrap items-center gap-2 text-[11.5px]">
          <span className={cn("rounded px-1.5 py-0.5 font-semibold",
            d.status === "delivered"
              ? "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
              : d.status === "pending"
                ? "bg-amber-500/15 text-amber-700 dark:text-amber-300"
                : "bg-red-500/15 text-red-700 dark:text-red-300")}>
            {d.status}
          </span>
          <span className="font-mono">{d.event}</span>
          {d.http_status ? <span className="text-muted-foreground">HTTP {d.http_status}</span> : null}
          {d.attempts > 1 && <span className="text-muted-foreground">{d.attempts} attempts</span>}
          <span className="text-muted-foreground">{ago(d.created_at)}</span>
          {d.error && <span className="text-red-600 dark:text-red-400">{d.error}</span>}
        </li>
      ))}
    </ul>
  )
}

function Secret({ id }: { id: string }) {
  const [shown, setShown] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  return (
    <div className="mt-2 flex items-center gap-1.5">
      {shown ? (
        <>
          <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap rounded border border-border bg-background px-2 py-1 font-mono text-[11px]">
            {shown}
          </code>
          <Button size="sm" variant="ghost"
            onClick={async () => {
              await navigator.clipboard.writeText(shown)
              setCopied(true); setTimeout(() => setCopied(false), 1500)
            }}>
            {copied ? <Check size={12} className="text-emerald-600" /> : "Copy"}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setShown(null)}>
            <EyeOff size={12} />
          </Button>
        </>
      ) : (
        <Button size="sm" variant="ghost"
          onClick={async () => setShown(await webhookSecret(id))}>
          <Eye size={12} /> Show signing secret
        </Button>
      )}
    </div>
  )
}

/**
 * Webhooks — ServerAlly POSTs to the customer's own systems when something happens.
 *
 * Every request is signed, so the receiver can prove it came from us rather than from anyone
 * who guessed the URL.
 */
export default function WebhooksPanel() {
  const qc = useQueryClient()
  const { data: hooks = [] } = useQuery({ queryKey: ["webhooks"], queryFn: listWebhooks })
  const { data: info } = useQuery({ queryKey: ["webhook-info"], queryFn: webhookInfo })
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState<{ name: string; url: string; events: string[] }>({
    name: "", url: "", events: ["incident.opened", "uptime.down"],
  })
  const [expanded, setExpanded] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [ok, setOk] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ["webhooks"] })

  const create = useMutation({
    mutationFn: () => createWebhook({
      name: form.name.trim() || "My webhook", url: form.url.trim(), events: form.events,
    }),
    onSuccess: () => {
      setAdding(false)
      setForm({ name: "", url: "", events: ["incident.opened", "uptime.down"] })
      invalidate()
    },
    onError: (e) => setError(detail(e, "Could not save that webhook.")),
  })
  const toggle = useMutation({
    mutationFn: (h: WebhookEndpoint) => updateWebhook(h.id, { is_active: !h.is_active }),
    onSuccess: invalidate,
  })
  const remove = useMutation({ mutationFn: deleteWebhook, onSuccess: invalidate })
  const test = useMutation({
    mutationFn: testWebhook,
    onSuccess: (res) => { setOk(`Test delivered (HTTP ${res.http_status}).`); setTimeout(() => setOk(null), 4000) },
    onError: (e) => setError(detail(e, "The test could not be delivered.")),
  })

  const events = info?.events ?? Object.keys(EVENT_LABEL)

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <Webhook size={15} className="text-primary" />
        <h3 className="text-sm font-semibold">Webhooks</h3>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        We’ll POST to your address whenever something happens, so events can flow into your
        own dashboard or ticket system. Every request is signed, so your code can prove it
        really came from us.
      </p>

      {hooks.length === 0 && !adding && (
        <p className="mb-3 rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
          No webhooks yet.
        </p>
      )}

      {hooks.length > 0 && (
        <ul className="mb-3 space-y-2">
          {hooks.map((h) => (
            <li key={h.id} className="rounded-lg border border-border p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="flex flex-wrap items-center gap-1.5 text-[13px] font-medium">
                    {h.name}
                    {!h.is_active && (
                      <span className="rounded-full bg-red-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-red-700 dark:text-red-300">
                        Off
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">{h.url}</p>
                  <p className="mt-1 text-[11.5px] text-muted-foreground">
                    {h.events.map((e) => EVENT_LABEL[e] ?? e).join(" · ")}
                  </p>
                  {h.disabled_reason && (
                    <p className="mt-1 text-[11.5px] text-red-600 dark:text-red-400">
                      {h.disabled_reason}
                    </p>
                  )}
                  <Secret id={h.id} />
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button title="Send a test" disabled={test.isPending}
                    onClick={() => { setError(null); test.mutate(h.id) }}
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
                    {test.isPending ? <Loader2 size={14} className="animate-spin" /> : <Send size={14} />}
                  </button>
                  <button title="Recent deliveries"
                    onClick={() => setExpanded(expanded === h.id ? null : h.id)}
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
                    <History size={14} />
                  </button>
                  <button title={h.is_active ? "Turn off" : "Turn on"} onClick={() => toggle.mutate(h)}
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
                    <Power size={14} />
                  </button>
                  <button title="Delete" onClick={() => remove.mutate(h.id)}
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-red-500/10 hover:text-red-600">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
              {expanded === h.id && <Deliveries id={h.id} />}
            </li>
          ))}
        </ul>
      )}

      {adding ? (
        <div className="rounded-lg border border-border p-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className={label}>Name</label>
              <input className={input} placeholder="Our Slack app"
                value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <label className={label}>Your address</label>
              <input className={`${input} font-mono text-xs`} placeholder="https://example.com/hooks/serverally"
                value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
            </div>
          </div>
          <p className={`${label} mt-3`}>Send me these events</p>
          <div className="grid gap-1.5 sm:grid-cols-2">
            {events.map((ev) => (
              <label key={ev} className="flex cursor-pointer items-center gap-2 rounded-md px-1 py-0.5 text-[12.5px]">
                <input type="checkbox" checked={form.events.includes(ev)}
                  onChange={(e) => setForm({
                    ...form,
                    events: e.target.checked
                      ? [...form.events, ev]
                      : form.events.filter((x) => x !== ev),
                  })} />
                {EVENT_LABEL[ev] ?? ev}
              </label>
            ))}
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => { setAdding(false); setError(null) }}>
              Cancel
            </Button>
            <Button size="sm"
              disabled={create.isPending || !form.url.trim() || form.events.length === 0}
              onClick={() => { setError(null); create.mutate() }}>
              {create.isPending ? <><Loader2 size={13} className="animate-spin" /> Saving…</> : "Add webhook"}
            </Button>
          </div>
        </div>
      ) : (
        <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
          <Plus size={14} /> New webhook
        </Button>
      )}

      {ok && (
        <p className="mt-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-400">
          {ok}
        </p>
      )}
      {error && (
        <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      {info && (
        <p className="mt-3 text-[11px] text-muted-foreground">
          We retry {info.delivery.retries} times ({info.delivery.backoff_minutes.join(", ")} minutes
          apart) and expect any 2xx reply. After {info.delivery.disabled_after} failures in a row
          we switch the webhook off so we stop knocking on a door nobody answers.
        </p>
      )}
    </div>
  )
}

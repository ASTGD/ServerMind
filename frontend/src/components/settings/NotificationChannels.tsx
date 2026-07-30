import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Bell, Check, Loader2, Mail, MessageSquare, Send, Smartphone, Trash2, AlertTriangle } from "lucide-react"
import {
  listChannels, createChannel, testChannel, deleteChannel,
  type ChannelKind, type NotificationChannel,
} from "@/api/channels"

/**
 * Where alerts go — set up once, used by every rule.
 *
 * Before this, every alert rule carried its own copy of the destination, so an agency
 * watching three metrics across fifteen servers had the same Slack URL pasted into
 * forty-five places and no way to change it once.
 *
 * The "Send test" button is the important control, not a nicety: a channel is shown as
 * unproven until a real message has arrived, because alerting that silently goes nowhere is
 * worse than none at all — which is exactly what we found in production.
 */

const KINDS: {
  kind: ChannelKind
  label: string
  icon: typeof Mail
  blurb: string
  fields: { name: string; label: string; placeholder: string; help?: string }[]
}[] = [
  {
    kind: "email", label: "Email", icon: Mail,
    blurb: "An email address.",
    fields: [{ name: "address", label: "Email address", placeholder: "you@example.com" }],
  },
  {
    kind: "slack", label: "Slack", icon: MessageSquare,
    blurb: "A Slack channel, via an incoming webhook.",
    fields: [{
      name: "webhook_url", label: "Webhook URL",
      placeholder: "https://hooks.slack.com/services/...",
      help: "In Slack: Apps → Incoming Webhooks → Add to Slack, then copy the URL.",
    }],
  },
  {
    kind: "telegram", label: "Telegram", icon: Send,
    blurb: "A Telegram chat or group.",
    fields: [
      {
        name: "bot_token", label: "Bot token", placeholder: "123456789:AAE...",
        help: "Message @BotFather on Telegram, create a bot, and copy the token it gives you.",
      },
      {
        name: "chat_id", label: "Chat ID", placeholder: "-1001234567890",
        help: "Send your bot a message first, then it can reply to that chat.",
      },
    ],
  },
  {
    kind: "sms", label: "SMS", icon: Smartphone,
    blurb: "A text message. Uses the Twilio account from your on-call settings.",
    fields: [{
      name: "phone", label: "Phone number", placeholder: "+8801712345678",
      help: "International format, starting with + and the country code.",
    }],
  },
]

function KindIcon({ kind }: { kind: ChannelKind }) {
  const entry = KINDS.find((k) => k.kind === kind)
  const Icon = entry?.icon ?? Bell
  return <Icon size={14} className="text-muted-foreground" />
}

export default function NotificationChannels() {
  const qc = useQueryClient()
  const [adding, setAdding] = useState<ChannelKind | null>(null)
  const [label, setLabel] = useState("")
  const [config, setConfig] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [testingId, setTestingId] = useState<string | null>(null)

  const { data: channels = [], isLoading } = useQuery({
    queryKey: ["channels"],
    queryFn: listChannels,
  })

  const reset = () => { setAdding(null); setLabel(""); setConfig({}); setError(null) }

  const create = useMutation({
    mutationFn: () => createChannel({ kind: adding!, label, config }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["channels"] }); reset() },
    // The server's message names the actual problem ("that is not a Slack webhook URL"),
    // so show it rather than a generic failure.
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "Could not save this channel."),
  })

  const test = useMutation({
    mutationFn: (id: string) => testChannel(id),
    onSettled: () => { setTestingId(null); qc.invalidateQueries({ queryKey: ["channels"] }) },
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteChannel(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["channels"] }),
  })

  const spec = KINDS.find((k) => k.kind === adding)

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="flex items-center gap-2 text-h3 text-foreground">
            <Bell size={16} className="text-primary" /> Notification channels
          </h3>
          <p className="mt-1 text-small text-muted-foreground">
            Where alerts go. Set one up once and use it for any server.
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-6 text-muted-foreground">
          <Loader2 size={16} className="animate-spin" />
        </div>
      ) : channels.length === 0 ? (
        <p className="mt-4 rounded-lg border border-dashed border-border p-4 text-center text-small text-muted-foreground">
          No channels yet — alerts have nowhere to go. Add one below.
        </p>
      ) : (
        <ul className="mt-4 space-y-2">
          {channels.map((c: NotificationChannel) => (
            <li key={c.id} className="flex items-center gap-3 rounded-lg border border-border p-3">
              <KindIcon kind={c.kind} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">{c.label}</p>
                <p className="truncate text-caption text-muted-foreground">
                  {Object.values(c.details).filter(Boolean).join(" · ") || c.kind}
                </p>
              </div>

              {/* Unproven is a real state, shown plainly — not assumed to be working. */}
              {c.last_error ? (
                <span className="flex items-center gap-1 text-caption text-destructive" title={c.last_error}>
                  <AlertTriangle size={12} /> Failed
                </span>
              ) : c.verified_at ? (
                <span className="flex items-center gap-1 text-caption text-[hsl(var(--success))]">
                  <Check size={12} /> Working
                </span>
              ) : (
                <span className="text-caption text-muted-foreground">Not tested yet</span>
              )}

              <button
                onClick={() => { setTestingId(c.id); test.mutate(c.id) }}
                disabled={testingId === c.id}
                className="rounded-md border border-border px-2 py-1 text-caption text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                {testingId === c.id ? <Loader2 size={12} className="animate-spin" /> : "Send test"}
              </button>
              <button
                onClick={() => remove.mutate(c.id)}
                aria-label={`Remove ${c.label}`}
                className="rounded p-1 text-muted-foreground transition-colors hover:text-destructive"
              >
                <Trash2 size={13} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {test.isError && (
        <p className="mt-3 rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-destructive">
          {(test.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
            ?? "The test message could not be sent."}
        </p>
      )}

      {/* ── add ── */}
      {!adding ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {KINDS.map((k) => (
            <button
              key={k.kind}
              onClick={() => { reset(); setAdding(k.kind) }}
              className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-small text-foreground transition-colors hover:bg-accent"
            >
              <k.icon size={13} /> Add {k.label}
            </button>
          ))}
        </div>
      ) : (
        <form
          onSubmit={(e) => { e.preventDefault(); setError(null); create.mutate() }}
          className="mt-4 space-y-3 rounded-lg border border-border p-4"
        >
          <p className="text-small text-muted-foreground">{spec?.blurb}</p>

          <div>
            <label className="text-caption text-muted-foreground">Name</label>
            <input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Ops Slack"
              required
              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground"
            />
            <p className="mt-1 text-caption text-muted-foreground">
              What you will call it when picking where an alert goes.
            </p>
          </div>

          {spec?.fields.map((f) => (
            <div key={f.name}>
              <label className="text-caption text-muted-foreground">{f.label}</label>
              <input
                value={config[f.name] ?? ""}
                onChange={(e) => setConfig({ ...config, [f.name]: e.target.value })}
                placeholder={f.placeholder}
                required
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground"
              />
              {f.help && <p className="mt-1 text-caption text-muted-foreground">{f.help}</p>}
            </div>
          ))}

          {error && (
            <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-destructive">
              {error}
            </p>
          )}

          <div className="flex gap-2">
            <button
              type="submit"
              disabled={create.isPending}
              className="rounded-lg bg-primary px-3 py-1.5 text-small font-medium text-primary-foreground disabled:opacity-60"
            >
              {create.isPending ? "Saving…" : "Save channel"}
            </button>
            <button
              type="button"
              onClick={reset}
              className="rounded-lg border border-border px-3 py-1.5 text-small text-muted-foreground hover:bg-accent"
            >
              Cancel
            </button>
          </div>
        </form>
      )}
    </div>
  )
}

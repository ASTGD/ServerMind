import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Mail, Loader2, Trash2, Send, Check, Plus, Pause, Play } from "lucide-react"
import {
  listReportRecipients, addReportRecipient, updateReportRecipient,
  deleteReportRecipient, sendReportNow, type ReportRecipient,
} from "@/api/branding"
import { listServers } from "@/api/servers"
import { Button } from "@/components/ui"

const input =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
const label = "mb-1 block text-xs font-medium text-muted-foreground"

function ordinal(n: number): string {
  const suffix = n % 10 === 1 && n !== 11 ? "st" : n % 10 === 2 && n !== 12 ? "nd" : n % 10 === 3 && n !== 13 ? "rd" : "th"
  return `${n}${suffix}`
}

/**
 * Monthly client reports — an agency schedules the branded "here is what we did for you"
 * email that goes to *their* client. Deterministic, so it costs nothing to send.
 */
export default function ClientReportsPanel() {
  const qc = useQueryClient()
  const { data: recipients = [] } = useQuery({
    queryKey: ["client-report-recipients"], queryFn: listReportRecipients,
  })
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers })

  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ server_id: "", recipient_email: "", recipient_name: "", send_day: 1 })
  const [error, setError] = useState<string | null>(null)
  const [sentTo, setSentTo] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ["client-report-recipients"] })
  const fail = (e: unknown, fallback: string) => {
    const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
    setError(typeof d === "string" ? d : fallback)
  }

  const add = useMutation({
    mutationFn: () => addReportRecipient({
      server_id: form.server_id,
      recipient_email: form.recipient_email.trim(),
      recipient_name: form.recipient_name.trim() || null,
      send_day: form.send_day,
    }),
    onSuccess: () => {
      invalidate()
      setAdding(false)
      setForm({ server_id: "", recipient_email: "", recipient_name: "", send_day: 1 })
    },
    onError: (e) => fail(e, "Could not add that recipient."),
  })

  const toggle = useMutation({
    mutationFn: (r: ReportRecipient) => updateReportRecipient(r.id, { is_active: !r.is_active }),
    onSuccess: invalidate,
  })

  const remove = useMutation({
    mutationFn: (id: string) => deleteReportRecipient(id),
    onSuccess: invalidate,
  })

  const sendNow = useMutation({
    mutationFn: (id: string) => sendReportNow(id),
    onSuccess: (res) => {
      setSentTo(res.to)
      setTimeout(() => setSentTo(null), 3000)
    },
    onError: (e) => fail(e, "Could not send that email."),
  })

  const serverName = (id: string) => servers.find((s) => s.id === id)?.name || "this server"

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <Mail size={15} className="text-primary" />
        <h3 className="text-sm font-semibold">Monthly client reports</h3>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Email a client their own branded report every month — uptime, security and the work
        you did. Free to send: the numbers come from what we already track.
      </p>

      {recipients.length === 0 && !adding && (
        <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
          No one is receiving a monthly report yet.
        </p>
      )}

      {recipients.length > 0 && (
        <ul className="mb-3 space-y-2">
          {recipients.map((r) => (
            <li key={r.id} className="rounded-lg border border-border p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-medium">
                    {r.recipient_name ? `${r.recipient_name} · ` : ""}{r.recipient_email}
                  </p>
                  <p className="mt-0.5 text-[11.5px] text-muted-foreground">
                    {serverName(r.server_id)} · {ordinal(r.send_day)} of each month
                    {r.last_sent && ` · last sent ${new Date(r.last_sent).toLocaleDateString()}`}
                    {!r.is_active && " · paused"}
                    {r.last_status === "failed" && (
                      <span className="text-red-600 dark:text-red-400"> · last send failed</span>
                    )}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button
                    title="Send now"
                    onClick={() => { setError(null); sendNow.mutate(r.id) }}
                    disabled={sendNow.isPending}
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  >
                    {sentTo === r.recipient_email
                      ? <Check size={14} className="text-emerald-600" />
                      : <Send size={14} />}
                  </button>
                  <button
                    title={r.is_active ? "Pause" : "Resume"}
                    onClick={() => toggle.mutate(r)}
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  >
                    {r.is_active ? <Pause size={14} /> : <Play size={14} />}
                  </button>
                  <button
                    title="Remove"
                    onClick={() => remove.mutate(r.id)}
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-red-500/10 hover:text-red-600"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {adding ? (
        <div className="rounded-lg border border-border p-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className={label}>Which server’s report?</label>
              <select
                className={input} value={form.server_id}
                onChange={(e) => setForm({ ...form, server_id: e.target.value })}
              >
                <option value="">Choose a server…</option>
                {servers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </div>
            <div>
              <label className={label}>Client’s email</label>
              <input
                className={input} type="email" placeholder="jane@acmeltd.com"
                value={form.recipient_email}
                onChange={(e) => setForm({ ...form, recipient_email: e.target.value })}
              />
            </div>
            <div>
              <label className={label}>Their name <span className="text-muted-foreground/70">(optional)</span></label>
              <input
                className={input} placeholder="Jane Doe"
                value={form.recipient_name}
                onChange={(e) => setForm({ ...form, recipient_name: e.target.value })}
              />
            </div>
            <div>
              <label className={label}>Send on</label>
              <select
                className={input} value={form.send_day}
                onChange={(e) => setForm({ ...form, send_day: Number(e.target.value) })}
              >
                {/* Capped at 28 so every month actually has this day. */}
                {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
                  <option key={d} value={d}>{ordinal(d)} of each month</option>
                ))}
              </select>
            </div>
          </div>
          <div className="mt-3 flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => { setAdding(false); setError(null) }}>
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={!form.server_id || !form.recipient_email.trim() || add.isPending}
              onClick={() => { setError(null); add.mutate() }}
            >
              {add.isPending ? <><Loader2 size={14} className="animate-spin" /> Adding…</> : "Add recipient"}
            </Button>
          </div>
        </div>
      ) : (
        <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
          <Plus size={14} /> Add a client
        </Button>
      )}

      {error && (
        <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  )
}

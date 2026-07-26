import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import { KeyRound, Plus, Loader2, Copy, Check, Trash2, TriangleAlert } from "lucide-react"
import { listApiKeys, createApiKey, revokeApiKey, type NewApiKey } from "@/api/integrations"
import { Button } from "@/components/ui"

const input =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
const label = "mb-1 block text-xs font-medium text-muted-foreground"

function ago(iso: string | null): string {
  if (!iso) return "never"
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true })
  } catch {
    return "—"
  }
}

/** The one and only time the full key exists in the browser. */
function RevealedKey({ created, onDone }: { created: NewApiKey; onDone: () => void }) {
  const [copied, setCopied] = useState(false)
  return (
    <div className="rounded-lg border border-amber-500/40 bg-amber-500/[0.07] p-3">
      <p className="mb-1 flex items-center gap-1.5 text-[13px] font-semibold text-amber-800 dark:text-amber-300">
        <TriangleAlert size={14} /> Copy this key now
      </p>
      <p className="mb-2 text-[11.5px] text-amber-800/80 dark:text-amber-300/80">
        {created.warning}
      </p>
      <div className="flex items-center gap-1.5">
        <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap rounded-md border border-border bg-background px-2.5 py-2 font-mono text-xs">
          {created.key}
        </code>
        <Button
          size="sm" variant="outline"
          onClick={async () => {
            await navigator.clipboard.writeText(created.key)
            setCopied(true)
            setTimeout(() => setCopied(false), 2000)
          }}
        >
          {copied ? <><Check size={13} className="text-emerald-600" /> Copied</> : <><Copy size={13} /> Copy</>}
        </Button>
      </div>
      <div className="mt-2 flex justify-end">
        <Button size="sm" variant="ghost" onClick={onDone}>I’ve saved it</Button>
      </div>
    </div>
  )
}

/**
 * API keys — so a customer's own scripts, CI jobs and cron can talk to ServerAlly. A browser
 * login lasts 15 minutes, which is no use to a machine.
 */
export default function ApiKeysPanel() {
  const qc = useQueryClient()
  const { data: keys = [] } = useQuery({ queryKey: ["api-keys"], queryFn: listApiKeys })
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ name: "", write: false, expires: "" })
  const [created, setCreated] = useState<NewApiKey | null>(null)
  const [error, setError] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ["api-keys"] })

  const create = useMutation({
    mutationFn: () => createApiKey({
      name: form.name.trim() || "API key",
      scopes: form.write ? ["read", "write"] : ["read"],
      expires_in_days: form.expires ? Number(form.expires) : null,
    }),
    onSuccess: (res) => {
      setCreated(res)
      setAdding(false)
      setForm({ name: "", write: false, expires: "" })
      invalidate()
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(typeof d === "string" ? d : "Could not create the key.")
    },
  })

  const revoke = useMutation({ mutationFn: revokeApiKey, onSuccess: invalidate })
  const live = keys.filter((k) => !k.revoked_at)

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <KeyRound size={15} className="text-primary" />
        <h3 className="text-sm font-semibold">API keys</h3>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        For your own scripts and deploy pipelines — “after my deploy, run this playbook”.
        A key can read your servers and, if you allow it, run playbooks and scans. It can
        never change your password, your security settings, or read a server’s login.
      </p>

      {created && (
        <div className="mb-3">
          <RevealedKey created={created} onDone={() => setCreated(null)} />
        </div>
      )}

      {live.length === 0 && !adding && !created && (
        <p className="mb-3 rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
          No API keys yet.
        </p>
      )}

      {live.length > 0 && (
        <ul className="mb-3 space-y-2">
          {live.map((k) => (
            <li key={k.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border p-3">
              <div className="min-w-0">
                <p className="flex flex-wrap items-center gap-1.5 text-[13px] font-medium">
                  {k.name}
                  <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${
                    k.scopes.includes("write")
                      ? "bg-amber-500/15 text-amber-700 dark:text-amber-300"
                      : "bg-muted text-muted-foreground"}`}>
                    {k.scopes.includes("write") ? "Read + write" : "Read only"}
                  </span>
                </p>
                <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                  {k.prefix}…
                  <span className="ml-2 font-sans">
                    used {ago(k.last_used_at)}
                    {k.expires_at && ` · expires ${ago(k.expires_at)}`}
                  </span>
                </p>
              </div>
              <button
                title="Revoke" onClick={() => revoke.mutate(k.id)}
                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-red-500/10 hover:text-red-600"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}

      {adding ? (
        <div className="rounded-lg border border-border p-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className={label}>What is it for?</label>
              <input className={input} placeholder="GitHub Actions"
                value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <label className={label}>Expires after <span className="text-muted-foreground/70">(optional)</span></label>
              <select className={input} value={form.expires}
                onChange={(e) => setForm({ ...form, expires: e.target.value })}>
                <option value="">Never</option>
                <option value="30">30 days</option>
                <option value="90">90 days</option>
                <option value="365">1 year</option>
              </select>
            </div>
          </div>
          <label className="mt-3 flex cursor-pointer items-start gap-2.5 rounded-lg border border-border p-3">
            <input type="checkbox" className="mt-0.5" checked={form.write}
              onChange={(e) => setForm({ ...form, write: e.target.checked })} />
            <span>
              <span className="block text-[13px] font-medium">Allow it to make changes</span>
              <span className="block text-[11.5px] text-muted-foreground">
                Run playbooks and scans, and acknowledge incidents. Leave off for a key that
                can only read.
              </span>
            </span>
          </label>
          <div className="mt-3 flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => { setAdding(false); setError(null) }}>
              Cancel
            </Button>
            <Button size="sm" disabled={create.isPending}
              onClick={() => { setError(null); create.mutate() }}>
              {create.isPending ? <><Loader2 size={13} className="animate-spin" /> Creating…</> : "Create key"}
            </Button>
          </div>
        </div>
      ) : (
        <Button size="sm" variant="outline" onClick={() => { setCreated(null); setAdding(true) }}>
          <Plus size={14} /> New API key
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

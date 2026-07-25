import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Cloud, Plus, Trash2, CheckCircle2, AlertTriangle, Loader2, RefreshCw, X } from "lucide-react"
import {
  listDestinations, createDestination, testDestination, deleteDestination,
  type BackupDestination, type DestinationBody,
} from "@/api/backups"
import { Button } from "@/components/ui"

/** Provider presets — every one speaks the S3 API; the endpoint is what differs. */
const PROVIDERS: { value: string; label: string; endpointHint: string; needsEndpoint: boolean }[] = [
  { value: "s3", label: "Amazon S3", endpointHint: "", needsEndpoint: false },
  { value: "r2", label: "Cloudflare R2", endpointHint: "https://<account-id>.r2.cloudflarestorage.com", needsEndpoint: true },
  { value: "b2", label: "Backblaze B2", endpointHint: "https://s3.us-west-004.backblazeb2.com", needsEndpoint: true },
  { value: "spaces", label: "DigitalOcean Spaces", endpointHint: "https://nyc3.digitaloceanspaces.com", needsEndpoint: true },
  { value: "wasabi", label: "Wasabi", endpointHint: "https://s3.wasabisys.com", needsEndpoint: true },
  { value: "minio", label: "MinIO / other S3", endpointHint: "https://minio.example.com", needsEndpoint: true },
]

const input =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
const label = "mb-1 block text-xs font-medium text-muted-foreground"

function AddDestinationForm({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState<DestinationBody>({
    name: "", provider: "r2", bucket: "", region: "auto",
    endpoint_url: "", prefix: "", access_key_id: "", secret_key: "",
  })
  const [error, setError] = useState<string | null>(null)
  const preset = PROVIDERS.find((p) => p.value === form.provider)!

  const save = useMutation({
    mutationFn: () =>
      createDestination({
        ...form,
        region: form.region?.trim() || null,
        endpoint_url: form.endpoint_url?.trim() || null,
        prefix: form.prefix?.trim() || null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["backup-destinations"] })
      onClose()
    },
    onError: (e: unknown) => {
      const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(typeof detail === "string" ? detail : "Could not save this destination.")
    },
  })

  const ready = form.name && form.bucket && form.access_key_id && form.secret_key &&
    (!preset.needsEndpoint || form.endpoint_url)

  return (
    <div className="rounded-xl border border-border bg-muted/30 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="text-sm font-semibold">Add offsite storage</h4>
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-accent">
          <X size={15} />
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={label}>Name</label>
          <input className={input} placeholder="R2 — main" value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>
        <div>
          <label className={label}>Provider</label>
          <select className={input} value={form.provider}
            onChange={(e) => {
              const p = PROVIDERS.find((x) => x.value === e.target.value)!
              setForm({ ...form, provider: p.value, region: p.value === "r2" ? "auto" : form.region })
            }}>
            {PROVIDERS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </select>
        </div>
        <div>
          <label className={label}>Bucket</label>
          <input className={input} placeholder="my-backups" value={form.bucket}
            onChange={(e) => setForm({ ...form, bucket: e.target.value })} />
        </div>
        <div>
          <label className={label}>Region {form.provider === "s3" && <span className="text-muted-foreground/70">(e.g. eu-west-1)</span>}</label>
          <input className={input} value={form.region ?? ""}
            onChange={(e) => setForm({ ...form, region: e.target.value })} />
        </div>
        {preset.needsEndpoint && (
          <div className="sm:col-span-2">
            <label className={label}>Endpoint URL</label>
            <input className={`${input} font-mono text-xs`} placeholder={preset.endpointHint}
              value={form.endpoint_url ?? ""}
              onChange={(e) => setForm({ ...form, endpoint_url: e.target.value })} />
          </div>
        )}
        <div>
          <label className={label}>Access key ID</label>
          <input className={`${input} font-mono text-xs`} autoComplete="off" value={form.access_key_id}
            onChange={(e) => setForm({ ...form, access_key_id: e.target.value })} />
        </div>
        <div>
          <label className={label}>Secret key</label>
          <input type="password" className={`${input} font-mono text-xs`} autoComplete="new-password"
            value={form.secret_key ?? ""}
            onChange={(e) => setForm({ ...form, secret_key: e.target.value })} />
        </div>
        <div className="sm:col-span-2">
          <label className={label}>Folder inside the bucket <span className="text-muted-foreground/70">(optional)</span></label>
          <input className={`${input} font-mono text-xs`} placeholder="serverally/"
            value={form.prefix ?? ""} onChange={(e) => setForm({ ...form, prefix: e.target.value })} />
        </div>
      </div>

      {error && (
        <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      <p className="mt-3 text-[11px] text-muted-foreground">
        Your keys stay in ServerAlly — they are encrypted and never sent to your servers. We check we can
        actually write to the bucket before saving.
      </p>

      <div className="mt-3 flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
        <Button size="sm" disabled={!ready || save.isPending} onClick={() => { setError(null); save.mutate() }}>
          {save.isPending ? <><Loader2 size={14} className="animate-spin" /> Checking…</> : "Add destination"}
        </Button>
      </div>
    </div>
  )
}

function DestinationRow({ dest }: { dest: BackupDestination }) {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: ["backup-destinations"] })
  const test = useMutation({ mutationFn: () => testDestination(dest.id), onSuccess: refresh })
  const remove = useMutation({ mutationFn: () => deleteDestination(dest.id), onSuccess: refresh })

  return (
    <li className="flex items-start justify-between gap-3 rounded-lg border border-border bg-background px-3 py-2.5">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Cloud size={14} className="shrink-0 text-primary" />
          <span className="truncate text-sm font-medium">{dest.name}</span>
          <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] uppercase text-muted-foreground">
            {dest.provider}
          </span>
          {dest.last_status === "ok" && (
            <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 size={11} /> reachable
            </span>
          )}
          {dest.last_status === "failed" && (
            <span className="inline-flex items-center gap-1 text-[11px] text-red-600 dark:text-red-400">
              <AlertTriangle size={11} /> problem
            </span>
          )}
        </div>
        <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground">
          {dest.bucket}{dest.prefix ? `/${dest.prefix.replace(/^\/+|\/+$/g, "")}` : ""}
        </p>
        {dest.last_status === "failed" && dest.last_error && (
          <p className="mt-1 text-[11px] text-red-600 dark:text-red-400">{dest.last_error}</p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Button size="sm" variant="ghost" title="Test now"
          disabled={test.isPending} onClick={() => test.mutate()}>
          {test.isPending ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
        </Button>
        <Button size="sm" variant="ghost" disabled={remove.isPending}
          onClick={() => {
            if (window.confirm(`Remove "${dest.name}"? Backup jobs using it will fall back to local-only. Your stored files are not deleted.`))
              remove.mutate()
          }}
          className="text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-400 dark:hover:bg-red-950/30">
          <Trash2 size={14} />
        </Button>
      </div>
    </li>
  )
}

/** Offsite storage destinations — reusable across every backup job. */
export default function DestinationManager() {
  const [adding, setAdding] = useState(false)
  const { data: dests = [], isLoading } = useQuery({
    queryKey: ["backup-destinations"],
    queryFn: listDestinations,
  })

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Offsite storage</h3>
        {!adding && (
          <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
            <Plus size={14} /> Add
          </Button>
        )}
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Send a copy of each backup to object storage, so a lost server does not take the backups with it.
      </p>

      {adding && <div className="mb-3"><AddDestinationForm onClose={() => setAdding(false)} /></div>}

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : dests.length === 0 && !adding ? (
        <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
          No offsite storage yet. Backups are kept only on the server itself.
        </div>
      ) : (
        <ul className="space-y-2">{dests.map((d) => <DestinationRow key={d.id} dest={d} />)}</ul>
      )}
    </div>
  )
}

import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Globe2, Plus, Trash2, ExternalLink, Loader2, X, Copy, Check, EyeOff } from "lucide-react"
import {
  listStatusPages, createStatusPage, updateStatusPage, deleteStatusPage,
  type StatusPage,
} from "@/api/statusPages"
import { listMonitors } from "@/api/uptime"
import { Button } from "@/components/ui"

const input =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
const label = "mb-1 block text-xs font-medium text-muted-foreground"

function slugify(text: string): string {
  const s = text.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64)
  return s.replace(/-+$/, "") || "my-status"
}

function pageUrl(slug: string): string {
  return `${window.location.origin}/status/${slug}`
}

function AddPageForm({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient()
  const { data: monitors = [] } = useQuery({ queryKey: ["uptime-monitors", "all"], queryFn: () => listMonitors() })
  const [title, setTitle] = useState("")
  const [slug, setSlug] = useState("")
  const [slugEdited, setSlugEdited] = useState(false)
  const [description, setDescription] = useState("")
  const [selected, setSelected] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: () =>
      createStatusPage({
        title, slug: slug || slugify(title), description: description.trim() || null,
        is_public: true,
        items: Object.entries(selected).map(([monitor_id, display_name]) => ({
          monitor_id, display_name: display_name.trim() || null,
        })),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["status-pages"] })
      onClose()
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(typeof d === "string" ? d : "Could not create this page.")
    },
  })

  const effectiveSlug = slug || slugify(title)

  return (
    <div className="rounded-xl border border-border bg-muted/30 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="text-sm font-semibold">New status page</h4>
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-accent">
          <X size={15} />
        </button>
      </div>

      <div className="space-y-3">
        <div>
          <label className={label}>Page title</label>
          <input className={input} placeholder="Acme Status" value={title}
            onChange={(e) => {
              setTitle(e.target.value)
              if (!slugEdited) setSlug(slugify(e.target.value))
            }} />
        </div>
        <div>
          <label className={label}>Public address</label>
          <div className="flex items-center gap-1 rounded-lg border border-border bg-background px-3 py-2 text-sm">
            <span className="shrink-0 text-muted-foreground">{window.location.origin}/status/</span>
            <input className="min-w-0 flex-1 bg-transparent outline-none" placeholder="my-status"
              value={slug} onChange={(e) => { setSlugEdited(true); setSlug(slugify(e.target.value)) }} />
          </div>
          <p className="mt-1 text-[11px] text-muted-foreground">
            Anyone with this link can see it — that is the point. Lowercase letters, numbers and hyphens.
          </p>
        </div>
        <div>
          <label className={label}>Short description <span className="text-muted-foreground/70">(optional)</span></label>
          <input className={input} placeholder="Live status of our services" value={description}
            onChange={(e) => setDescription(e.target.value)} />
        </div>

        <div>
          <label className={label}>What to show</label>
          {monitors.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
              You need at least one site being watched first — add one under “Site uptime”.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {monitors.map((m) => {
                const on = m.id in selected
                return (
                  <li key={m.id} className={`rounded-lg border p-2.5 ${on ? "border-primary bg-primary/5" : "border-border"}`}>
                    <label className="flex cursor-pointer items-center gap-2">
                      <input type="checkbox" checked={on}
                        onChange={(e) =>
                          setSelected((prev) => {
                            const next = { ...prev }
                            if (e.target.checked) next[m.id] = m.name
                            else delete next[m.id]
                            return next
                          })} />
                      <span className="text-[13px] font-medium">{m.name}</span>
                    </label>
                    {on && (
                      <div className="mt-2 pl-6">
                        <label className="mb-1 block text-[11px] text-muted-foreground">
                          Name shown to visitors
                        </label>
                        <input className={`${input} py-1.5 text-[13px]`} value={selected[m.id]}
                          onChange={(e) => setSelected((p) => ({ ...p, [m.id]: e.target.value }))} />
                        <p className="mt-1 text-[11px] text-muted-foreground">
                          Visitors see this name only — never the address you monitor or the server behind it.
                        </p>
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>

      {error && (
        <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      <div className="mt-3 flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
        <Button size="sm"
          disabled={!title || !effectiveSlug || !Object.keys(selected).length || save.isPending}
          onClick={() => { setError(null); save.mutate() }}>
          {save.isPending ? <><Loader2 size={14} className="animate-spin" /> Creating…</> : "Publish page"}
        </Button>
      </div>
    </div>
  )
}

function PageRow({ page }: { page: StatusPage }) {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: ["status-pages"] })
  const [copied, setCopied] = useState(false)
  const toggle = useMutation({
    mutationFn: () => updateStatusPage(page.id, { is_public: !page.is_public }),
    onSuccess: refresh,
  })
  const remove = useMutation({ mutationFn: () => deleteStatusPage(page.id), onSuccess: refresh })

  const url = pageUrl(page.slug)
  return (
    <li className="rounded-lg border border-border bg-background px-3 py-2.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-medium">{page.title}</span>
            {page.is_public ? (
              <span className="rounded-full bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                live
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                <EyeOff size={9} /> hidden
              </span>
            )}
          </div>
          <a href={url} target="_blank" rel="noreferrer"
            className="mt-0.5 inline-flex items-center gap-1 truncate font-mono text-[11px] text-muted-foreground hover:text-foreground hover:underline">
            /status/{page.slug} <ExternalLink size={9} />
          </a>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {page.items.length} item{page.items.length === 1 ? "" : "s"} shown
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button size="sm" variant="ghost" title="Copy link"
            onClick={() => {
              void navigator.clipboard.writeText(url)
              setCopied(true)
              setTimeout(() => setCopied(false), 1500)
            }}>
            {copied ? <Check size={14} className="text-emerald-500" /> : <Copy size={14} />}
          </Button>
          <Button size="sm" variant="ghost" title={page.is_public ? "Take offline" : "Publish"}
            disabled={toggle.isPending} onClick={() => toggle.mutate()}>
            <EyeOff size={14} />
          </Button>
          <Button size="sm" variant="ghost" disabled={remove.isPending}
            onClick={() => { if (window.confirm(`Delete "${page.title}"? The link will stop working.`)) remove.mutate() }}
            className="text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-400 dark:hover:bg-red-950/30">
            <Trash2 size={14} />
          </Button>
        </div>
      </div>
    </li>
  )
}

/** Public status pages — a link you can give customers so they stop asking "is it down?". */
export default function StatusPagesPanel() {
  const [adding, setAdding] = useState(false)
  const { data: pages = [], isLoading } = useQuery({
    queryKey: ["status-pages"],
    queryFn: listStatusPages,
  })

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Globe2 size={15} className="text-primary" />
          Status pages
        </h3>
        {!adding && (
          <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
            <Plus size={14} /> New page
          </Button>
        )}
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        A public link you can give customers. It shows only the names you choose and whether they are up.
      </p>

      {adding && <div className="mb-3"><AddPageForm onClose={() => setAdding(false)} /></div>}

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : pages.length === 0 && !adding ? (
        <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
          No status page yet.
        </div>
      ) : (
        <ul className="space-y-2">{pages.map((p) => <PageRow key={p.id} page={p} />)}</ul>
      )}
    </div>
  )
}

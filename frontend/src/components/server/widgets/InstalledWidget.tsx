import { useState, type ReactNode } from "react"
import { useQuery, useMutation } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import {
  Package, ScanLine, Loader2, ExternalLink, ChevronDown, ChevronRight, Eye, EyeOff, Copy, Check,
} from "lucide-react"
import { getInstalled, scanServer, revealInstall, type InstalledItem } from "@/api/installed"

function fmtInstalled(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  return `${d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })} · ${formatDistanceToNow(d, { addSuffix: true })}`
}

function CopyBtn({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      aria-label="Copy"
      onClick={() => {
        void navigator.clipboard?.writeText(value)
        setCopied(true)
        setTimeout(() => setCopied(false), 1200)
      }}
      className="shrink-0 text-muted-foreground hover:text-foreground"
    >
      {copied ? <Check size={12} className="text-green-500" /> : <Copy size={12} />}
    </button>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-28 shrink-0 truncate font-mono text-muted-foreground">{label}</span>
      <div className="flex min-w-0 flex-1 items-center gap-1.5">{children}</div>
    </div>
  )
}

/** One install — collapsed to title + age; expands to full detail with a reveal toggle
 * that decrypts credentials on demand (owner-only, audited server-side). */
function InstalledItemRow({ serverId, item }: { serverId: string; item: InstalledItem }) {
  const [open, setOpen] = useState(false)
  const [shown, setShown] = useState(false)
  const reveal = useMutation({
    mutationFn: () => revealInstall(serverId, item.run_id),
    onSuccess: () => setShown(true),
  })
  const revealed = shown ? reveal.data : undefined
  const access = revealed?.access ?? item.access
  const vars = Object.entries(revealed?.variables ?? item.variables ?? {})

  function toggleReveal() {
    if (shown) setShown(false)
    else if (reveal.data) setShown(true)
    else reveal.mutate()
  }

  return (
    <div className="rounded-md border border-border/60 bg-background">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        {open ? (
          <ChevronDown size={13} className="shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight size={13} className="shrink-0 text-muted-foreground" />
        )}
        <span className="truncate text-sm font-medium text-foreground">{item.playbook_title}</span>
        {item.installed_at && (
          <span className="ml-auto shrink-0 text-xs text-muted-foreground">
            {formatDistanceToNow(new Date(item.installed_at), { addSuffix: true })}
          </span>
        )}
      </button>

      {open && (
        <div className="space-y-1.5 border-t border-border/60 px-3 py-2.5 text-xs">
          <Row label="Installed">
            <span className="text-foreground">{fmtInstalled(item.installed_at)}</span>
          </Row>

          {access?.url && (
            <Row label="URL">
              <a
                href={access.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex min-w-0 items-center gap-1 text-primary hover:underline"
              >
                <ExternalLink size={11} className="shrink-0" />
                <span className="truncate">{access.url.replace(/^https?:\/\//, "")}</span>
              </a>
              <CopyBtn value={access.url} />
            </Row>
          )}

          {access?.username && (
            <Row label="Username">
              <span className="truncate font-mono text-foreground">{access.username}</span>
              <CopyBtn value={access.username} />
            </Row>
          )}

          {vars.length > 0 && (
            <div className="border-t border-border/60 pt-2">
              <p className="mb-1.5 text-[11px] uppercase tracking-wide text-muted-foreground/70">Details</p>
              <div className="space-y-1.5">
                {vars.map(([k, v]) => (
                  <Row key={k} label={k}>
                    <span className="truncate font-mono text-foreground">{v}</span>
                    {revealed && v && v !== "••••••" && <CopyBtn value={v} />}
                  </Row>
                ))}
              </div>
            </div>
          )}

          {access?.note && <p className="pt-1 leading-relaxed text-muted-foreground">{access.note}</p>}

          {item.has_secrets && (
            <button
              type="button"
              onClick={toggleReveal}
              disabled={reveal.isPending}
              className="mt-1 flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-muted-foreground hover:bg-accent disabled:opacity-50"
            >
              {reveal.isPending ? (
                <Loader2 size={12} className="animate-spin" />
              ) : shown ? (
                <EyeOff size={12} />
              ) : (
                <Eye size={12} />
              )}
              {shown ? "Hide credentials" : "Reveal credentials"}
            </button>
          )}
          {reveal.isError && <p className="text-red-400">Couldn't reveal — try again.</p>}
        </div>
      )}
    </div>
  )
}

/** Read-only "what's installed" widget — expandable items with details + reveal, plus an
 * on-demand live scan. */
export default function InstalledWidget({ serverId }: { serverId: string }) {
  const { data: items = [], isLoading } = useQuery({
    queryKey: ["installed", serverId],
    queryFn: () => getInstalled(serverId),
  })
  const scan = useMutation({ mutationFn: () => scanServer(serverId) })

  const detected = scan.data && scan.data.supported !== false
    ? [scan.data.os, ...scan.data.web_servers, ...scan.data.databases, ...scan.data.runtimes].filter(Boolean)
    : []

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-sm font-medium text-foreground">
          <Package size={14} /> Installed
        </h3>
        <button
          onClick={() => scan.mutate()}
          disabled={scan.isPending}
          className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-accent disabled:opacity-50"
        >
          {scan.isPending ? <Loader2 size={12} className="animate-spin" /> : <ScanLine size={12} />}
          {scan.isPending ? "Scanning…" : "Scan"}
        </button>
      </div>

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          Nothing installed through ServerAlly yet — run a playbook, or scan to see what's already here.
        </p>
      ) : (
        <div className="space-y-2">
          {items.slice(0, 6).map((it) => (
            <InstalledItemRow key={it.run_id} serverId={serverId} item={it} />
          ))}
        </div>
      )}

      {detected.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-border pt-3">
          <span className="text-xs text-muted-foreground">Detected:</span>
          {detected.slice(0, 6).map((s, i) => (
            <span key={i} className="rounded-full bg-muted px-2 py-0.5 text-xs text-foreground">{s}</span>
          ))}
        </div>
      )}
      {scan.isError && <p className="mt-2 text-xs text-red-400">Scan failed — the server may be offline.</p>}
    </div>
  )
}

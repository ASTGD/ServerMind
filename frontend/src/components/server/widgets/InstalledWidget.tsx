import { useState, type ReactNode } from "react"
import { useQuery, useMutation } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import {
  Package, ScanLine, Loader2, ExternalLink, ChevronDown, ChevronRight, Eye, EyeOff,
  Copy, Check, AlertTriangle,
} from "lucide-react"
import { getInstalled, scanServer, revealInstall, type InstalledItem } from "@/api/installed"

function fmtInstalled(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  return `${d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })} · ${formatDistanceToNow(d, { addSuffix: true })}`
}

/** The explicit port in an access URL, or null for a default (80/443) / unparseable URL. */
function urlPort(url?: string | null): string | null {
  if (!url) return null
  try {
    return new URL(url).port || null
  } catch {
    return null
  }
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
      {copied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
    </button>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-32 shrink-0 truncate font-mono text-muted-foreground">{label}</span>
      <div className="flex min-w-0 flex-1 items-center gap-1.5">{children}</div>
    </div>
  )
}

/** One install — collapsed to title + age; expands to full detail with a reveal toggle
 * that decrypts credentials on demand. `detectedPorts` (from a live scan) lets us flag a
 * record that isn't actually running anymore (e.g. wiped by a server rebuild). */
function InstalledItemRow({
  serverId,
  item,
  detectedPorts,
}: {
  serverId: string
  item: InstalledItem
  detectedPorts: string[] | null
}) {
  const [open, setOpen] = useState(false)
  const [shown, setShown] = useState(false)
  const reveal = useMutation({
    mutationFn: () => revealInstall(serverId, item.run_id),
    onSuccess: () => setShown(true),
  })
  const revealed = shown ? reveal.data : undefined
  const access = revealed?.access ?? item.access
  const vars = Object.entries(revealed?.variables ?? item.variables ?? {})

  // After a scan, a record with a distinctive (non-80/443) port that isn't listening is a
  // ghost — it was installed once but isn't running now.
  const port = urlPort(item.access?.url)
  const notDetected = detectedPorts !== null && port !== null && !detectedPorts.includes(port)

  function toggleReveal() {
    if (shown) setShown(false)
    else if (reveal.data) setShown(true)
    else reveal.mutate()
  }

  return (
    <div className={`rounded-md border bg-background ${notDetected ? "border-amber-500/40" : "border-border/60"}`}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left"
      >
        {open ? (
          <ChevronDown size={15} className="shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight size={15} className="shrink-0 text-muted-foreground" />
        )}
        <span className="truncate text-base font-medium text-foreground">{item.playbook_title}</span>
        {notDetected && (
          <span className="ml-1 shrink-0 rounded-full bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-600 dark:text-amber-400">
            not detected
          </span>
        )}
        {item.installed_at && (
          <span className="ml-auto shrink-0 text-sm text-muted-foreground">
            {formatDistanceToNow(new Date(item.installed_at), { addSuffix: true })}
          </span>
        )}
      </button>

      {open && (
        <div className="space-y-2 border-t border-border/60 px-3.5 py-3 text-sm">
          {notDetected && (
            <div className="flex items-start gap-1.5 rounded-md bg-amber-500/10 px-2.5 py-2 text-amber-600 dark:text-amber-400">
              <AlertTriangle size={15} className="mt-0.5 shrink-0" />
              <span>
                Not running on the server right now — it may have been removed, or the server was
                rebuilt since this was installed.
              </span>
            </div>
          )}

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
                <ExternalLink size={13} className="shrink-0" />
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
              <p className="mb-1.5 text-xs uppercase tracking-wide text-muted-foreground/70">
                Details
              </p>
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
              className="mt-1 flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent disabled:opacity-50"
            >
              {reveal.isPending ? (
                <Loader2 size={14} className="animate-spin" />
              ) : shown ? (
                <EyeOff size={14} />
              ) : (
                <Eye size={14} />
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
 * on-demand live scan that also flags records no longer running on the box. */
export default function InstalledWidget({ serverId }: { serverId: string }) {
  const { data: items = [], isLoading } = useQuery({
    queryKey: ["installed", serverId],
    queryFn: () => getInstalled(serverId),
  })
  const scan = useMutation({ mutationFn: () => scanServer(serverId) })

  const scanOk = scan.data && scan.data.supported !== false
  const detectedPorts = scanOk ? scan.data!.ports : null
  const detected = scanOk
    ? [scan.data!.os, ...scan.data!.web_servers, ...scan.data!.databases, ...scan.data!.runtimes].filter(Boolean)
    : []

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-base font-medium text-foreground">
          <Package size={16} /> Installed
        </h3>
        <button
          onClick={() => scan.mutate()}
          disabled={scan.isPending}
          className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent disabled:opacity-50"
        >
          {scan.isPending ? <Loader2 size={14} className="animate-spin" /> : <ScanLine size={14} />}
          {scan.isPending ? "Scanning…" : "Scan"}
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Nothing installed through ServerAlly yet — run a playbook, or scan to see what's already here.
        </p>
      ) : (
        <div className="space-y-2">
          {items.slice(0, 6).map((it) => (
            <InstalledItemRow key={it.run_id} serverId={serverId} item={it} detectedPorts={detectedPorts} />
          ))}
        </div>
      )}

      {detected.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-border pt-3">
          <span className="text-sm text-muted-foreground">Detected:</span>
          {detected.slice(0, 8).map((s, i) => (
            <span key={i} className="rounded-full bg-muted px-2 py-0.5 text-sm text-foreground">{s}</span>
          ))}
        </div>
      )}
      {scan.isError && <p className="mt-2 text-sm text-red-400">Scan failed — the server may be offline.</p>}
    </div>
  )
}

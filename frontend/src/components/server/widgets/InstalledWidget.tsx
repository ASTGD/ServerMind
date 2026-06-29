import { useQuery, useMutation } from "@tanstack/react-query"
import { Package, ScanLine, Loader2, ExternalLink } from "lucide-react"
import { getInstalled, scanServer } from "@/api/installed"

/** Read-only "what's installed" widget — access cards + an on-demand live scan, inline.
 * Replaces the standalone Installed page for at-a-glance use. */
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
          {items.slice(0, 4).map((it) => (
            <div key={it.run_id} className="rounded-md border border-border/60 bg-background px-3 py-2">
              <p className="truncate text-sm font-medium text-foreground">{it.playbook_title}</p>
              {it.access?.url && (
                <a
                  href={it.access.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={`Open ${it.access.url} in a new tab`}
                  className="mt-1 flex items-center gap-1 text-xs text-primary hover:underline"
                >
                  <ExternalLink size={11} className="shrink-0" />
                  <span className="truncate">{it.access.url.replace(/^https?:\/\//, "")}</span>
                </a>
              )}
              {it.access?.note && (
                <p className="mt-0.5 truncate text-xs text-muted-foreground">{it.access.note}</p>
              )}
            </div>
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

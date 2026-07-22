import { useState } from "react"
import { useParams, Link } from "react-router-dom"
import { useQuery, useMutation } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import {
  ArrowLeft,
  Package,
  ScanLine,
  Loader2,
  Server as ServerIcon,
  Globe,
  Database,
  Boxes,
  Cpu,
  LayoutPanelLeft,
  Network,
  ChevronDown,
  ChevronRight,
} from "lucide-react"
import { getServer } from "@/api/servers"
import { getInstalled, scanServer, type InstalledItem, type ScanResult } from "@/api/installed"
import { AccessCard } from "@/components/playbooks/AccessCard"

/** One installed-by-ServerAlly item: title, when, access card, and masked install inputs. */
function InstalledCard({ item }: { item: InstalledItem }) {
  const [open, setOpen] = useState(false)
  const vars = Object.entries(item.variables ?? {})
  const hasAccess = item.access && (item.access.url || item.access.username || item.access.note)
  return (
    <div className="rounded-xl border border-border bg-card p-4 space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h3 className="font-medium text-foreground">{item.playbook_title}</h3>
        {item.installed_at && (
          <span className="shrink-0 text-xs text-muted-foreground">
            installed {formatDistanceToNow(new Date(item.installed_at), { addSuffix: true })}
          </span>
        )}
      </div>

      {hasAccess && <AccessCard access={item.access!} />}

      {vars.length > 0 && (
        <div>
          <button
            onClick={() => setOpen((v) => !v)}
            className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            Install details
          </button>
          {open && (
            <div className="mt-2 space-y-1 text-xs">
              {vars.map(([k, v]) => (
                <div key={k} className="flex gap-2">
                  <span className="w-36 shrink-0 font-mono text-muted-foreground">{k}</span>
                  <span className="break-all font-mono text-foreground">{v}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const SCAN_GROUPS: { key: keyof ScanResult; label: string; Icon: typeof Globe }[] = [
  { key: "web_servers", label: "Web servers", Icon: Globe },
  { key: "databases", label: "Databases", Icon: Database },
  { key: "runtimes", label: "Runtimes", Icon: Cpu },
  { key: "containers", label: "Containers", Icon: Boxes },
  { key: "panels", label: "Control panels", Icon: LayoutPanelLeft },
  { key: "ports", label: "Listening ports", Icon: Network },
]

/** Render a live scan result as grouped chips. */
function ScanView({ data }: { data: ScanResult }) {
  if (data.supported === false) {
    return (
      <p className="text-sm text-muted-foreground">
        Live scan is available for Linux (SSH) servers.
      </p>
    )
  }
  const groups = [
    { label: "Operating system", Icon: ServerIcon, items: data.os ? [data.os] : [] },
    ...SCAN_GROUPS.map((g) => ({ label: g.label, Icon: g.Icon, items: (data[g.key] as string[]) ?? [] })),
  ].filter((g) => g.items.length > 0)

  if (groups.length === 0) {
    return <p className="text-sm text-muted-foreground">No common software detected.</p>
  }
  return (
    <div className="divide-y divide-border rounded-xl border border-border bg-card">
      {groups.map((g) => (
        <div key={g.label} className="flex items-start gap-3 p-3">
          <g.Icon className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0">
            <p className="text-xs text-muted-foreground">{g.label}</p>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {g.items.map((it, i) => (
                <span
                  key={i}
                  className="rounded border border-border bg-muted px-2 py-0.5 font-mono text-xs text-foreground"
                >
                  {it}
                </span>
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

export default function Installed() {
  const { id } = useParams<{ id: string }>()
  const { data: server } = useQuery({ queryKey: ["server", id], queryFn: () => getServer(id!), enabled: !!id })
  const { data: items = [], isLoading } = useQuery({
    queryKey: ["installed", id],
    queryFn: () => getInstalled(id!),
    enabled: !!id,
  })
  const scan = useMutation({ mutationFn: () => scanServer(id!) })

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div>
        <Link
          to={`/servers/${id}`}
          className="mb-4 flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> {server?.name ?? "Server"}
        </Link>
        <h1 className="flex items-center gap-2 text-h1 text-foreground">
          <Package className="h-6 w-6 text-primary" /> Installed software
        </h1>
        <p className="mt-1 text-muted-foreground">
          What's installed on {server?.name ?? "this server"}, and how to reach it.
        </p>
      </div>

      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-foreground">Installed by ServerAlly</h2>
        {isLoading ? (
          <div className="flex items-center gap-2 text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading…
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
            Nothing installed through ServerAlly yet. Run a playbook, or scan the server below to
            see what's already there.
          </div>
        ) : (
          <div className="space-y-4">
            {items.map((it) => (
              <InstalledCard key={it.run_id} item={it} />
            ))}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-foreground">Detected on the server</h2>
            <p className="text-xs text-muted-foreground">
              A live read-only scan — catches anything installed outside ServerAlly too.
            </p>
          </div>
          <button
            onClick={() => scan.mutate()}
            disabled={scan.isPending}
            className="flex shrink-0 items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {scan.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanLine className="h-4 w-4" />}
            {scan.isPending ? "Scanning…" : "Scan server"}
          </button>
        </div>
        {scan.isError && (
          <p className="text-sm text-red-400">Scan failed — the server may be offline or unreachable.</p>
        )}
        {scan.data && <ScanView data={scan.data} />}
      </section>
    </div>
  )
}

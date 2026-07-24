import { useEffect, useRef } from "react"
import { useQuery } from "@tanstack/react-query"
import { Loader2, CheckCircle2, Ban, XCircle, Server as ServerIcon, ChevronUp, Activity } from "lucide-react"
import { listMcpConnections, type McpActivityItem } from "@/api/mcp"
import { useMcpActivity } from "@/hooks/useMcpActivity"
import { useMcpDrawerStore } from "@/store/mcpDrawerStore"

function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 5) return "just now"
  if (s < 60) return `${Math.floor(s)}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return new Date(iso).toLocaleDateString()
}

function duration(a: McpActivityItem): string | null {
  const start = new Date(a.started_at).getTime()
  const end = a.finished_at ? new Date(a.finished_at).getTime() : Date.now()
  const s = Math.max(0, Math.round((end - start) / 1000))
  return s >= 1 ? `${s}s` : null
}

function StatusIcon({ status }: { status: McpActivityItem["status"] }) {
  if (status === "running") return <Loader2 size={15} className="shrink-0 animate-spin text-primary" />
  if (status === "ok") return <CheckCircle2 size={15} className="shrink-0 text-emerald-600 dark:text-emerald-400" />
  if (status === "blocked") return <Ban size={15} className="shrink-0 text-red-600 dark:text-red-400" />
  return <XCircle size={15} className="shrink-0 text-red-600 dark:text-red-400" />
}

function Row({ a }: { a: McpActivityItem }) {
  const running = a.status === "running"
  const dur = duration(a)
  return (
    <li className="rounded-lg border border-border bg-background px-3 py-2.5">
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5">
          <StatusIcon status={a.status} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-sm font-medium">{a.label}</span>
            {a.server_name && (
              <span className="inline-flex items-center gap-1 rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                <ServerIcon size={10} /> {a.server_name}
              </span>
            )}
            {running ? (
              <span className="text-[11px] font-medium text-primary">running{dur ? ` · ${dur}` : ""}…</span>
            ) : (
              typeof a.exit_code === "number" && (
                <span className={`text-[11px] ${a.exit_code === 0 ? "text-muted-foreground" : "text-red-600 dark:text-red-400"}`}>
                  exit {a.exit_code}
                </span>
              )
            )}
          </div>
          {a.command && (
            <code className="mt-1 block overflow-x-auto whitespace-pre rounded bg-muted/60 px-2 py-1 text-[11px] text-foreground/80">
              {a.command}
            </code>
          )}
          <div className="mt-1 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
            <span>{a.client_name}</span>
            <span>·</span>
            <span>{timeAgo(a.started_at)}</span>
            {!running && dur && (
              <>
                <span>·</span>
                <span>{dur}</span>
              </>
            )}
            {a.detail && (
              <>
                <span>·</span>
                <span className={a.status === "blocked" || a.status === "error" ? "text-red-600 dark:text-red-400" : ""}>
                  {a.detail}
                </span>
              </>
            )}
          </div>
        </div>
      </div>
    </li>
  )
}

/**
 * The floating MCP Activity drawer — slides down from the top bar to show what a connected
 * AI is doing live (running → done), and slides back up when collapsed. Mounted globally in
 * Layout so it overlays every page; opened from the top-bar MCP icon (and auto-opens when a
 * new action starts running). Polls ~2s while open; the AI's reasoning stays in its own app,
 * so we show the actions, not the thinking.
 */
export default function McpActivityDrawer() {
  const open = useMcpDrawerStore((s) => s.open)
  const collapse = useMcpDrawerStore((s) => s.collapse)
  const panelRef = useRef<HTMLDivElement>(null)

  const { data: conns } = useQuery({ queryKey: ["mcp-connections"], queryFn: listMcpConnections })
  const hasMcp = (conns?.length ?? 0) > 0
  const { data: items = [] } = useMcpActivity(open, hasMcp)
  const runningCount = items.filter((a) => a.status === "running").length

  // Click outside the panel (but not the top-bar toggle) collapses it.
  useEffect(() => {
    if (!open) return
    function onDown(e: MouseEvent) {
      const t = e.target as HTMLElement
      if (panelRef.current && !panelRef.current.contains(t) && !t.closest("[data-mcp-toggle]")) {
        collapse()
      }
    }
    document.addEventListener("mousedown", onDown)
    return () => document.removeEventListener("mousedown", onDown)
  }, [open, collapse])

  return (
    <div
      ref={panelRef}
      className={`fixed right-3 top-[3.75rem] z-30 w-[min(420px,calc(100vw-1.5rem))] origin-top transition-all duration-300 ease-out ${
        open ? "translate-y-0 opacity-100" : "pointer-events-none -translate-y-3 opacity-0"
      }`}
      aria-hidden={!open}
    >
      <div className="flex max-h-[min(70vh,560px)] flex-col overflow-hidden rounded-xl border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5">
          <div className="flex items-center gap-2">
            <Activity size={15} className="text-primary" />
            <span className="text-sm font-semibold">MCP Activity</span>
            <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-75" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
              </span>
              Live
            </span>
            {runningCount > 0 && (
              <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                {runningCount} running
              </span>
            )}
          </div>
          <button
            onClick={collapse}
            title="Collapse"
            className="flex items-center justify-center rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <ChevronUp size={16} />
          </button>
        </div>
        <p className="border-b border-border px-4 py-2 text-[11px] text-muted-foreground">
          What your connected AI does on your servers, live — the actions (commands, scans), not its private reasoning.
        </p>
        <div className="min-h-0 flex-1 overflow-y-auto p-3">
          {items.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
              No activity yet. When a connected AI runs a command or a scan, it shows here — live.
            </div>
          ) : (
            <ul className="space-y-2">
              {items.map((a) => (
                <Row key={a.id} a={a} />
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}

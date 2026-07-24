import { useQuery } from "@tanstack/react-query"
import { Loader2, CheckCircle2, Ban, XCircle, Server as ServerIcon, Activity } from "lucide-react"
import { listMcpActivity, type McpActivityItem } from "@/api/mcp"

/** Relative "3s ago" / "2m ago". */
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

/** Elapsed seconds a running action has been going, or its total duration when finished. */
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
                <span
                  className={`text-[11px] ${a.exit_code === 0 ? "text-muted-foreground" : "text-red-600 dark:text-red-400"}`}
                >
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
 * Live feed of what connected AI clients DO over MCP (run_command + scans). Polls every ~2s
 * so an action appears as "running…" and then flips to its result — the near-live view of
 * MCP work, since the AI's reasoning lives in its own app and only the actions reach us.
 */
export default function McpActivity() {
  const { data: items = [] } = useQuery({
    queryKey: ["mcp-activity"],
    queryFn: listMcpActivity,
    refetchInterval: 2000,
    refetchIntervalInBackground: false,
  })
  const runningCount = items.filter((a) => a.status === "running").length

  return (
    <div className="mt-5">
      <div className="mb-2 flex items-center gap-2">
        <Activity size={14} className="text-muted-foreground" />
        <h4 className="text-sm font-semibold">Activity</h4>
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
      <p className="mb-2.5 text-xs text-muted-foreground">
        What your connected AI does on your servers, live. We show the actions (commands run, scans) — not the
        AI's private reasoning, which stays in its own app.
      </p>
      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
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
  )
}

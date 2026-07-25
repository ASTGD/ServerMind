import { useEffect, useMemo, useState } from "react"
import { useOutletContext } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { FileText, Search, RefreshCw, Loader2, Sparkles, AlertTriangle } from "lucide-react"
import { listLogs, readLog, type LogFile } from "@/api/logs"
import { redactSecrets } from "@/lib/redactSecrets"
import { useAssistantStore } from "@/store/assistantStore"
import { Button, EmptyState } from "@/components/ui"
import type { Server } from "@/types"

const LINE_OPTIONS = [50, 200, 500, 1000, 2000]

/** Words that mark a line as a problem — kept in step with log_service.line_severity. */
const ERROR_RE = /\b(error|fatal|critical|emerg|alert|panic|denied|failed|failure|exception)\b/i
const WARN_RE = /\b(warn|warning|deprecated|notice)\b/i

function lineClass(line: string): string {
  if (ERROR_RE.test(line)) return "text-red-400"
  if (WARN_RE.test(line)) return "text-amber-400"
  return "text-zinc-300"
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const CATEGORY_ORDER = ["web", "app", "database", "security", "system", "site", "mail"]
const CATEGORY_LABEL: Record<string, string> = {
  web: "Web server", app: "Application", database: "Database",
  security: "Security", system: "System", site: "Sites", mail: "Mail",
}

export default function ServerLogs() {
  const { server } = useOutletContext<{ server: Server }>()
  const openServer = useAssistantStore((s) => s.openServer)

  const [selected, setSelected] = useState<string | null>(null)
  const [lines, setLines] = useState(200)
  const [search, setSearch] = useState("")
  const [appliedSearch, setAppliedSearch] = useState("")
  const [auto, setAuto] = useState(false)

  const { data: files = [], isLoading: loadingList } = useQuery({
    queryKey: ["server-logs", server.id],
    queryFn: () => listLogs(server.id),
  })

  // Default to the first log (the catalogue is ordered most-useful-first).
  useEffect(() => {
    if (!selected && files.length) setSelected(files[0].path)
  }, [files, selected])

  const {
    data: content, isFetching, refetch,
  } = useQuery({
    queryKey: ["server-log", server.id, selected, lines, appliedSearch],
    queryFn: () => readLog(server.id, selected!, lines, appliedSearch || undefined),
    enabled: !!selected,
    refetchInterval: auto ? 10_000 : false,
  })

  const grouped = useMemo(() => {
    const by: Record<string, LogFile[]> = {}
    for (const f of files) (by[f.category] ??= []).push(f)
    return CATEGORY_ORDER.filter((c) => by[c]?.length).map((c) => [c, by[c]] as const)
  }, [files])

  const rows = useMemo(() => (content?.content ?? "").split("\n"), [content])
  const errorCount = useMemo(() => rows.filter((l) => ERROR_RE.test(l)).length, [rows])

  /** Hand the visible log to Ally — secrets are stripped in the BROWSER first, so a
   *  token in a log line never reaches the AI (same rule as the file manager). */
  function askAlly() {
    const tail = rows.slice(-120).join("\n")
    const { text, count } = redactSecrets(tail)
    const label = files.find((f) => f.path === selected)?.label ?? selected
    openServer(
      server,
      `Here are the last lines of ${label} (${selected}) on this server. ` +
        `Tell me in plain language what is wrong and how to fix it.` +
        (count ? ` (${count} secret value(s) were hidden before sending.)` : "") +
        `\n\n\`\`\`\n${text}\n\`\`\``,
    )
  }

  if (server.connection_type !== "ssh") {
    return (
      <EmptyState
        icon={FileText}
        title="Logs need an SSH server"
        description={`This is a '${server.connection_type}' connection, which has no shell to read log files from.`}
      />
    )
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-h1 flex items-center gap-2 text-foreground">
          <FileText className="h-6 w-6 text-primary" />
          Logs
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          What your server is actually saying. Ally can read these and explain the problem.
        </p>
      </div>

      {loadingList ? (
        <div className="flex items-center gap-2 py-12 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Looking for log files…
        </div>
      ) : !files.length ? (
        <EmptyState
          icon={FileText}
          title="No log files found"
          description="We looked in the usual places (nginx, Apache, PHP, MySQL, system). If this server runs everything in Docker, its logs live inside the containers rather than in /var/log."
        />
      ) : (
        <div className="flex flex-col gap-4 lg:flex-row">
          {/* File picker */}
          <div className="w-full shrink-0 lg:w-64">
            <div className="rounded-xl border border-border bg-card p-3">
              {grouped.map(([category, group]) => (
                <div key={category} className="mb-3 last:mb-0">
                  <p className="px-1 pb-1 text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground/60">
                    {CATEGORY_LABEL[category] ?? category}
                  </p>
                  <ul className="space-y-0.5">
                    {group.map((f) => (
                      <li key={f.path}>
                        <button
                          onClick={() => setSelected(f.path)}
                          className={`w-full rounded-lg px-2 py-1.5 text-left transition-colors ${
                            selected === f.path
                              ? "bg-accent text-accent-foreground"
                              : "hover:bg-muted/60"
                          }`}
                        >
                          <span className="block truncate text-[13px] font-medium">{f.label}</span>
                          <span className="block truncate font-mono text-[10.5px] text-muted-foreground">
                            {f.path.split("/").slice(-2).join("/")} · {fmtSize(f.size_bytes)}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </div>

          {/* Viewer */}
          <div className="min-w-0 flex-1 space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative min-w-[180px] flex-1">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") setAppliedSearch(search.trim()) }}
                  placeholder="Search this log…"
                  className="w-full rounded-lg border border-border bg-background py-2 pl-8 pr-3 text-sm outline-none focus:border-primary"
                />
              </div>
              <Button size="sm" variant="outline" onClick={() => setAppliedSearch(search.trim())}>
                Search
              </Button>
              <select
                value={lines}
                onChange={(e) => setLines(Number(e.target.value))}
                className="rounded-lg border border-border bg-background px-2 py-2 text-sm outline-none focus:border-primary"
              >
                {LINE_OPTIONS.map((n) => <option key={n} value={n}>Last {n} lines</option>)}
              </select>
              <Button size="sm" variant="ghost" onClick={() => refetch()} disabled={isFetching} title="Refresh">
                {isFetching ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              </Button>
              <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} />
                Auto
              </label>
              <Button size="sm" onClick={askAlly} disabled={!content?.content}>
                <Sparkles size={14} /> Ask Ally
              </Button>
            </div>

            {appliedSearch && (
              <p className="text-xs text-muted-foreground">
                Showing lines containing “{appliedSearch}”.{" "}
                <button className="underline" onClick={() => { setSearch(""); setAppliedSearch("") }}>
                  Clear
                </button>
              </p>
            )}

            {errorCount > 0 && (
              <p className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
                <AlertTriangle size={13} />
                {errorCount} line{errorCount === 1 ? "" : "s"} look like problems.
              </p>
            )}

            <div className="overflow-hidden rounded-xl border border-black/50 bg-[#0d0d0d]">
              <div className="max-h-[62vh] overflow-auto p-3">
                {isFetching && !content ? (
                  <div className="flex items-center gap-2 py-8 text-sm text-zinc-400">
                    <Loader2 className="h-4 w-4 animate-spin" />Reading…
                  </div>
                ) : !content?.content?.trim() ? (
                  <p className="py-8 text-center text-sm text-zinc-500">
                    {appliedSearch ? "Nothing in this log matches that search." : "This log is empty."}
                  </p>
                ) : (
                  <pre className="whitespace-pre-wrap break-words font-mono text-[11.5px] leading-relaxed">
                    {rows.map((line, i) => (
                      <div key={i} className={lineClass(line)}>{line || " "}</div>
                    ))}
                  </pre>
                )}
              </div>
            </div>

            {content?.truncated && (
              <p className="text-xs text-muted-foreground">
                Very long output — only the most recent part is shown.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { Terminal, PlayCircle, Search, ScrollText, ExternalLink, ArrowLeft } from "lucide-react"
import { listActivity } from "@/api/activity"
import { getCommand } from "@/api/commands"
import { getPlaybookRun } from "@/api/playbooks"
import { listServers } from "@/api/servers"
import type { ActivityItem, Server } from "@/types"
import { failureRemedy } from "@/lib/preflightRemedy"
import { redactSecrets } from "@/lib/redactSecrets"
import { cn } from "@/lib/utils"

// ── Helpers ──────────────────────────────────────────────────────────────────

const STATUS: Record<string, { label: string; cls: string }> = {
  success: { label: "Success", cls: "bg-green-500/10 text-green-600 border-green-500/20" },
  failed: { label: "Failed", cls: "bg-red-500/10 text-red-600 border-red-500/20" },
  partial: { label: "Partial", cls: "bg-amber-500/10 text-amber-600 border-amber-500/20" },
  blocked: { label: "Blocked", cls: "bg-red-500/10 text-red-600 border-red-500/20" },
  cancelled: { label: "Cancelled", cls: "bg-muted text-muted-foreground border-border" },
  running: { label: "Running", cls: "bg-blue-500/10 text-blue-600 border-blue-500/20" },
  pending_approval: { label: "Pending", cls: "bg-amber-500/10 text-amber-600 border-amber-500/20" },
}

function StatusBadge({ status }: { status: string | null }) {
  const s = STATUS[status ?? ""] ?? { label: status ?? "—", cls: "bg-muted text-muted-foreground border-border" }
  return <span className={cn("rounded-full border px-2 py-0.5 text-[11px] font-medium", s.cls)}>{s.label}</span>
}

function fmtDuration(ms: number | null): string | null {
  if (ms == null) return null
  if (ms < 1000) return `${ms}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)}s`
  const m = Math.floor(s / 60)
  return `${m}m ${Math.round(s % 60)}s`
}

function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return "just now"
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d}d ago`
  return new Date(iso).toLocaleDateString()
}

type KindFilter = "all" | "playbook" | "command"
const keyOf = (a: ActivityItem) => `${a.kind}-${a.id}`

// ── Detail pane ────────────────────────────────────────────────────────────────

function OutputBlock({ text }: { text: string }) {
  return (
    <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-all rounded-lg bg-[#0d0d0d] p-3 font-mono text-[11.5px] leading-relaxed text-zinc-300">
      {redactSecrets(text).text}
    </pre>
  )
}

/** Shell of the detail card — header (title, status, server, meta) + children. */
function DetailShell({
  item, serverName, title, children,
}: { item: ActivityItem; serverName: (id: string | null) => string; title: string; children: React.ReactNode }) {
  const dur = fmtDuration(item.duration_ms)
  const Icon = item.kind === "command" ? Terminal : PlayCircle
  return (
    <div>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
            <Icon size={15} />
          </span>
          <div className="min-w-0">
            <h2 className="break-words text-[15px] font-semibold leading-snug text-foreground">{title}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground">
              <span>{item.kind === "command" ? "AI command" : "Playbook"}</span>
              {item.server_id && (
                <>
                  <span>·</span>
                  <Link to={`/servers/${item.server_id}`} className="inline-flex items-center gap-0.5 hover:text-foreground hover:underline">
                    {serverName(item.server_id)} <ExternalLink size={10} />
                  </Link>
                </>
              )}
              {dur && (<><span>·</span><span className="tabular-nums">{dur}</span></>)}
              {item.risk_level && item.risk_level !== "low" && (<><span>·</span><span className="capitalize">{item.risk_level} risk</span></>)}
              <span>·</span>
              <span>{timeAgo(item.created_at)}</span>
            </div>
          </div>
        </div>
        <StatusBadge status={item.status} />
      </div>
      <div className="mt-4 space-y-4">{children}</div>
    </div>
  )
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{children}</p>
}

function CommandDetail({ item, serverName }: { item: ActivityItem; serverName: (id: string | null) => string }) {
  const { data: c, isLoading, isError } = useQuery({ queryKey: ["command", item.id], queryFn: () => getCommand(item.id) })
  if (isLoading) return <DetailShell item={item} serverName={serverName} title={item.title}><p className="text-sm text-muted-foreground">Loading…</p></DetailShell>
  if (isError || !c) return <DetailShell item={item} serverName={serverName} title={item.title}><p className="text-sm text-muted-foreground">Couldn't load this command.</p></DetailShell>
  const cmds = (c.commands ?? []).map((x) => x?.cmd).filter(Boolean) as string[]
  return (
    <DetailShell item={item} serverName={serverName} title={c.user_input || item.title}>
      {c.ai_explanation && (
        <div>
          <SectionLabel>Ally's explanation</SectionLabel>
          <p className="text-[13px] leading-relaxed text-foreground">{c.ai_explanation}</p>
        </div>
      )}
      {cmds.length > 0 && (
        <div>
          <SectionLabel>Commands</SectionLabel>
          <div className="space-y-1">
            {cmds.map((cmd, i) => (
              <pre key={i} className="overflow-x-auto rounded bg-[#0d0d0d] px-2.5 py-1.5 font-mono text-[11.5px] text-zinc-300">$ {redactSecrets(cmd).text}</pre>
            ))}
          </div>
        </div>
      )}
      {c.output && (
        <div>
          <SectionLabel>Output</SectionLabel>
          <OutputBlock text={c.output} />
        </div>
      )}
      {!c.ai_explanation && !cmds.length && !c.output && (
        <p className="text-sm text-muted-foreground">No output recorded for this command.</p>
      )}
    </DetailShell>
  )
}

function PlaybookDetail({ item, serverName }: { item: ActivityItem; serverName: (id: string | null) => string }) {
  const { data: r, isLoading, isError } = useQuery({ queryKey: ["run", item.id], queryFn: () => getPlaybookRun(item.id) })
  if (isLoading) return <DetailShell item={item} serverName={serverName} title={item.title}><p className="text-sm text-muted-foreground">Loading…</p></DetailShell>
  if (isError || !r) return <DetailShell item={item} serverName={serverName} title={item.title}><p className="text-sm text-muted-foreground">Couldn't load this run.</p></DetailShell>
  const vars = Object.entries(r.variables_used ?? {})
  return (
    <DetailShell item={item} serverName={serverName} title={item.title}>
      {item.failure_reason && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
          <p className="text-[13px] text-red-600 dark:text-red-400">{item.failure_reason}</p>
          {failureRemedy(item.failure_reason) && (
            <p className="mt-1 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">What to do:</span> {failureRemedy(item.failure_reason)}
            </p>
          )}
        </div>
      )}
      {vars.length > 0 && (
        <div>
          <SectionLabel>Variables</SectionLabel>
          <div className="flex flex-wrap gap-1.5">
            {vars.map(([k, v]) => (
              <span key={k} className="rounded-md border border-border bg-card px-2 py-0.5 text-[11.5px] text-muted-foreground">
                {k}=<span className="text-foreground">{redactSecrets(String(v)).text}</span>
              </span>
            ))}
          </div>
        </div>
      )}
      {r.output ? (
        <div>
          <SectionLabel>Output</SectionLabel>
          <OutputBlock text={r.output} />
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">No output recorded for this run.</p>
      )}
    </DetailShell>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function Logs() {
  const [kind, setKind] = useState<KindFilter>("all")
  const [q, setQ] = useState("")
  const [selectedKey, setSelectedKey] = useState<string | null>(null)

  const { data: activity = [], isLoading } = useQuery<ActivityItem[]>({ queryKey: ["activity"], queryFn: () => listActivity(100) })
  const { data: servers = [] } = useQuery<Server[]>({ queryKey: ["servers"], queryFn: listServers })

  const serverName = useMemo(() => {
    const map = new Map(servers.map((s) => [s.id, s.name]))
    return (id: string | null) => (id ? map.get(id) ?? "Unknown server" : "—")
  }, [servers])

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return activity.filter((a) => {
      if (kind !== "all" && a.kind !== kind) return false
      if (!needle) return true
      return a.title.toLowerCase().includes(needle) || serverName(a.server_id).toLowerCase().includes(needle)
    })
  }, [activity, kind, q, serverName])

  // Default to the first entry so the detail pane is never empty.
  const selected = filtered.find((a) => keyOf(a) === selectedKey) ?? filtered[0]

  const tabs: { key: KindFilter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "playbook", label: "Playbooks" },
    { key: "command", label: "AI Commands" },
  ]

  return (
    <div>
      <header className="mb-4">
        <h1 className="flex items-center gap-2 text-h1 text-foreground">
          <ScrollText className="h-5 w-5 text-primary" /> Activity Log
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">Playbook runs and AI commands across your servers.</p>
      </header>

      {/* Controls — tabs + search, full width so the list and detail align at the top.
          Hidden on mobile when an entry's detail is open. */}
      <div className={cn("mb-4 flex flex-wrap items-center justify-between gap-3", selectedKey && "hidden lg:flex")}>
        <div className="flex gap-0.5 rounded-lg border border-border bg-card p-0.5">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setKind(t.key)}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                kind === t.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search activity…"
            className="w-64 rounded-lg border border-border bg-background py-1.5 pl-8 pr-3 text-sm outline-none focus:border-primary"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3 lg:items-start">
        {/* LEFT — the activity list. Hidden on mobile when an entry's detail is open. */}
        <aside className={cn("min-w-0 lg:col-span-1", selectedKey && "hidden lg:block")}>
          {isLoading ? (
            <div className="space-y-1.5">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-14 animate-pulse rounded-lg border border-border bg-card" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center">
              <ScrollText size={28} className="mx-auto mb-2 text-muted-foreground/50" />
              <p className="text-sm font-medium text-foreground">{activity.length === 0 ? "No activity yet" : "No matches"}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {activity.length === 0 ? "Run a playbook or chat with a server to see it here." : "Try a different filter or search."}
              </p>
            </div>
          ) : (
            <div className="max-h-[calc(100vh-15rem)] space-y-1.5 overflow-y-auto pr-1">
              {filtered.map((a) => {
                const Icon = a.kind === "command" ? Terminal : PlayCircle
                const isSel = selected && keyOf(selected) === keyOf(a)
                return (
                  <button
                    key={keyOf(a)}
                    onClick={() => setSelectedKey(keyOf(a))}
                    className={cn(
                      "block w-full rounded-lg border bg-card p-2.5 text-left transition-colors",
                      isSel ? "border-primary ring-1 ring-primary/40" : "border-border hover:border-primary/40 hover:bg-accent/40",
                    )}
                  >
                    <div className="flex items-center gap-2">
                      <Icon size={13} className="shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-foreground">{a.title}</span>
                    </div>
                    <div className="mt-1 flex items-center justify-between gap-2 pl-5">
                      <span className="truncate text-[11px] text-muted-foreground">
                        {serverName(a.server_id)} · {timeAgo(a.created_at)}
                      </span>
                      <StatusBadge status={a.status} />
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </aside>

        {/* RIGHT — the selected entry's detail (first entry by default on desktop).
            Hidden on mobile until an entry is tapped. */}
        <section className={cn("min-w-0 rounded-2xl border border-border bg-card/40 p-4 sm:p-5 lg:col-span-2", !selectedKey && "hidden lg:block")}>
          {/* Mobile-only back link to the list */}
          <button
            onClick={() => setSelectedKey(null)}
            className="mb-3 -ml-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground lg:hidden"
          >
            <ArrowLeft size={13} /> All activity
          </button>
          {selected ? (
            selected.kind === "command" ? (
              <CommandDetail item={selected} serverName={serverName} />
            ) : (
              <PlaybookDetail item={selected} serverName={serverName} />
            )
          ) : (
            <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
              Select an activity entry to see its detail.
            </div>
          )}
        </section>
      </div>
    </div>
  )
}

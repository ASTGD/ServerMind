import { useMemo, useState, useRef, useEffect } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { differenceInCalendarDays, formatDistanceToNow } from "date-fns"
import { X, Search, MessageSquare, Pencil, Trash2, Check } from "lucide-react"
import { renameThread, type ThreadSummary } from "@/api/assistant"
import { cn } from "@/lib/utils"

const GROUP_ORDER = ["Today", "Yesterday", "This week", "Older"] as const
type Group = (typeof GROUP_ORDER)[number]

function groupOf(iso: string): Group {
  const days = differenceInCalendarDays(new Date(), new Date(iso))
  if (days <= 0) return "Today"
  if (days === 1) return "Yesterday"
  if (days < 7) return "This week"
  return "Older"
}

function ThreadRow({
  thread,
  active,
  onOpen,
  onDelete,
}: {
  thread: ThreadSummary
  active: boolean
  onOpen: () => void
  onDelete: () => void
}) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
  }, [editing])

  async function commitRename() {
    const next = inputRef.current?.value.trim()
    setEditing(false)
    if (!next || next === thread.title) return
    try {
      await renameThread(thread.id, next)
      qc.invalidateQueries({ queryKey: ["assistant-threads"] })
    } catch {
      // Best-effort — the list simply keeps the old title on failure.
    }
  }

  const when = formatDistanceToNow(new Date(thread.updated_at), { addSuffix: true })

  return (
    <div
      onClick={() => !editing && !confirming && onOpen()}
      onMouseLeave={() => setConfirming(false)}
      className={cn(
        "group cursor-pointer rounded-lg px-2.5 py-2 transition-colors",
        active
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
      )}
    >
      <div className="flex items-center gap-2">
        <MessageSquare size={14} className="shrink-0" />
        {editing ? (
          <input
            ref={inputRef}
            defaultValue={thread.title}
            onClick={(e) => e.stopPropagation()}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitRename()
              else if (e.key === "Escape") setEditing(false)
            }}
            className="min-w-0 flex-1 rounded border border-primary/40 bg-background px-1.5 py-0.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-primary/40"
          />
        ) : (
          <span
            className={cn("min-w-0 flex-1 truncate text-sm", active && "font-medium")}
            onDoubleClick={(e) => { e.stopPropagation(); setEditing(true) }}
            title={thread.title}
          >
            {thread.title}
          </span>
        )}

        {/* Row actions — rename + a two-step delete so one stray click can't lose a thread. */}
        {!editing && (
          <span className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
            {confirming ? (
              <>
                <button
                  onClick={(e) => { e.stopPropagation(); onDelete() }}
                  aria-label="Confirm delete"
                  title="Delete this conversation"
                  className="rounded p-1 text-destructive transition-colors hover:bg-destructive/10"
                >
                  <Check size={13} />
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); setConfirming(false) }}
                  aria-label="Cancel delete"
                  className="rounded p-1 text-muted-foreground transition-colors hover:bg-accent"
                >
                  <X size={13} />
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={(e) => { e.stopPropagation(); setEditing(true) }}
                  aria-label="Rename conversation"
                  title="Rename"
                  className="rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                >
                  <Pencil size={12} />
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); setConfirming(true) }}
                  aria-label="Delete conversation"
                  title="Delete"
                  className="rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-destructive"
                >
                  <Trash2 size={12} />
                </button>
              </>
            )}
          </span>
        )}
      </div>
      <p className={cn("mt-0.5 truncate pl-[22px] text-[11px]", confirming ? "font-medium text-destructive" : "text-muted-foreground/70")}>
        {confirming
          ? "Delete this conversation?"
          : `${when} · ${thread.message_count} message${thread.message_count === 1 ? "" : "s"}`}
      </p>
    </div>
  )
}

/**
 * The Ally window's conversation history rail: searchable, grouped by recency
 * (Today / Yesterday / This week / Older), with inline rename (pencil or
 * double-click) and a two-step delete. Titles auto-set from the first message;
 * rename lets the user fix them.
 */
export default function ThreadHistory({
  threads,
  activeId,
  onOpen,
  onDelete,
  onClose,
}: {
  threads: ThreadSummary[]
  activeId: string | null
  onOpen: (id: string) => void
  onDelete: (id: string) => void
  onClose: () => void
}) {
  const [q, setQ] = useState("")

  const groups = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const filtered = needle ? threads.filter((t) => t.title.toLowerCase().includes(needle)) : threads
    const sorted = [...filtered].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    )
    const byGroup = new Map<Group, ThreadSummary[]>()
    for (const t of sorted) {
      const g = groupOf(t.updated_at)
      byGroup.set(g, [...(byGroup.get(g) ?? []), t])
    }
    return GROUP_ORDER.filter((g) => byGroup.has(g)).map((g) => ({ label: g, items: byGroup.get(g)! }))
  }, [threads, q])

  return (
    <aside className="flex w-72 shrink-0 flex-col border-r border-border">
      <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
        <span className="text-sm font-semibold text-foreground">History</span>
        <button
          onClick={onClose}
          aria-label="Close history"
          className="rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <X size={15} />
        </button>
      </div>

      {/* Search — client-side filter on titles. */}
      <div className="relative border-b border-border px-3 py-2">
        <Search size={13} className="pointer-events-none absolute left-5 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search conversations"
          className="w-full rounded-lg border border-border bg-background py-1.5 pl-7 pr-2 text-sm text-foreground placeholder:text-muted-foreground/60 focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        {threads.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-muted-foreground">No conversations yet</p>
        ) : groups.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-muted-foreground">No conversations match “{q}”</p>
        ) : (
          groups.map((g) => (
            <div key={g.label} className="mb-1.5">
              <p className="px-2.5 pb-1 pt-2 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-muted-foreground/60">
                {g.label}
              </p>
              <div className="space-y-0.5">
                {g.items.map((t) => (
                  <ThreadRow
                    key={t.id}
                    thread={t}
                    active={activeId === t.id}
                    onOpen={() => onOpen(t.id)}
                    onDelete={() => onDelete(t.id)}
                  />
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </aside>
  )
}

import { useEffect, useState, useRef, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { X, Sparkles, ChevronDown, Layers, Server as ServerIcon, Check, Plus, Minus, PanelLeft, MessageSquare, Trash2 } from "lucide-react"
import { listServers } from "@/api/servers"
import { listThreads, getThread, createThread, deleteThread, appendMessage } from "@/api/assistant"
import ChatWindow from "@/components/chat/ChatWindow"
import type { ChatMessageData } from "@/components/chat/ChatMessage"
import { useAssistantStore } from "@/store/assistantStore"
import { useResolvedPageContext } from "@/hooks/usePageContext"

/**
 * Ally — ONE window, everywhere. The whole assistant (Chat on the left, Workspace on the
 * right) lives in a single focus-mode window that opens from the round Ally icon in the
 * sidebar and covers the content area. Navigating to another page MINIMIZES it back to that
 * icon (Layout handles the minimize) — the conversation and any running mission stay alive
 * in the store / on the backend, so restoring it brings everything back exactly as it was.
 * Chat and Workspace are never separate: they're one paired window.
 */
export default function AssistantDrawer() {
  const { open, target, seed, setTarget, close, clearConversation } = useAssistantStore()
  const threadId = useAssistantStore((s) => s.threadId)
  const setMessages = useAssistantStore((s) => s.setMessages)
  const setThreadId = useAssistantStore((s) => s.setThreadId)
  const hasMessages = useAssistantStore((s) => s.messages.length > 0)
  const pageCtx = useResolvedPageContext()
  const qc = useQueryClient()
  const [mounted, setMounted] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)

  // Auto-save the continuous conversation to an assistant thread (best-effort — a save
  // failure never blocks chat). threadId lives in the store, read fresh via getState()
  // so concurrent turns can't race a stale closure into two threads.
  //
  // ALL appends run through ONE serial queue: a thread's messages live in a single JSONB
  // column (read-modify-write per append), so appends that settle on the same event — the
  // answer + command output + a chart artifact all landing together — would otherwise race
  // and clobber each other (lost messages). Chaining guarantees order AND no lost writes,
  // and also means the thread-creating user turn always finishes before any work append.
  const persistQueue = useRef<Promise<unknown>>(Promise.resolve())
  const enqueue = useCallback((fn: () => Promise<void>) => {
    const run = () => fn().catch(() => {}) // best-effort: one failure never breaks the chain
    persistQueue.current = persistQueue.current.then(run, run)
    return persistQueue.current
  }, [])

  const persistUser = useCallback((content: string) => enqueue(async () => {
    let tid = useAssistantStore.getState().threadId
    if (!tid) {
      const t = await createThread()
      tid = t.id
      useAssistantStore.getState().setThreadId(tid)
    }
    await appendMessage(tid, "user", content)
    qc.invalidateQueries({ queryKey: ["assistant-threads"] })
  }), [enqueue, qc])

  const persistAnswer = useCallback((content: string) => enqueue(async () => {
    const tid = useAssistantStore.getState().threadId
    if (!tid || !content) return
    await appendMessage(tid, "assistant", content)
    qc.invalidateQueries({ queryKey: ["assistant-threads"] })
  }), [enqueue, qc])

  // Persist a finished WORKSPACE message (mission / command output / artifact) to the
  // thread so reopening it restores the Workspace, not just the chat. The message rides
  // along as structured `data`; command output is tail-capped so a huge dump can't bloat
  // the thread. The triggering user turn already created the thread (and, via the queue,
  // has finished), so a missing threadId just means "nothing to attach to".
  const persistWork = useCallback((msg: ChatMessageData) => enqueue(async () => {
    const tid = useAssistantStore.getState().threadId
    if (!tid) return
    const data =
      msg.role === "assistant" && msg.kind === "output"
        ? { ...msg, content: msg.content.slice(-16000) }
        : msg
    await appendMessage(tid, "assistant", "", data)
    qc.invalidateQueries({ queryKey: ["assistant-threads"] })
  }), [enqueue, qc])

  // Mount the chat (and its socket) lazily on first open, then keep it alive so a running
  // mission keeps streaming even while the window is minimized.
  useEffect(() => {
    if (open) setMounted(true)
  }, [open])

  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers, enabled: mounted })
  const { data: threads = [] } = useQuery({ queryKey: ["assistant-threads"], queryFn: listThreads, enabled: mounted })

  useEffect(() => {
    if (!pickerOpen) return
    const onClick = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) setPickerOpen(false)
    }
    document.addEventListener("mousedown", onClick)
    return () => document.removeEventListener("mousedown", onClick)
  }, [pickerOpen])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setPickerOpen(false); close() }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, close])

  // Open a saved thread INTO the shared conversation (continuing it appends to that thread).
  async function openThread(id: string) {
    if (id === useAssistantStore.getState().threadId) { setHistoryOpen(false); return }
    const t = await getThread(id)
    const msgs: ChatMessageData[] = t.messages.map((m, i) => {
      // A saved WORKSPACE message (mission / output / artifact) — restore it verbatim so
      // the Workspace comes back, not just the chat. Re-id to a stable history key.
      if (m.data && typeof m.data === "object") {
        return { ...(m.data as ChatMessageData), id: `h${i}` }
      }
      return m.role === "user"
        ? ({ id: `h${i}`, role: "user", content: m.content } as ChatMessageData)
        : ({ id: `h${i}`, role: "assistant", kind: "answer", content: m.content, suggestions: [] } as ChatMessageData)
    })
    setMessages(msgs)
    setThreadId(id)
    setHistoryOpen(false)
  }

  async function removeThread(id: string) {
    await deleteThread(id)
    if (useAssistantStore.getState().threadId === id) clearConversation()
    qc.invalidateQueries({ queryKey: ["assistant-threads"] })
  }

  const label = target.kind === "server" ? target.server.name : "All servers"

  return (
    <>
      {/* Dim the content area behind the floating window; click it to minimize. Sidebar +
          topbar stay clear so navigation still works. */}
      <div
        onClick={close}
        aria-hidden="true"
        className={`fixed left-0 right-0 top-14 bottom-0 z-40 bg-black/20 backdrop-blur-[1px] transition-opacity duration-300 ease-out md:left-60 ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />

      {/* The floating window. Its BOTTOM sits 74px above the viewport bottom so its chat
          input lines up on the SAME line as the sidebar composer; anchored flush-left (next
          to the sidebar) with origin-bottom-left so it grows OUT of the left panel. */}
      <aside
        role="complementary"
        aria-label="Ally"
        aria-hidden={!open}
        className={`fixed left-3 right-3 top-[4.5rem] bottom-[74px] z-50 flex origin-bottom-left flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] md:left-[15.75rem] md:right-5 ${
          open ? "scale-100 opacity-100" : "pointer-events-none scale-90 opacity-0"
        }`}
      >
      <div className="flex items-center gap-2 border-b border-border px-3 py-3">
        <button
          onClick={() => setHistoryOpen((o) => !o)}
          aria-label="Conversation history"
          title="Conversation history"
          className={`rounded-lg p-1.5 transition-colors ${
            historyOpen ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground"
          }`}
        >
          <PanelLeft size={17} />
        </button>

        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 text-white">
          <Sparkles size={17} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-foreground">Ally</p>
          {/* Context switcher — fleet or a specific server. */}
          <div className="relative" ref={pickerRef}>
            <button
              onClick={() => setPickerOpen((o) => !o)}
              className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              {target.kind === "server" ? <ServerIcon size={11} /> : <Layers size={11} />}
              <span className="max-w-[12rem] truncate">{label}</span>
              <ChevronDown size={11} />
            </button>
            {pickerOpen && (
              <div className="absolute left-0 top-6 z-10 max-h-72 w-60 overflow-y-auto rounded-lg border border-border bg-card py-1 shadow-xl">
                <button
                  onClick={() => { setTarget({ kind: "fleet" }); setPickerOpen(false) }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-foreground hover:bg-accent"
                >
                  <Layers size={14} className="text-muted-foreground" />
                  <span className="flex-1">All servers</span>
                  {target.kind === "fleet" && <Check size={14} className="text-primary" />}
                </button>
                {servers.length > 0 && <div className="my-1 border-t border-border" />}
                {servers.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => { setTarget({ kind: "server", server: s }); setPickerOpen(false) }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-foreground hover:bg-accent"
                  >
                    <ServerIcon size={14} className="text-muted-foreground" />
                    <span className="flex-1 truncate">{s.name}</span>
                    {target.kind === "server" && target.server.id === s.id && (
                      <Check size={14} className="text-primary" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {hasMessages && (
          <button
            onClick={clearConversation}
            className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            <Plus size={15} />
            New chat
          </button>
        )}
        <button
          onClick={close}
          aria-label="Minimize"
          title="Minimize (Ally keeps working)"
          className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <Minus size={18} />
        </button>
      </div>

      {/* Body: Chat + Workspace (paired), with the thread History tucked behind a toggle. */}
      <div className="flex min-h-0 flex-1">
        {historyOpen && (
          <aside className="flex w-60 shrink-0 flex-col border-r border-border">
            <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
              <span className="text-sm font-semibold text-foreground">History</span>
              <button
                onClick={() => setHistoryOpen(false)}
                aria-label="Close history"
                className="rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <X size={15} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-2 py-2">
              {threads.length === 0 ? (
                <p className="px-2 py-6 text-center text-xs text-muted-foreground">No conversations yet</p>
              ) : (
                threads.map((tItem) => (
                  <div
                    key={tItem.id}
                    onClick={() => openThread(tItem.id)}
                    className={`group flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                      threadId === tItem.id
                        ? "bg-accent font-medium text-accent-foreground"
                        : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                    }`}
                  >
                    <MessageSquare size={14} className="shrink-0" />
                    <span className="min-w-0 flex-1 truncate">{tItem.title}</span>
                    <button
                      onClick={(e) => { e.stopPropagation(); removeThread(tItem.id) }}
                      aria-label="Delete conversation"
                      className="shrink-0 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))
              )}
            </div>
          </aside>
        )}

        <div className="min-h-0 min-w-0 flex-1">
          {mounted && (
            <ChatWindow
              target={target}
              seed={seed}
              pageContext={pageCtx.context}
              templates={pageCtx.templates}
              pageLabel={pageCtx.label}
              persistent
              workspace
              onPersistUser={persistUser}
              onPersistAnswer={persistAnswer}
              onPersistWork={persistWork}
            />
          )}
        </div>
      </div>
      </aside>
    </>
  )
}

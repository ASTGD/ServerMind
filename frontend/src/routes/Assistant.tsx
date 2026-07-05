import { useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, MessageSquare, Trash2, Sparkles, Layers, Server as ServerIcon } from "lucide-react"
import { listThreads, getThread, createThread, deleteThread, appendMessage } from "@/api/assistant"
import ChatWindow from "@/components/chat/ChatWindow"
import { useAssistantStore } from "@/store/assistantStore"
import type { ChatMessageData } from "@/components/chat/ChatMessage"

/**
 * The Ally page — the SAME one continuous conversation as the drawer, just bigger, with
 * the saved-thread history beside it ("one Ally, two sizes"). It renders the store-backed
 * conversation in `persistent` mode, so opening this page and opening the drawer show the
 * exact same messages, focus, and live work — never a second Ally. Opening a past thread
 * loads it into the shared conversation; "New chat" clears it.
 */
export default function Assistant() {
  const qc = useQueryClient()
  const target = useAssistantStore((s) => s.target)
  const threadId = useAssistantStore((s) => s.threadId)
  const setMessages = useAssistantStore((s) => s.setMessages)
  const setThreadId = useAssistantStore((s) => s.setThreadId)
  const clearConversation = useAssistantStore((s) => s.clearConversation)

  const { data: threads = [] } = useQuery({ queryKey: ["assistant-threads"], queryFn: listThreads })

  // Auto-save the shared conversation to its thread — identical behavior to the drawer
  // (threadId read fresh from the store so concurrent turns can't split into two threads).
  const persistUser = useCallback(async (content: string) => {
    try {
      let tid = useAssistantStore.getState().threadId
      if (!tid) {
        const t = await createThread()
        tid = t.id
        useAssistantStore.getState().setThreadId(tid)
      }
      await appendMessage(tid, "user", content)
      qc.invalidateQueries({ queryKey: ["assistant-threads"] })
    } catch { /* keep chatting */ }
  }, [qc])

  const persistAnswer = useCallback(async (content: string) => {
    try {
      const tid = useAssistantStore.getState().threadId
      if (!tid || !content) return
      await appendMessage(tid, "assistant", content)
      qc.invalidateQueries({ queryKey: ["assistant-threads"] })
    } catch { /* keep chatting */ }
  }, [qc])

  // Open a saved thread INTO the shared conversation (continuing it appends to that thread).
  async function openThread(id: string) {
    if (id === useAssistantStore.getState().threadId) return
    const t = await getThread(id)
    const msgs: ChatMessageData[] = t.messages.map((m, i) =>
      m.role === "user"
        ? ({ id: `h${i}`, role: "user", content: m.content } as ChatMessageData)
        : ({ id: `h${i}`, role: "assistant", kind: "answer", content: m.content, suggestions: [] } as ChatMessageData),
    )
    setMessages(msgs)
    setThreadId(id)
  }

  async function remove(id: string) {
    await deleteThread(id)
    if (useAssistantStore.getState().threadId === id) clearConversation()
    qc.invalidateQueries({ queryKey: ["assistant-threads"] })
  }

  const focusLabel = target.kind === "server" ? target.server.name : "fleet-wide"

  return (
    <div className="flex h-[calc(100vh-6.5rem)] gap-4">
      {/* Threads */}
      <aside className="flex w-64 shrink-0 flex-col overflow-hidden rounded-xl border border-border bg-card">
        <div className="p-2">
          <button
            onClick={clearConversation}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            <Plus size={15} />
            New chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-2">
          {threads.length === 0 ? (
            <p className="px-2 py-6 text-center text-xs text-muted-foreground">No conversations yet</p>
          ) : (
            threads.map((t) => (
              <div
                key={t.id}
                onClick={() => openThread(t.id)}
                className={`group flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                  threadId === t.id
                    ? "bg-accent font-medium text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                }`}
              >
                <MessageSquare size={14} className="shrink-0" />
                <span className="min-w-0 flex-1 truncate">{t.title}</span>
                <button
                  onClick={(e) => { e.stopPropagation(); remove(t.id) }}
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

      {/* Conversation — the shared store conversation (same one the drawer shows) */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-card">
        <div className="flex items-center gap-2.5 border-b border-border px-4 py-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500 text-white">
            <Sparkles size={16} />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-foreground">Ally</p>
            <p className="flex items-center gap-1 text-xs text-muted-foreground">
              {target.kind === "server" ? <ServerIcon size={11} /> : <Layers size={11} />}
              {focusLabel}
            </p>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-hidden">
          <ChatWindow
            target={target}
            persistent
            onPersistUser={persistUser}
            onPersistAnswer={persistAnswer}
          />
        </div>
      </div>
    </div>
  )
}

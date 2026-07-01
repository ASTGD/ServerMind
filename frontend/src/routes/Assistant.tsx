import { useState, useMemo, useRef } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, MessageSquare, Trash2, Loader2, Sparkles } from "lucide-react"
import { listThreads, getThread, createThread, deleteThread, appendMessage } from "@/api/assistant"
import ChatWindow from "@/components/chat/ChatWindow"
import type { ChatMessageData } from "@/components/chat/ChatMessage"

const FLEET = { kind: "fleet" as const }

/** The Assistant workspace — a full-page fleet chat with saved, revisitable threads.
 * The thread list is on the left; the active conversation reuses ChatWindow. */
export default function Assistant() {
  const qc = useQueryClient()
  // `activeId` is the thread we persist to / highlight; `mountKey` keys ChatWindow so it
  // only remounts on New chat or when a *different* thread is opened — not when the first
  // message quietly creates a thread mid-conversation.
  const [activeId, setActiveId] = useState<string | null>(null)
  const [mountKey, setMountKey] = useState("new-0")
  const activeIdRef = useRef<string | null>(null)
  activeIdRef.current = activeId

  const isNew = mountKey.startsWith("new-")

  const { data: threads = [] } = useQuery({ queryKey: ["assistant-threads"], queryFn: listThreads })
  const { data: activeThread, isLoading: threadLoading } = useQuery({
    queryKey: ["assistant-thread", activeId],
    queryFn: () => getThread(activeId!),
    enabled: !!activeId && mountKey === activeId,
  })

  const initialMessages: ChatMessageData[] = useMemo(() => {
    if (isNew || !activeThread) return []
    return activeThread.messages.map((m, i) =>
      m.role === "user"
        ? ({ id: `h${i}`, role: "user", content: m.content } as ChatMessageData)
        : ({ id: `h${i}`, role: "assistant", kind: "answer", content: m.content, suggestions: [] } as ChatMessageData),
    )
  }, [isNew, activeThread])

  function newChat() {
    setActiveId(null)
    setMountKey(`new-${Math.random().toString(36).slice(2)}`)
  }

  function openThread(id: string) {
    setActiveId(id)
    setMountKey(id)
  }

  async function persistUser(content: string) {
    let tid = activeIdRef.current
    if (!tid) {
      const t = await createThread()
      tid = t.id
      activeIdRef.current = tid
      setActiveId(tid) // highlights + enables persistence; mountKey stays, so no remount
    }
    await appendMessage(tid, "user", content)
    qc.invalidateQueries({ queryKey: ["assistant-threads"] })
  }

  async function persistAnswer(content: string) {
    const tid = activeIdRef.current
    if (!tid) return
    await appendMessage(tid, "assistant", content)
    qc.invalidateQueries({ queryKey: ["assistant-threads"] })
  }

  async function remove(id: string) {
    await deleteThread(id)
    if (activeIdRef.current === id) newChat()
    qc.invalidateQueries({ queryKey: ["assistant-threads"] })
  }

  const ready = isNew || !!activeThread

  return (
    <div className="flex h-[calc(100vh-6.5rem)] gap-4">
      {/* Threads */}
      <aside className="flex w-64 shrink-0 flex-col overflow-hidden rounded-xl border border-border bg-card">
        <div className="p-2">
          <button
            onClick={newChat}
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
                  activeId === t.id
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

      {/* Conversation */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-card">
        <div className="flex items-center gap-2.5 border-b border-border px-4 py-3">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500 text-white">
            <Sparkles size={16} />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-foreground">
              {activeThread?.title ?? "New chat"}
            </p>
            <p className="text-xs text-muted-foreground">Ally · fleet-wide</p>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-hidden">
          {!ready && threadLoading ? (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              <Loader2 size={20} className="animate-spin" />
            </div>
          ) : (
            <ChatWindow
              key={mountKey}
              target={FLEET}
              initialMessages={initialMessages}
              onPersistUser={persistUser}
              onPersistAnswer={persistAnswer}
            />
          )}
        </div>
      </div>
    </div>
  )
}

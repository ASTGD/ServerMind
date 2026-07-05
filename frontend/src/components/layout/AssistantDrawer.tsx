import { useEffect, useState, useRef, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate, useLocation } from "react-router-dom"
import { X, Sparkles, ChevronDown, Layers, Server as ServerIcon, Check, SquarePen, Maximize2 } from "lucide-react"
import { listServers } from "@/api/servers"
import { createThread, appendMessage } from "@/api/assistant"
import ChatWindow from "@/components/chat/ChatWindow"
import { useAssistantStore } from "@/store/assistantStore"
import { useResolvedPageContext } from "@/hooks/usePageContext"

/**
 * The global AI assistant — one docked drawer, ONE continuous conversation.
 * Defaults to the whole fleet (advisory); a context switcher scopes it to any server
 * (where it can execute with approval). Messages live in the assistant store, so
 * switching target or navigating never loses the thread — a divider marks each
 * switch. Every turn is auto-saved to a thread you can reopen on the Ally page.
 */
export default function AssistantDrawer() {
  const { open, target, seed, setTarget, close, clearConversation } = useAssistantStore()
  const hasMessages = useAssistantStore((s) => s.messages.length > 0)
  const pageCtx = useResolvedPageContext()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const [mounted, setMounted] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)

  // Auto-save the continuous conversation to an assistant thread (best-effort — a save
  // failure never blocks chat). threadId lives in the store, read fresh via getState()
  // so concurrent turns can't race a stale closure into two threads.
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

  // Mount the chat (and its socket) lazily on first open, then keep it alive.
  useEffect(() => {
    if (open) setMounted(true)
  }, [open])

  const { data: servers = [] } = useQuery({
    queryKey: ["servers"],
    queryFn: listServers,
    enabled: mounted,
  })

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
      if (e.key === "Escape") {
        setPickerOpen(false)
        close()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open, close])

  const label = target.kind === "server" ? target.server.name : "All servers"

  // On the full Ally page the page IS the conversation — don't also mount the drawer's
  // ChatWindow (that would open a second socket on the same shared conversation).
  if (location.pathname === "/assistant") return null

  return (
    <>
      {/* Dimmed backdrop on small screens (drawer overlays full-width there). */}
      <div
        onClick={close}
        aria-hidden="true"
        className={`fixed inset-0 top-14 z-30 bg-black/30 backdrop-blur-[1px] transition-opacity duration-300 md:hidden ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />

      <aside
        role="complementary"
        aria-label="Ally"
        aria-hidden={!open}
        className={`fixed bottom-0 right-0 top-14 z-40 flex w-full flex-col border-l border-border bg-card shadow-2xl transition-transform duration-300 ease-out md:w-[28rem] ${
          open ? "translate-x-0" : "pointer-events-none translate-x-full"
        }`}
      >
        <div className="flex items-center gap-2.5 border-b border-border px-4 py-3">
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
              aria-label="New conversation"
              title="New conversation (this one stays saved on the Ally page)"
              className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              <SquarePen size={16} />
            </button>
          )}
          <button
            onClick={() => { navigate("/assistant"); close() }}
            aria-label="Open in full page"
            title="Open in full page — same conversation, bigger"
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <Maximize2 size={16} />
          </button>
          <button
            onClick={close}
            aria-label="Close assistant"
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X size={18} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-hidden">
          {mounted && (
            <ChatWindow
              target={target}
              seed={seed}
              pageContext={pageCtx.context}
              templates={pageCtx.templates}
              pageLabel={pageCtx.label}
              persistent
              onPersistUser={persistUser}
              onPersistAnswer={persistAnswer}
            />
          )}
        </div>
      </aside>
    </>
  )
}

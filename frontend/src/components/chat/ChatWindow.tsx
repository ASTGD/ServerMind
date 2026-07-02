import { useEffect, useRef, useCallback, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useWebSocket } from "@/hooks/useWebSocket"
import { listServers } from "@/api/servers"
import { useAssistantStore } from "@/store/assistantStore"
import ChatInput from "./ChatInput"
import ChatMessage, { type ChatMessageData, type Handoff, type BatchSpec } from "./ChatMessage"
import BatchRunModal from "./BatchRunModal"
import CommandPlan from "./CommandPlan"
import { useAuthStore } from "@/store/authStore"
import { WifiOff, Square, Sparkles, ArrowRight } from "lucide-react"
import { cancelCommand } from "@/api/commands"
import type { CommandItem, GenerateScriptResult } from "@/types"
import type { AssistantTarget } from "@/store/assistantStore"

interface Props {
  target: AssistantTarget
  /** A one-shot prompt to auto-send once the socket opens (the "Hand to AI" handoff). */
  seed?: { text: string; key: number } | null
  /** Preloaded history (from a saved thread) to seed the conversation on mount. */
  initialMessages?: ChatMessageData[]
  /** Persist a turn (saved-thread mode on the Assistant page). */
  onPersistUser?: (content: string) => void
  onPersistAnswer?: (content: string) => void
  /** "What the user is looking at" — sent to Ally as background context (never as commands). */
  pageContext?: string | null
  /** Clickable starter questions for the current page, shown in the empty state. */
  templates?: string[]
  /** Short label for the current page, e.g. "My Scripts" — shown in the "Ally can see" chip. */
  pageLabel?: string
}

interface PendingPlan {
  planSummary: string
  commands: CommandItem[]
  requiresApproval: boolean
  riskLevel: string
  estimatedSeconds: number
}

let _msgId = 0
function nextId() { return String(++_msgId) }

export default function ChatWindow({ target, seed, initialMessages, onPersistUser, onPersistAnswer, pageContext, templates, pageLabel }: Props) {
  const user = useAuthStore((s) => s.user)
  const language = user?.preferred_language ?? "en"
  const openServer = useAssistantStore((s) => s.openServer)
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers })
  const [messages, setMessages] = useState<ChatMessageData[]>(initialMessages ?? [])
  const [batchModal, setBatchModal] = useState<BatchSpec | null>(null)
  const [pending, setPending] = useState<PendingPlan | null>(null)
  const [, setOutputBuffer] = useState<string>("")
  const [isLoading, setIsLoading] = useState(false)
  // Set when a durable (worker) run starts — enables the Stop button.
  const [runningLogId, setRunningLogId] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const addMsg = useCallback((msg: ChatMessageData) => {
    setMessages((prev) => [...prev, msg])
  }, [])

  const { send, status } = useWebSocket(target.kind === "server" ? `/ws/chat/${target.server.id}` : "/ws/chat", {
    onMessage: useCallback((raw: unknown) => {
      const msg = raw as Record<string, unknown>
      switch (msg.type) {
        case "thinking":
          setIsLoading(true)
          addMsg({ id: nextId(), role: "assistant", kind: "thinking" })
          break

        case "plan": {
          setIsLoading(false)
          // Remove thinking bubble
          setMessages((prev) => prev.filter((m) => !(m.role === "assistant" && m.kind === "thinking")))
          const plan: PendingPlan = {
            planSummary: msg.plan_summary as string,
            commands: msg.commands as CommandItem[],
            requiresApproval: msg.requires_approval as boolean,
            riskLevel: msg.risk_level as string ?? "low",
            estimatedSeconds: msg.estimated_duration_seconds as number ?? 30,
          }
          setPending(plan)
          if (!plan.requiresApproval) {
            // Auto-approved — execution will begin
          }
          break
        }

        case "run_started":
          // Durable worker run — remember its id so we can offer a Stop button.
          setRunningLogId(msg.log_id as string)
          break

        case "command_start":
          // Start accumulating output
          setOutputBuffer("")
          break

        case "output": {
          const chunk = (msg.data as string) ?? ""
          setOutputBuffer((prev) => {
            const next = prev + chunk
            setMessages((prevMsgs) => {
              const existing = prevMsgs.find(
                (m) => m.role === "assistant" && m.kind === "output"
              )
              if (existing) {
                return prevMsgs.map((m) =>
                  m.role === "assistant" && m.kind === "output"
                    ? { ...m, content: next }
                    : m
                )
              }
              return [...prevMsgs, { id: nextId(), role: "assistant", kind: "output", content: next } as ChatMessageData]
            })
            return next
          })
          break
        }

        case "command_done":
          break

        case "execution_complete":
          setIsLoading(false)
          setPending(null)
          setRunningLogId(null)
          setOutputBuffer("")
          setMessages((prev) => prev.filter((m) => !(m.role === "assistant" && m.kind === "output")))
          addMsg({
            id: nextId(),
            role: "assistant",
            kind: "complete",
            explanation: msg.explanation as string ?? "",
            status: msg.status as string ?? "success",
            suggestions: (msg.follow_up_suggestions as string[]) ?? [],
          })
          break

        case "answer": {
          setIsLoading(false)
          setMessages((prev) => prev.filter((m) => !(m.role === "assistant" && m.kind === "thinking")))
          const h = msg.handoff as { server_id: string; server_name: string; prompt: string } | null | undefined
          const b = msg.batch as { prompt: string; targets: { server_id: string; server_name: string }[] } | null | undefined
          const scr = (msg.script as GenerateScriptResult | null | undefined) ?? null
          addMsg({
            id: nextId(),
            role: "assistant",
            kind: "answer",
            content: (msg.content as string) ?? "",
            suggestions: (msg.suggestions as string[]) ?? [],
            handoff: h ? { serverId: h.server_id, serverName: h.server_name, prompt: h.prompt } : null,
            batch: b
              ? { prompt: b.prompt, targets: b.targets.map((t) => ({ serverId: t.server_id, serverName: t.server_name })) }
              : null,
            script: scr,
          })
          onPersistAnswer?.((msg.content as string) ?? "")
          break
        }

        case "blocked":
          setIsLoading(false)
          setMessages((prev) => prev.filter((m) => !(m.role === "assistant" && m.kind === "thinking")))
          setPending(null)
          addMsg({
            id: nextId(),
            role: "assistant",
            kind: "blocked",
            reason: msg.reason as string ?? "Command blocked by safety policy",
          })
          break

        case "clarification":
          setIsLoading(false)
          setMessages((prev) => prev.filter((m) => !(m.role === "assistant" && m.kind === "thinking")))
          addMsg({
            id: nextId(),
            role: "assistant",
            kind: "clarification",
            message: msg.message as string,
          })
          break

        case "cancelled":
          setIsLoading(false)
          setPending(null)
          break

        case "error":
          setIsLoading(false)
          setRunningLogId(null)
          setMessages((prev) => prev.filter((m) => !(m.role === "assistant" && m.kind === "thinking")))
          addMsg({
            id: nextId(),
            role: "assistant",
            kind: "error",
            message: msg.message as string ?? "An error occurred",
          })
          break
      }
    }, [addMsg]),
  })

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  // Conversation memory: the last few visible turns, sent with each message so Ally can
  // follow the thread ("install nginx" → "now add SSL to it"). Text-only turns; the
  // backend re-validates and caps everything.
  function recentHistory(): { role: "user" | "assistant"; content: string }[] {
    const turns: { role: "user" | "assistant"; content: string }[] = []
    for (const m of messages) {
      if (m.role === "user") turns.push({ role: "user", content: m.content })
      else if (m.kind === "answer" && m.content) turns.push({ role: "assistant", content: m.content })
      else if (m.kind === "complete" && m.explanation) turns.push({ role: "assistant", content: m.explanation })
      else if (m.kind === "clarification" && m.message) turns.push({ role: "assistant", content: m.message })
    }
    return turns.slice(-8).map((t) => ({ ...t, content: t.content.slice(0, 1500) }))
  }

  function handleSend(content: string) {
    // Snapshot history BEFORE adding the new message — it holds the previous turns only.
    const history = recentHistory()
    addMsg({ id: nextId(), role: "user", content })
    // Attach the page context (if any) as background — the backend frames it as
    // untrusted info and never as instructions.
    send({
      type: "message",
      content,
      language,
      ...(pageContext ? { page_context: pageContext } : {}),
      ...(history.length ? { history } : {}),
    })
    setPending(null)
    onPersistUser?.(content)
  }

  // Fleet → server handoff: switch the assistant to that server, seeded with the action.
  function handleHandoff(h: Handoff) {
    const s = servers.find((x) => x.id === h.serverId)
    if (s) openServer(s, h.prompt)
  }

  // Fleet → batch: run one action across several servers (opens the batch runner).
  function handleBatch(b: BatchSpec) {
    setBatchModal(b)
  }

  // "Hand to AI" handoff — auto-send the seeded prompt once, after the socket is open.
  const lastSeedKey = useRef(0)
  useEffect(() => {
    if (seed && seed.key !== lastSeedKey.current && status === "open" && seed.text.trim()) {
      lastSeedKey.current = seed.key
      handleSend(seed.text)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seed, status])

  function handleApprove() {
    send({ type: "approve" })
    setPending(null)
  }

  function handleCancel() {
    send({ type: "cancel" })
    setPending(null)
    setIsLoading(false)
  }

  async function handleStopRun() {
    if (!runningLogId) return
    try {
      await cancelCommand(runningLogId)
    } catch {
      /* the stream still resolves when the run ends */
    }
  }

  return (
    <div className="flex h-full flex-col">
      {/* Connection warning */}
      {(status === "closed" || status === "error") && (
        <div className="flex items-center justify-center gap-2 bg-destructive/10 px-4 py-2 text-xs text-destructive">
          <WifiOff size={12} />
          Disconnected — please refresh the page
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
            <div>
              <p className="text-sm font-medium text-foreground">
                {target.kind === "server" ? "Ask Ally to manage this server" : "Ask Ally"}
              </p>
              {pageLabel && pageContext && (
                <span className="mt-1.5 inline-flex items-center gap-1 rounded-full bg-accent px-2.5 py-1 text-xs text-accent-foreground">
                  <Sparkles size={11} className="text-primary" />
                  Ally can see: {pageLabel}
                </span>
              )}
            </div>

            {templates && templates.length > 0 ? (
              <div className="flex w-full max-w-sm flex-col gap-2">
                {templates.map((tpl) => (
                  <button
                    key={tpl}
                    onClick={() => handleSend(tpl)}
                    disabled={status !== "open"}
                    className="group flex items-center justify-between gap-2 rounded-xl border border-border bg-card px-3.5 py-2.5 text-left text-sm text-foreground transition-colors hover:border-primary/40 hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <span>{tpl}</span>
                    <ArrowRight
                      size={14}
                      className="shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100"
                    />
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                {target.kind === "server"
                  ? 'Try: "Install nginx", "Check disk space", "List running processes"'
                  : 'Try: "Which servers need attention?", "Best playbook for a Node app"'}
              </p>
            )}
          </div>
        )}

        {messages.map((msg) => (
          <ChatMessage
            key={msg.id}
            message={msg}
            onSuggestion={handleSend}
            onHandoff={handleHandoff}
            onBatch={handleBatch}
          />
        ))}

        {/* Pending plan */}
        {pending && (
          <CommandPlan
            planSummary={pending.planSummary}
            commands={pending.commands}
            requiresApproval={pending.requiresApproval}
            riskLevel={pending.riskLevel}
            estimatedSeconds={pending.estimatedSeconds}
            onApprove={handleApprove}
            onCancel={handleCancel}
          />
        )}

        <div ref={bottomRef} />
      </div>

      {/* Stop a running execution (durable worker path) */}
      {runningLogId && (
        <div className="flex items-center justify-between gap-2 border-t border-border bg-amber-500/5 px-4 py-2">
          <span className="text-xs text-muted-foreground">Running on the server…</span>
          <button
            onClick={handleStopRun}
            className="flex items-center gap-1.5 rounded-lg bg-red-500/90 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-red-500"
          >
            <Square className="h-3 w-3" />
            Stop
          </button>
        </div>
      )}

      {/* Input */}
      <div className="border-t border-border p-3">
        <ChatInput
          onSend={handleSend}
          disabled={status !== "open"}
          loading={isLoading}
        />
      </div>

      {batchModal && <BatchRunModal batch={batchModal} onClose={() => setBatchModal(null)} />}
    </div>
  )
}

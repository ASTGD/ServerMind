import { useEffect, useRef, useCallback, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useWebSocket } from "@/hooks/useWebSocket"
import { listServers } from "@/api/servers"
import { useAssistantStore } from "@/store/assistantStore"
import ChatInput from "./ChatInput"
import ChatMessage, { type ChatMessageData, type Handoff } from "./ChatMessage"
import CommandPlan from "./CommandPlan"
import { useAuthStore } from "@/store/authStore"
import { WifiOff, Square } from "lucide-react"
import { cancelCommand } from "@/api/commands"
import type { CommandItem } from "@/types"
import type { AssistantTarget } from "@/store/assistantStore"

interface Props {
  target: AssistantTarget
  /** A one-shot prompt to auto-send once the socket opens (the "Hand to AI" handoff). */
  seed?: { text: string; key: number } | null
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

export default function ChatWindow({ target, seed }: Props) {
  const user = useAuthStore((s) => s.user)
  const language = user?.preferred_language ?? "en"
  const openServer = useAssistantStore((s) => s.openServer)
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers })
  const [messages, setMessages] = useState<ChatMessageData[]>([])
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
          addMsg({
            id: nextId(),
            role: "assistant",
            kind: "answer",
            content: (msg.content as string) ?? "",
            suggestions: (msg.suggestions as string[]) ?? [],
            handoff: h ? { serverId: h.server_id, serverName: h.server_name, prompt: h.prompt } : null,
          })
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

  function handleSend(content: string) {
    addMsg({ id: nextId(), role: "user", content })
    send({ type: "message", content, language })
    setPending(null)
  }

  // Fleet → server handoff: switch the assistant to that server, seeded with the action.
  function handleHandoff(h: Handoff) {
    const s = servers.find((x) => x.id === h.serverId)
    if (s) openServer(s, h.prompt)
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
          <div className="flex h-full items-center justify-center text-center text-sm text-muted-foreground">
            {target.kind === "server" ? (
              <div>
                <p className="font-medium text-foreground">Ask AI to manage this server</p>
                <p className="mt-1 text-xs">Try: "Install nginx", "Check disk space", "List running processes"</p>
              </div>
            ) : (
              <div>
                <p className="font-medium text-foreground">Ask about any of your servers</p>
                <p className="mt-1 text-xs">Try: "Which servers need attention?", "Best playbook for a Node app"</p>
              </div>
            )}
          </div>
        )}

        {messages.map((msg) => (
          <ChatMessage
            key={msg.id}
            message={msg}
            onSuggestion={handleSend}
            onHandoff={handleHandoff}
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
    </div>
  )
}

import { useEffect, useRef, useCallback, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { useWebSocket } from "@/hooks/useWebSocket"
import { listServers } from "@/api/servers"
import { useAssistantStore } from "@/store/assistantStore"
import ChatInput from "./ChatInput"
import ChatMessage, { type ChatMessageData, type Handoff, type BatchSpec } from "./ChatMessage"
import ServerTag from "./ServerTag"
import { detectServers } from "./serverMentions"
import type { MissionOffer } from "./MissionCard"
import type { MissionState, MissionStep } from "./MissionProgress"
import BatchRunModal from "./BatchRunModal"
import CommandPlan from "./CommandPlan"
import { useAuthStore } from "@/store/authStore"
import { WifiOff, Square, Sparkles, ArrowRight, X } from "lucide-react"
import { cancelCommand } from "@/api/commands"
import type { CommandItem, GenerateScriptResult, Server } from "@/types"
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
  /** ONE continuous conversation (the drawer): messages live in the global assistant
   *  store instead of component state, so switching target or navigating never loses
   *  the thread. A "Now talking to X" divider marks each target switch. */
  persistent?: boolean
}

interface PendingPlan {
  planSummary: string
  commands: CommandItem[]
  requiresApproval: boolean
  riskLevel: string
  estimatedSeconds: number
  serverName?: string | null
}

let _msgId = 0
function nextId() { return String(++_msgId) }

export default function ChatWindow({ target, seed, initialMessages, onPersistUser, onPersistAnswer, pageContext, templates, pageLabel, persistent }: Props) {
  const user = useAuthStore((s) => s.user)
  const language = user?.preferred_language ?? "en"
  const openServer = useAssistantStore((s) => s.openServer)
  const setTarget = useAssistantStore((s) => s.setTarget)
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers })
  // Persistent mode (the drawer): messages live in the global store and survive target
  // switches + navigation. Otherwise (Assistant page): plain local state per thread.
  const storeMessages = useAssistantStore((s) => s.messages)
  const setStoreMessages = useAssistantStore((s) => s.setMessages)
  const [localMessages, setLocalMessages] = useState<ChatMessageData[]>(initialMessages ?? [])
  const messages = persistent ? storeMessages : localMessages
  const setMessages = persistent ? setStoreMessages : setLocalMessages
  const [batchModal, setBatchModal] = useState<BatchSpec | null>(null)
  const [pending, setPending] = useState<PendingPlan | null>(null)
  const [, setOutputBuffer] = useState<string>("")
  const [isLoading, setIsLoading] = useState(false)
  // Set when a durable (worker) run starts — enables the Stop button.
  const [runningLogId, setRunningLogId] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  // The active mission's message id — mission_* events update that message in place.
  const missionMsgIdRef = useRef<string | null>(null)
  // The last thing the user asked — re-sent when they pick a server from a "which one?"
  // clarification, so the pick answers the question without retyping.
  const pendingIntentRef = useRef<string>("")

  const addMsg = useCallback((msg: ChatMessageData) => {
    setMessages((prev) => [...prev, msg])
  }, [setMessages])

  // Update the live mission message (steps append, statuses flip) without remounting.
  // The target id is captured NOW, not inside the queued updater — handlers null the
  // ref right after queueing a terminal update, and React runs the updater later.
  const updateMission = useCallback((fn: (m: MissionState) => MissionState) => {
    const targetId = missionMsgIdRef.current
    if (!targetId) return
    setMessages((prev) =>
      prev.map((m) =>
        m.id === targetId && m.role === "assistant" && m.kind === "mission"
          ? { ...m, mission: fn(m.mission) }
          : m,
      ),
    )
  }, [setMessages])

  // ONE Ally socket (Stage 2): every ChatWindow connects to /ws/chat and names its
  // target per message (server_id). Switching target never reconnects — a pending
  // plan or a running mission stays alive, bound server-side to its own server.
  const { send, status } = useWebSocket("/ws/chat", {
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
            serverName: (msg.server_name as string | undefined) ?? null,
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
            serverId: (msg.server_id as string | undefined) ?? undefined,
            serverName: (msg.server_name as string | undefined) ?? undefined,
          })
          if (msg.explanation) onPersistAnswer?.(msg.explanation as string)
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
            serverId: (msg.server_id as string | undefined) ?? undefined,
            serverName: (msg.server_name as string | undefined) ?? undefined,
          })
          onPersistAnswer?.((msg.content as string) ?? "")
          break
        }

        // ── Ally Missions (docs/ALLY-MISSIONS.md) ────────────────────────────
        case "mission_offer":
          setIsLoading(false)
          setMessages((prev) => prev.filter((m) => !(m.role === "assistant" && m.kind === "thinking")))
          addMsg({
            id: nextId(),
            role: "assistant",
            kind: "mission_offer",
            offer: {
              goal: (msg.goal as string) ?? "",
              skill: (msg.skill as string | null) ?? null,
              message: (msg.message as string) ?? "",
              serverId: (msg.server_id as string | null | undefined) ?? null,
              serverName: (msg.server_name as string | null | undefined) ?? null,
            },
          })
          break

        case "mission_started": {
          setIsLoading(true)
          const id = nextId()
          missionMsgIdRef.current = id
          addMsg({
            id,
            role: "assistant",
            kind: "mission",
            mission: { goal: (msg.goal as string) ?? "", status: "running", steps: [] },
          })
          break
        }

        case "mission_step": {
          const step: MissionStep = {
            index: msg.index as number,
            cmd: (msg.cmd as string) ?? "",
            description: (msg.description as string) ?? "",
            riskLevel: (msg.risk_level as string) ?? "low",
            needsApproval: Boolean(msg.needs_approval),
            running: true,
            serverName: (msg.server_name as string | undefined) ?? undefined,
            verifying: Boolean(msg.verifying),
            waiting: Boolean(msg.waiting),
          }
          updateMission((m) => ({ ...m, steps: [...m.steps.filter((s) => s.index !== step.index), step] }))
          // Risky step — reuse the normal approval UI (approve/cancel go over the socket).
          if (step.needsApproval) {
            setPending({
              planSummary: step.description || step.cmd,
              commands: [{
                cmd: step.cmd,
                description: step.description,
                risk_level: (step.riskLevel ?? "low") as CommandItem["risk_level"],
                requires_confirmation: true,
              }],
              requiresApproval: true,
              riskLevel: step.riskLevel ?? "low",
              estimatedSeconds: 30,
              serverName: step.serverName ?? null,
            })
          }
          break
        }

        case "mission_step_done":
          setPending(null)
          updateMission((m) => {
            const idx = msg.index as number
            const apply = (s: MissionStep): MissionStep => ({
              ...s,
              running: false,
              cmd: (msg.cmd as string) ?? s.cmd,
              description: (msg.description as string) ?? s.description,
              exitCode: (msg.exit_code as number) ?? 0,
              outputTail: (msg.output_tail as string) ?? "",
              note: (msg.note as string) ?? "",
              serverName: (msg.server_name as string | undefined) ?? s.serverName,
              verifying: msg.verifying !== undefined ? Boolean(msg.verifying) : s.verifying,
              waiting: msg.waiting !== undefined ? Boolean(msg.waiting) : s.waiting,
            })
            // Rejected steps (safety / transfer guards) emit step_done with no prior
            // step event — append a row so the timeline shows what was refused.
            if (!m.steps.some((s) => s.index === idx)) {
              return { ...m, steps: [...m.steps, apply({ index: idx, cmd: "", description: "", running: false })] }
            }
            return { ...m, steps: m.steps.map((s) => (s.index === idx ? apply(s) : s)) }
          })
          break

        case "mission_complete":
          setIsLoading(false)
          setPending(null)
          updateMission((m) => ({
            ...m,
            status: "complete",
            summary: (msg.summary as string) ?? "Mission complete.",
            // Verification gate: verified true = goal proven; false = finished but the
            // goal couldn't be confirmed (shown honestly, not as a green success).
            verified: msg.verified !== undefined ? Boolean(msg.verified) : undefined,
            verification: (msg.verification as string | undefined) ?? (msg.caveat as string | undefined),
            steps: m.steps.map((s) => ({ ...s, running: false })),
          }))
          missionMsgIdRef.current = null
          break

        case "mission_blocked":
          setIsLoading(false)
          setPending(null)
          updateMission((m) => ({
            ...m,
            status: "blocked",
            summary: (msg.reason as string) ?? "I can't continue from here.",
            steps: m.steps.map((s) => ({ ...s, running: false })),
          }))
          missionMsgIdRef.current = null
          break

        case "mission_failed":
          setIsLoading(false)
          setPending(null)
          updateMission((m) => ({
            ...m,
            status: "failed",
            summary: (msg.reason as string) ?? "The mission failed.",
            steps: m.steps.map((s) => ({ ...s, running: false })),
          }))
          missionMsgIdRef.current = null
          break

        case "mission_stopped":
          setIsLoading(false)
          setPending(null)
          updateMission((m) => ({
            ...m,
            status: "stopped",
            steps: m.steps.map((s) => ({ ...s, running: false })),
          }))
          missionMsgIdRef.current = null
          break

        case "quota_exceeded":
          setIsLoading(false)
          setMessages((prev) => prev.filter((m) => !(m.role === "assistant" && m.kind === "thinking")))
          addMsg({
            id: nextId(),
            role: "assistant",
            kind: "quota",
            message: (msg.message as string) ?? "You've used all your Ally actions for this month.",
          })
          break

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
            // "Which server did you mean?" — candidate chips (backend maps names→ids).
            askServers: (msg.ask_servers as { id: string; name: string }[] | undefined) ?? undefined,
            serverId: (msg.server_id as string | undefined) ?? undefined,
            serverName: (msg.server_name as string | undefined) ?? undefined,
          })
          if (msg.message) onPersistAnswer?.(msg.message as string)
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
    }, [addMsg, updateMission, setMessages, onPersistAnswer]),
  })

  // The conversation's current FOCUS — the server "this" / "my server" resolves to, and
  // what the input reflects. One continuous conversation: switching focus no longer
  // "restarts" the thread with a divider — a light indicator by the input shows it, and
  // every message carries its own stable-colored server chip.
  const focusServer = target.kind === "server" ? target.server : null

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

  // Which server a message is about: an explicitly named server wins (and becomes the
  // new focus); no name → the current focus; two+ names → fleet-scoped so Ally sorts it
  // out. Same matcher as the chips, so what's highlighted is exactly what's targeted.
  function resolveTarget(content: string): Server | null {
    const named = detectServers(content, servers)
    if (named.length === 1) return servers.find((s) => s.id === named[0].id) ?? null
    if (named.length === 0) return focusServer
    return null // two+ named → fleet-scoped
  }

  // The actual send, bound to a concrete (maybe null = fleet) server.
  function sendMessage(content: string, server: Server | null) {
    // Snapshot history BEFORE adding the new message — it holds the previous turns only.
    const history = recentHistory()
    pendingIntentRef.current = content
    addMsg({ id: nextId(), role: "user", content, serverId: server?.id, serverName: server?.name })
    // One socket, per-message target: name the server this message is for (none =
    // fleet scope). Attach the page context (if any) as background — the backend
    // frames it as untrusted info and never as instructions.
    send({
      type: "message",
      content,
      language,
      ...(server ? { server_id: server.id } : {}),
      ...(pageContext ? { page_context: pageContext } : {}),
      ...(history.length ? { history } : {}),
    })
    setPending(null)
    onPersistUser?.(content)
    // A message naming a different server moves the conversation's focus to it.
    if (server && !(target.kind === "server" && target.server.id === server.id)) {
      setTarget({ kind: "server", server })
    }
  }

  function handleSend(content: string) {
    sendMessage(content, resolveTarget(content))
  }

  // Ally asked "which server?" and the user clicked one → retry the intent bound to it
  // (pass the server explicitly — React's target state isn't updated yet this tick).
  function handlePickServer(id: string) {
    const s = servers.find((x) => x.id === id)
    if (!s) return
    if (pendingIntentRef.current) sendMessage(pendingIntentRef.current, s)
    else setTarget({ kind: "server", server: s })
  }

  // Fleet → server handoff: switch the assistant to that server, seeded with the action.
  function handleHandoff(h: Handoff) {
    const s = servers.find((x) => x.id === h.serverId)
    if (s) openServer(s, h.prompt)
  }

  // A server-name chip in a bubble was clicked — point Ally at that server.
  function handleServerClick(id: string) {
    const s = servers.find((x) => x.id === id)
    if (s) openServer(s)
  }

  // Fleet → batch: run one action across several servers (opens the batch runner).
  function handleBatch(b: BatchSpec) {
    setBatchModal(b)
  }

  // Start a mission (the one mission-level approval) — the backend loop takes over.
  // The home server rides along: the offer's own target first, else the current one.
  function handleStartMission(offer: MissionOffer) {
    setMessages((prev) =>
      prev.map((m) =>
        m.role === "assistant" && m.kind === "mission_offer" && m.offer === offer
          ? { ...m, offer: { ...m.offer, started: true } }
          : m,
      ),
    )
    const homeId = offer.serverId ?? (target.kind === "server" ? target.server.id : null)
    send({
      type: "mission_start",
      goal: offer.goal,
      skill: offer.skill,
      language,
      ...(homeId ? { server_id: homeId } : {}),
    })
  }

  function handleStopMission() {
    send({ type: "mission_stop" })
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

  // Resume an interrupted mission (Phase 3) — send it once the socket is open; the
  // backend replays the saved transcript and continues the loop.
  const resume = useAssistantStore((s) => s.resume)
  const clearResume = useAssistantStore((s) => s.clearResume)
  const lastResumeKey = useRef(0)
  useEffect(() => {
    if (resume && resume.key !== lastResumeKey.current && status === "open") {
      lastResumeKey.current = resume.key
      send({ type: "mission_resume", mission_id: resume.missionId, language })
      clearResume()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resume, status])

  // Attach to a mission running in the background (Phase 4) — reconnect + watch it
  // live; the backend replays the transcript so far, then streams new steps.
  const attach = useAssistantStore((s) => s.attach)
  const clearAttach = useAssistantStore((s) => s.clearAttach)
  const lastAttachKey = useRef(0)
  useEffect(() => {
    if (attach && attach.key !== lastAttachKey.current && status === "open") {
      lastAttachKey.current = attach.key
      send({ type: "mission_attach", mission_id: attach.missionId, language })
      clearAttach()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attach, status])

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
            onStartMission={handleStartMission}
            onStopMission={handleStopMission}
            servers={servers}
            onServerClick={handleServerClick}
            onPickServer={handlePickServer}
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
            serverName={pending.serverName}
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

      {/* Input — held while Ally is thinking or a mission is running (the mission
          loop owns the socket then; Stop and Approve stay available). */}
      <div className="border-t border-border p-3">
        {/* Light, continuous focus indicator (replaces the "Now talking to X" divider):
            which server "this" means, clearable back to the whole fleet. */}
        {focusServer && (
          <div className="mb-2 flex items-center gap-1.5 px-1">
            <span className="text-[11px] text-muted-foreground">Focused on</span>
            <ServerTag name={focusServer.name} />
            <button
              onClick={() => setTarget({ kind: "fleet" })}
              title="Clear focus — talk to the whole fleet"
              className="rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
            >
              <X size={12} />
            </button>
          </div>
        )}
        <ChatInput
          onSend={handleSend}
          disabled={status !== "open" || isLoading}
          loading={isLoading}
          servers={servers}
          placeholder={focusServer ? `Message Ally about ${focusServer.name}…` : undefined}
        />
      </div>

      {batchModal && <BatchRunModal batch={batchModal} onClose={() => setBatchModal(null)} />}
    </div>
  )
}

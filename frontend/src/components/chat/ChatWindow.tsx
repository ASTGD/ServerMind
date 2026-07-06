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
import { Loader2, Square, Sparkles, ArrowRight, X } from "lucide-react"
import { cancelCommand } from "@/api/commands"
import type { CommandItem, GenerateScriptResult, Server } from "@/types"
import type { AssistantTarget } from "@/store/assistantStore"

interface Props {
  target: AssistantTarget
  /** A one-shot prompt to auto-send once the socket opens (Hand-to-AI, a Recipe). When
   *  `serverId` is set the message is PINNED to that server (a name in the text can't
   *  redirect it — e.g. migrate names the source but runs on the chosen target). */
  seed?: { text: string; key: number; serverId?: string } | null
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
  strong?: boolean
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
  // Accumulates streamed command output across chunks. A ref, NOT state, on purpose: its
  // value only feeds the single "output" message. Writing it must never happen inside a
  // React state updater — updaters run during the render phase, and a store write there
  // updates subscribers like AssistantDrawer mid-render ("setState during render" warning).
  const outputBufferRef = useRef<string>("")
  const [isLoading, setIsLoading] = useState(false)
  // Set when a durable (worker) run starts — enables the Stop button.
  const [runningLogId, setRunningLogId] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  // Pass 2 — several missions can stream at once as workspace cards. Each event
  // carries a mission_id; this map routes it to its card's message. The fallback key
  // covers events from a mission whose row couldn't be persisted (id-less).
  const missionMsgIdsRef = useRef<Map<string, string>>(new Map())
  const lastMissionKeyRef = useRef<string | null>(null)
  // The last thing the user asked — re-sent when they pick a server from a "which one?"
  // clarification, so the pick answers the question without retyping.
  const pendingIntentRef = useRef<string>("")

  const addMsg = useCallback((msg: ChatMessageData) => {
    setMessages((prev) => [...prev, msg])
  }, [setMessages])

  // Update ONE mission card (steps append, statuses flip) without remounting.
  const updateMission = useCallback((key: string | null | undefined, fn: (m: MissionState) => MissionState) => {
    const msgId = key ? missionMsgIdsRef.current.get(key) : undefined
    if (!msgId) return
    setMessages((prev) =>
      prev.map((m) =>
        m.id === msgId && m.role === "assistant" && m.kind === "mission"
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
            strong: Boolean(msg.strong),
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
          outputBufferRef.current = ""
          break

        case "output": {
          const chunk = (msg.data as string) ?? ""
          outputBufferRef.current += chunk
          const next = outputBufferRef.current
          // Direct store write from the socket callback (an event, not render) — mirror the
          // accumulated output into the single "output" message.
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
          break
        }

        case "command_done":
          break

        case "execution_complete":
          setIsLoading(false)
          setPending(null)
          setRunningLogId(null)
          outputBufferRef.current = ""
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
          // Pass 2: each mission is its own workspace card. The chat input stays
          // usable — missions run detached and stream in concurrently.
          const key = (msg.mission_id as string | undefined) ?? `local-${nextId()}`
          lastMissionKeyRef.current = key
          const fresh: MissionState = {
            missionId: key,
            goal: (msg.goal as string) ?? "",
            serverName: (msg.server_name as string | undefined) ?? null,
            status: "running",
            steps: [],
            pendingApproval: null,
          }
          if (missionMsgIdsRef.current.has(key)) {
            // Re-attach replay for a card we already show: reset it; the replayed
            // steps repopulate the timeline (no duplicate cards).
            updateMission(key, () => fresh)
          } else {
            const id = nextId()
            missionMsgIdsRef.current.set(key, id)
            addMsg({ id, role: "assistant", kind: "mission", mission: fresh })
            // A short narration line — the card is the workspace; the chat stays free.
            if (!msg.attached) {
              addMsg({
                id: nextId(), role: "system", kind: "divider",
                label: `Mission ${msg.resumed ? "resumed" : "started"}${fresh.serverName ? ` on ${fresh.serverName}` : ""} — follow it in the card; you can keep chatting`,
              })
            }
          }
          break
        }

        case "mission_step": {
          const key = (msg.mission_id as string | undefined) ?? lastMissionKeyRef.current
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
            strong: Boolean(msg.strong),
          }
          // A risky step pauses INSIDE its own card (several missions may be running —
          // the approval must visibly bind to exactly one of them).
          updateMission(key, (m) => ({
            ...m,
            steps: [...m.steps.filter((s) => s.index !== step.index), step],
            pendingApproval: step.needsApproval
              ? {
                  index: step.index, cmd: step.cmd, description: step.description,
                  riskLevel: step.riskLevel, serverName: step.serverName ?? null,
                }
              : m.pendingApproval,
          }))
          break
        }

        case "mission_step_done": {
          const key = (msg.mission_id as string | undefined) ?? lastMissionKeyRef.current
          updateMission(key, (m) => {
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
            const done = {
              // This step is resolved — a pending approval for it is over.
              pendingApproval: m.pendingApproval?.index === idx ? null : m.pendingApproval,
            }
            // Rejected steps (safety / transfer guards) emit step_done with no prior
            // step event — append a row so the timeline shows what was refused.
            if (!m.steps.some((s) => s.index === idx)) {
              return { ...m, ...done, steps: [...m.steps, apply({ index: idx, cmd: "", description: "", running: false })] }
            }
            return { ...m, ...done, steps: m.steps.map((s) => (s.index === idx ? apply(s) : s)) }
          })
          break
        }

        case "mission_complete":
        case "mission_blocked":
        case "mission_failed":
        case "mission_stopped": {
          const key = (msg.mission_id as string | undefined) ?? lastMissionKeyRef.current
          const status =
            msg.type === "mission_complete" ? "complete"
            : msg.type === "mission_blocked" ? "blocked"
            : msg.type === "mission_failed" ? "failed" : "stopped"
          updateMission(key, (m) => ({
            ...m,
            status,
            summary:
              status === "complete" ? ((msg.summary as string) ?? "Mission complete.")
              : status === "blocked" ? ((msg.reason as string) ?? "I can't continue from here.")
              : status === "failed" ? ((msg.reason as string) ?? "The mission failed.")
              : m.summary,
            // Verification gate: verified true = goal proven; false = finished but the
            // goal couldn't be confirmed (shown honestly, not as a green success).
            verified:
              status === "complete" && msg.verified !== undefined ? Boolean(msg.verified) : m.verified,
            verification:
              status === "complete"
                ? ((msg.verification as string | undefined) ?? (msg.caveat as string | undefined) ?? m.verification)
                : m.verification,
            pendingApproval: null,
            steps: m.steps.map((s) => ({ ...s, running: false })),
          }))
          if (key) {
            missionMsgIdsRef.current.delete(key)
            if (lastMissionKeyRef.current === key) lastMissionKeyRef.current = null
          }
          break
        }

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

  // Auto re-attach a still-running mission after a RECONNECT. A dropped socket (backend
  // restart, network blip, sleep) must not lose the live view of an in-flight mission —
  // the mission itself keeps running detached (Phase 4), so we just re-subscribe to it.
  const messagesRef = useRef(messages)
  messagesRef.current = messages
  const wasOpenRef = useRef(false)
  const everOpenRef = useRef(false)
  useEffect(() => {
    if (status !== "open") {
      wasOpenRef.current = false
      return
    }
    if (!wasOpenRef.current && everOpenRef.current) {
      for (const m of messagesRef.current) {
        if (m.role === "assistant" && m.kind === "mission" && m.mission.status === "running") {
          const mid = m.mission.missionId
          if (mid && !mid.startsWith("local-")) {
            send({ type: "mission_attach", mission_id: mid, language })
            break
          }
        }
      }
    }
    wasOpenRef.current = true
    everOpenRef.current = true
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])

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

  // Mission control is routed by mission_id (several cards can run at once). A
  // "local-" key means the mission row couldn't be persisted — the backend then
  // routes to the sole live mission; the `mission: true` marker keeps an id-less
  // mission approval distinct from a plan approval.
  function missionWire(m: MissionState): Record<string, unknown> {
    return m.missionId && !m.missionId.startsWith("local-")
      ? { mission_id: m.missionId }
      : { mission: true }
  }

  function handleStopMission(mission: MissionState) {
    send({ type: "mission_stop", ...missionWire(mission) })
  }

  function handleApproveMission(mission: MissionState) {
    send({ type: "approve", ...missionWire(mission) })
    // Optimistic: the box closes now; the step's own done event settles the row.
    updateMission(mission.missionId, (m) => ({ ...m, pendingApproval: null }))
  }

  // "Hand to AI" / Recipe seed — auto-send the seeded prompt once, after the socket is
  // open. A PINNED seed (seed.serverId) runs on ITS chosen server, never re-derived from a
  // server name in the text — a migrate recipe names the SOURCE in its sentence but must
  // run on the chosen TARGET. Unpinned seeds keep the normal name-detection behaviour.
  const lastSeedKey = useRef(0)
  useEffect(() => {
    if (seed && seed.key !== lastSeedKey.current && status === "open" && seed.text.trim()) {
      lastSeedKey.current = seed.key
      const pinned = seed.serverId ? servers.find((s) => s.id === seed.serverId) : null
      if (pinned) sendMessage(seed.text, pinned)
      else handleSend(seed.text)
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
      {/* Connection warning — the socket auto-reconnects, so this is a calm, transient
          notice, never a "please refresh the page" dead end. */}
      {status !== "open" && (
        <div className="flex items-center justify-center gap-2 bg-amber-500/10 px-4 py-2 text-xs text-amber-700 dark:text-amber-400">
          <Loader2 size={12} className="animate-spin" />
          Reconnecting…
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
            onApproveMission={handleApproveMission}
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
            strong={pending.strong}
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

      {/* Input — held only while Ally is thinking about a chat turn. Missions run
          detached in their cards (Pass 2): you can keep chatting while they work. */}
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

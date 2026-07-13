import { create } from "zustand"
import type { Server } from "@/types"
import type { PageContext } from "@/lib/pageContext"
import type { ChatMessageData } from "@/components/chat/ChatMessage"

/** What the assistant is currently scoped to: the whole fleet, or one server. */
export type AssistantTarget = { kind: "fleet" } | { kind: "server"; server: Server }

/** Ally's model picker. "auto" = the automatic model ladder decides; the rest pin one
 *  model for the conversation (fastest → smartest). Sent with each chat/mission frame. */
export type ModelChoice = "auto" | "fast" | "smart" | "expert" | "genius"

type MessagesUpdater = ChatMessageData[] | ((prev: ChatMessageData[]) => ChatMessageData[])

interface AssistantState {
  open: boolean
  target: AssistantTarget
  /** A one-shot prompt to auto-send once connected (e.g. terminal "Hand to AI", a Recipe).
   *  `serverId` PINS the message to a chosen server — it wins over any server NAME inside
   *  the text (a migrate recipe names the SOURCE server in its sentence, but must run on
   *  the chosen TARGET), so the auto-target detection can't redirect it. */
  seed: { text: string; key: number; serverId?: string } | null
  /** A one-shot request to resume an interrupted mission once connected (Phase 3). */
  resume: { missionId: string; key: number } | null
  /** A one-shot request to attach to a mission running in the background (Phase 4). */
  attach: { missionId: string; key: number } | null
  /** Entity-specific context published by the current route (e.g. an open script), or null.
   *  Ally reads this + the static route context so it knows what the user is looking at. */
  pageContext: PageContext | null
  /** ONE continuous Ally conversation, app-wide ("one Ally, one thread"): lives here —
   *  not in component state — so switching target or navigating never loses it. */
  messages: ChatMessageData[]
  /** The saved assistant_thread backing this conversation (auto-created on first turn). */
  threadId: string | null
  openFleet: () => void
  openServer: (server: Server, seedText?: string) => void
  /** Open the Ally window and send a message on the CURRENT target (from the sidebar
   *  composer). Unpinned — a server name typed in the text still targets that server. */
  askAlly: (text: string) => void
  /** Open Ally on a server (or fleet) and resume the given interrupted mission. */
  resumeMission: (target: AssistantTarget, missionId: string) => void
  clearResume: () => void
  /** Open Ally and attach to a mission still running in the background (Phase 4). */
  attachMission: (target: AssistantTarget, missionId: string) => void
  clearAttach: () => void
  setTarget: (target: AssistantTarget) => void
  setPageContext: (ctx: PageContext | null) => void
  setMessages: (updater: MessagesUpdater) => void
  setThreadId: (id: string | null) => void
  /** Ally's model picker for this conversation (Auto or a pinned model). */
  modelChoice: ModelChoice
  setModelChoice: (c: ModelChoice) => void
  clearConversation: () => void
  toggle: () => void
  close: () => void
}

/**
 * The global AI assistant. One drawer, context-aware: fleet-wide by default, or
 * scoped to a specific server (where it can execute with approval). Lives in the app
 * shell so it's reachable from every page via the top-bar launcher (and ⌘K).
 */
export const useAssistantStore = create<AssistantState>((set) => ({
  open: false,
  target: { kind: "fleet" },
  seed: null,
  resume: null,
  attach: null,
  pageContext: null,
  messages: [],
  threadId: null,
  modelChoice: "auto",
  setModelChoice: (c) => set({ modelChoice: c }),
  openFleet: () => set({ open: true, target: { kind: "fleet" }, seed: null }),
  askAlly: (text) => set({ open: true, seed: { text, key: Date.now() } }),
  openServer: (server, seedText) =>
    set({
      open: true,
      target: { kind: "server", server },
      // Pin the seed to THIS server so a server name inside the text can't redirect it.
      seed: seedText ? { text: seedText, key: Date.now(), serverId: server.id } : null,
    }),
  resumeMission: (target, missionId) =>
    set({ open: true, target, seed: null, resume: { missionId, key: Date.now() } }),
  clearResume: () => set({ resume: null }),
  attachMission: (target, missionId) =>
    set({ open: true, target, seed: null, attach: { missionId, key: Date.now() } }),
  clearAttach: () => set({ attach: null }),
  setTarget: (target) => set({ target, seed: null }),
  setPageContext: (ctx) => set({ pageContext: ctx }),
  setMessages: (updater) =>
    set((s) => ({ messages: typeof updater === "function" ? updater(s.messages) : updater })),
  setThreadId: (id) => set({ threadId: id }),
  // A new conversation returns to the automatic model ladder (Auto) — the safe, low-cost
  // default. A pinned model (Expert/etc.) applies only to the conversation you chose it
  // in, so an earlier pick never silently drives cost in the next chat.
  clearConversation: () => set({ messages: [], threadId: null, modelChoice: "auto" }),
  toggle: () => set((s) => ({ open: !s.open })),
  close: () => set({ open: false }),
}))

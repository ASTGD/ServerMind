import { create } from "zustand"
import type { Server } from "@/types"
import type { PageContext } from "@/lib/pageContext"
import type { ChatMessageData } from "@/components/chat/ChatMessage"

/** What the assistant is currently scoped to: the whole fleet, or one server. */
export type AssistantTarget = { kind: "fleet" } | { kind: "server"; server: Server }

type MessagesUpdater = ChatMessageData[] | ((prev: ChatMessageData[]) => ChatMessageData[])

interface AssistantState {
  open: boolean
  target: AssistantTarget
  /** A one-shot prompt to auto-send once connected (e.g. terminal "Hand to AI"). */
  seed: { text: string; key: number } | null
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
  setTarget: (target: AssistantTarget) => void
  setPageContext: (ctx: PageContext | null) => void
  setMessages: (updater: MessagesUpdater) => void
  setThreadId: (id: string | null) => void
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
  pageContext: null,
  messages: [],
  threadId: null,
  openFleet: () => set({ open: true, target: { kind: "fleet" }, seed: null }),
  openServer: (server, seedText) =>
    set({
      open: true,
      target: { kind: "server", server },
      seed: seedText ? { text: seedText, key: Date.now() } : null,
    }),
  setTarget: (target) => set({ target, seed: null }),
  setPageContext: (ctx) => set({ pageContext: ctx }),
  setMessages: (updater) =>
    set((s) => ({ messages: typeof updater === "function" ? updater(s.messages) : updater })),
  setThreadId: (id) => set({ threadId: id }),
  clearConversation: () => set({ messages: [], threadId: null }),
  toggle: () => set((s) => ({ open: !s.open })),
  close: () => set({ open: false }),
}))

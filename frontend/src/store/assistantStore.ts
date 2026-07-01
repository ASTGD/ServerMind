import { create } from "zustand"
import type { Server } from "@/types"

/** What the assistant is currently scoped to: the whole fleet, or one server. */
export type AssistantTarget = { kind: "fleet" } | { kind: "server"; server: Server }

interface AssistantState {
  open: boolean
  target: AssistantTarget
  /** A one-shot prompt to auto-send once connected (e.g. terminal "Hand to AI"). */
  seed: { text: string; key: number } | null
  openFleet: () => void
  openServer: (server: Server, seedText?: string) => void
  setTarget: (target: AssistantTarget) => void
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
  openFleet: () => set({ open: true, target: { kind: "fleet" }, seed: null }),
  openServer: (server, seedText) =>
    set({
      open: true,
      target: { kind: "server", server },
      seed: seedText ? { text: seedText, key: Date.now() } : null,
    }),
  setTarget: (target) => set({ target, seed: null }),
  toggle: () => set((s) => ({ open: !s.open })),
  close: () => set({ open: false }),
}))

import { create } from "zustand"
import type { Server } from "@/types"

export type TermStatus = "connecting" | "connected" | "disconnected" | "error"

/** One live SSH session. The xterm instance + WebSocket live in the mounted
 *  <XTerminal>; this record is the manager's view of it (label, status, activity). */
export interface TermSession {
  id: string
  /** Stable server-side session id — lets a reconnect re-attach to the same shell. */
  sid: string
  server: Server
  label: string
  status: TermStatus
  lastActivity: number
}

interface TerminalState {
  sessions: TermSession[]
  activeId: string | null
  openSession: (server: Server) => void
  closeSession: (id: string) => void
  setActive: (id: string) => void
  setStatus: (id: string, status: TermStatus) => void
  touch: (id: string) => void
}

let _counter = 0
const nextId = () => `t${++_counter}`

/**
 * The global terminal session manager. Sessions live at the app-shell level (the
 * terminal workspace is mounted in Layout), so they persist across all navigation —
 * moving between pages never disconnects a shell. Sessions end only on explicit close,
 * logout (the workspace unmounts), or idle timeout.
 */
export const useTerminalStore = create<TerminalState>((set, get) => ({
  sessions: [],
  activeId: null,

  openSession: (server) => {
    const sessions = get().sessions
    const dupes = sessions.filter((s) => s.server.id === server.id).length
    const label = dupes > 0 ? `${server.name} · ${dupes + 1}` : server.name
    const id = nextId()
    const sid = crypto.randomUUID()
    set({
      sessions: [...sessions, { id, sid, server, label, status: "connecting", lastActivity: Date.now() }],
      activeId: id,
    })
  },

  closeSession: (id) => {
    const remaining = get().sessions.filter((s) => s.id !== id)
    const activeId =
      get().activeId === id ? (remaining[remaining.length - 1]?.id ?? null) : get().activeId
    set({ sessions: remaining, activeId })
  },

  setActive: (id) => set({ activeId: id }),
  setStatus: (id, status) =>
    set({ sessions: get().sessions.map((s) => (s.id === id ? { ...s, status } : s)) }),
  touch: (id) =>
    set({ sessions: get().sessions.map((s) => (s.id === id ? { ...s, lastActivity: Date.now() } : s)) }),
}))

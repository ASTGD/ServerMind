import { useEffect, useRef, useState } from "react"
import { useLocation } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import {
  Plus, X, Sparkles, Terminal as TerminalIcon, Server as ServerIcon, Square, LayoutGrid,
} from "lucide-react"
import { listServers } from "@/api/servers"
import { useTerminalStore, type TermStatus } from "@/store/terminalStore"
import { useAssistantStore } from "@/store/assistantStore"
import XTerminal, { type XTerminalHandle } from "./XTerminal"

const IDLE_MS = 30 * 60 * 1000 // close a shell after 30 min of no input/output

const DOT: Record<TermStatus, string> = {
  connected: "#10b981",
  connecting: "#f59e0b",
  disconnected: "#ef4444",
  error: "#ef4444",
}

type Mode = "focus" | "split"

/**
 * The terminal workspace — a full-canvas, tabbed, multi-session terminal (the Termius
 * model). Mounted once in the app shell so sessions stay connected across all navigation;
 * fills the content area on /terminal, hidden-but-mounted elsewhere.
 *
 * Focus mode shows one session (tabs to switch). Split mode tiles every session into a
 * grid — all live at once. Terminals never move in the tree (only CSS changes between
 * modes), so switching layouts never remounts them or drops a session.
 */
export default function TerminalWorkspace() {
  const { sessions, activeId, setActive, closeSession, openSession, setStatus, touch } = useTerminalStore()
  const openAlly = useAssistantStore((s) => s.openServer)
  const location = useLocation()
  const visible = location.pathname === "/terminal"

  const [mode, setMode] = useState<Mode>("focus")
  const [pickerOpen, setPickerOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)
  const refs = useRef<Map<string, XTerminalHandle>>(new Map())

  const split = mode === "split" && sessions.length > 1

  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers, enabled: visible })

  // Re-fit terminals when the workspace is shown, the mode changes, or tabs change.
  useEffect(() => {
    if (!visible) return
    const t = setTimeout(() => {
      if (split) sessions.forEach((s) => refs.current.get(s.id)?.fit())
      else if (activeId) refs.current.get(activeId)?.fit()
    }, 60)
    return () => clearTimeout(t)
  }, [visible, split, activeId, sessions.length])

  // Idle timeout — close shells with no activity for IDLE_MS.
  useEffect(() => {
    const iv = setInterval(() => {
      const now = Date.now()
      for (const s of useTerminalStore.getState().sessions) {
        if (now - s.lastActivity > IDLE_MS) useTerminalStore.getState().closeSession(s.id)
      }
    }, 60_000)
    return () => clearInterval(iv)
  }, [])

  useEffect(() => {
    if (!pickerOpen) return
    const onClick = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) setPickerOpen(false)
    }
    document.addEventListener("mousedown", onClick)
    return () => document.removeEventListener("mousedown", onClick)
  }, [pickerOpen])

  function handToAlly() {
    const s = sessions.find((x) => x.id === activeId)
    if (!s) return
    const out = (refs.current.get(s.id)?.getRecentOutput(40) ?? "").trim()
    const text = out
      ? `I'm in the terminal on ${s.server.name} and hit a problem. Here's the recent output — take a look and fix it:\n\n\`\`\`\n${out}\n\`\`\``
      : `I'm working in the terminal on ${s.server.name} and could use a hand.`
    openAlly(s.server, text)
  }

  const cols = sessions.length <= 1 ? 1 : sessions.length <= 4 ? 2 : 3
  const rows = Math.ceil(sessions.length / cols)
  const gridStyle = split
    ? { gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))`, gridTemplateRows: `repeat(${rows}, minmax(0,1fr))` }
    : undefined

  return (
    <div className={`fixed bottom-0 left-0 right-0 top-14 z-20 flex flex-col bg-[#0d0d0d] md:left-60 ${visible ? "" : "hidden"}`}>
      {/* Tab bar */}
      <div className="flex shrink-0 items-center gap-1 border-b border-black bg-[#1a1a1a] px-3 py-2">
        {/* Session tabs — only in focus mode (in split, the pane headers identify each). */}
        {!split && sessions.map((s) => (
          <div
            key={s.id}
            onClick={() => setActive(s.id)}
            className={`group flex cursor-pointer items-center gap-2 rounded-t-md px-3 py-2 text-sm ${
              s.id === activeId ? "bg-[#0d0d0d] text-white" : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: DOT[s.status] }} />
            <span className="whitespace-nowrap">{s.label}</span>
            <button
              onClick={(e) => { e.stopPropagation(); closeSession(s.id) }}
              aria-label="Close session"
              className="text-zinc-600 opacity-0 transition-opacity hover:text-zinc-200 group-hover:opacity-100"
            >
              <X size={14} />
            </button>
          </div>
        ))}

        <div className="relative" ref={pickerRef}>
          <button
            onClick={() => setPickerOpen((o) => !o)}
            aria-label="New session"
            className="flex h-8 w-8 items-center justify-center rounded-md text-zinc-400 hover:bg-white/5 hover:text-white"
          >
            <Plus size={16} />
          </button>
          {pickerOpen && (
            <div className="absolute left-0 top-10 z-10 max-h-80 w-60 overflow-y-auto rounded-lg border border-zinc-700 bg-[#1a1a1a] py-1 shadow-xl">
              {servers.length === 0 ? (
                <p className="px-3 py-2 text-xs text-zinc-500">No servers yet</p>
              ) : (
                servers.map((srv) => (
                  <button
                    key={srv.id}
                    onClick={() => { openSession(srv); setPickerOpen(false) }}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-zinc-300 hover:bg-white/5"
                  >
                    <ServerIcon size={14} className="text-zinc-500" />
                    <span className="truncate">{srv.name}</span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        <span className="flex-1" />

        {sessions.length >= 2 && (
          <div className="mr-1 flex items-center rounded-lg border border-zinc-700 p-0.5 text-xs font-medium">
            <button
              onClick={() => setMode("focus")}
              title="Show one terminal at a time"
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 transition-colors ${
                mode === "focus" ? "bg-indigo-500 text-white" : "text-zinc-400 hover:text-white"
              }`}
            >
              <Square size={13} />
              Single
            </button>
            <button
              onClick={() => setMode("split")}
              title="Show all terminals side by side"
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 transition-colors ${
                mode === "split" ? "bg-indigo-500 text-white" : "text-zinc-400 hover:text-white"
              }`}
            >
              <LayoutGrid size={13} />
              Split
            </button>
          </div>
        )}

        <button
          onClick={handToAlly}
          title="Hand to Ally"
          className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs text-zinc-400 hover:bg-white/5 hover:text-white"
        >
          <Sparkles size={14} />
          Hand to Ally
        </button>
      </div>

      {/* Bodies — every session's terminal stays mounted in the same position; CSS alone
          switches between the single-pane (focus) and grid (split) layouts. */}
      <div
        className={split ? "grid min-h-0 flex-1 gap-1.5 p-1.5" : "relative min-h-0 flex-1"}
        style={gridStyle}
      >
        {sessions.map((s) => (
          <div
            key={s.id}
            onClick={() => setActive(s.id)}
            className={
              split
                ? `flex min-h-0 flex-col overflow-hidden rounded-md border ${
                    s.id === activeId ? "border-indigo-500/60" : "border-zinc-800"
                  }`
                : `absolute inset-0 flex flex-col ${s.id === activeId ? "" : "hidden"}`
            }
          >
            <div className={split ? "flex shrink-0 items-center gap-2 border-b border-zinc-800 bg-[#161616] px-3 py-1.5 text-xs text-zinc-300" : "hidden"}>
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: DOT[s.status] }} />
              {s.label}
              <span className="flex-1" />
              <button
                onClick={(e) => { e.stopPropagation(); closeSession(s.id) }}
                aria-label="Close session"
                className="text-zinc-500 hover:text-zinc-100"
              >
                <X size={13} />
              </button>
            </div>
            <div className="min-h-0 flex-1 p-1">
              <XTerminal
                ref={(h) => { if (h) refs.current.set(s.id, h); else refs.current.delete(s.id) }}
                serverId={s.server.id}
                sid={s.sid}
                onStatusChange={(st) => setStatus(s.id, st)}
                onActivity={() => touch(s.id)}
              />
            </div>
          </div>
        ))}
        {sessions.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-500">
            <TerminalIcon size={30} className="opacity-40" />
            <p className="text-sm">No terminal sessions</p>
            <button
              onClick={() => setPickerOpen(true)}
              className="rounded-md border border-zinc-700 px-4 py-2 text-sm text-zinc-300 hover:bg-white/5"
            >
              Pick a server to start a session
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

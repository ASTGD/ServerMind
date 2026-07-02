import { useEffect, useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  Plus, X, ChevronDown, Sparkles, Maximize2, Minimize2, Terminal as TerminalIcon, Server as ServerIcon,
} from "lucide-react"
import { listServers } from "@/api/servers"
import { useTerminalStore, type TermStatus } from "@/store/terminalStore"
import { useAssistantStore } from "@/store/assistantStore"
import XTerminal, { type XTerminalHandle } from "./XTerminal"

const IDLE_MS = 30 * 60 * 1000 // close a shell after 30 min of no input/output
const MIN_H = 160
const DEFAULT_H = 320

const DOT: Record<TermStatus, string> = {
  connected: "#10b981",
  connecting: "#f59e0b",
  disconnected: "#ef4444",
  error: "#ef4444",
}

/**
 * The global terminal dock — a persistent, multi-session, tabbed terminal docked at
 * the bottom of the app shell. Sessions stay connected across all navigation (the dock
 * is mounted once in Layout); collapsing the dock hides it without ending sessions.
 */
export default function TerminalDock() {
  const { sessions, activeId, open, setActive, closeSession, closeDock, openSession, setStatus, touch } =
    useTerminalStore()
  const openAlly = useAssistantStore((s) => s.openServer)

  const [height, setHeight] = useState(() => Number(localStorage.getItem("term-dock-h")) || DEFAULT_H)
  const [maximized, setMaximized] = useState(false)
  const [pickerOpen, setPickerOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)
  const refs = useRef<Map<string, XTerminalHandle>>(new Map())

  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers, enabled: open })

  // Re-fit the active terminal whenever it becomes visible / the dock resizes.
  useEffect(() => {
    if (!open || !activeId) return
    const t = setTimeout(() => refs.current.get(activeId)?.fit(), 40)
    return () => clearTimeout(t)
  }, [activeId, open, height, maximized])

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

  // Close the server picker on outside click.
  useEffect(() => {
    if (!pickerOpen) return
    const onClick = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) setPickerOpen(false)
    }
    document.addEventListener("mousedown", onClick)
    return () => document.removeEventListener("mousedown", onClick)
  }, [pickerOpen])

  function startResize(e: React.MouseEvent) {
    e.preventDefault()
    const onMove = (ev: MouseEvent) => {
      const h = Math.max(MIN_H, Math.min(window.innerHeight - 120, window.innerHeight - ev.clientY))
      setHeight(h)
    }
    const onUp = () => {
      document.removeEventListener("mousemove", onMove)
      document.removeEventListener("mouseup", onUp)
      localStorage.setItem("term-dock-h", String(Math.round((document.getElementById("term-dock")?.offsetHeight) || DEFAULT_H)))
    }
    document.addEventListener("mousemove", onMove)
    document.addEventListener("mouseup", onUp)
  }

  function handToAlly() {
    const active = sessions.find((s) => s.id === activeId)
    if (!active) return
    const out = (refs.current.get(active.id)?.getRecentOutput(40) ?? "").trim()
    const text = out
      ? `I'm in the terminal on ${active.server.name} and hit a problem. Here's the recent output — take a look and fix it:\n\n\`\`\`\n${out}\n\`\`\``
      : `I'm working in the terminal on ${active.server.name} and could use a hand.`
    openAlly(active.server, text)
  }

  if (sessions.length === 0 && !open) return null

  return (
    <div
      id="term-dock"
      className={`fixed bottom-0 left-0 right-0 z-30 flex flex-col border-t border-zinc-800 bg-[#0d0d0d] shadow-2xl transition-transform duration-200 md:left-60 ${
        open ? "translate-y-0" : "translate-y-full"
      }`}
      style={{ height: maximized ? "calc(100vh - 3.5rem)" : height }}
    >
      {/* Resize grip */}
      <div
        onMouseDown={startResize}
        className="flex h-1.5 shrink-0 cursor-ns-resize items-center justify-center bg-[#111] hover:bg-[#1d1d1d]"
      >
        <span className="h-0.5 w-8 rounded-full bg-zinc-700" />
      </div>

      {/* Tab bar */}
      <div className="flex shrink-0 items-center gap-1 border-b border-black bg-[#1a1a1a] px-2 py-1.5">
        {sessions.map((s) => (
          <div
            key={s.id}
            onClick={() => setActive(s.id)}
            className={`group flex cursor-pointer items-center gap-2 rounded-t-md px-3 py-1.5 text-xs ${
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
              <X size={13} />
            </button>
          </div>
        ))}

        {/* New session */}
        <div className="relative" ref={pickerRef}>
          <button
            onClick={() => setPickerOpen((o) => !o)}
            aria-label="New session"
            className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 hover:bg-white/5 hover:text-white"
          >
            <Plus size={15} />
          </button>
          {pickerOpen && (
            <div className="absolute bottom-9 left-0 z-10 max-h-72 w-56 overflow-y-auto rounded-lg border border-zinc-700 bg-[#1a1a1a] py-1 shadow-xl">
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

        <button onClick={handToAlly} title="Hand to Ally" aria-label="Hand to Ally"
          className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 hover:bg-white/5 hover:text-white">
          <Sparkles size={15} />
        </button>
        <button onClick={() => setMaximized((m) => !m)} title={maximized ? "Restore" : "Maximize"}
          aria-label={maximized ? "Restore" : "Maximize"}
          className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 hover:bg-white/5 hover:text-white">
          {maximized ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
        </button>
        <button onClick={closeDock} title="Collapse (⌘\`)" aria-label="Collapse terminal"
          className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-400 hover:bg-white/5 hover:text-white">
          <ChevronDown size={16} />
        </button>
      </div>

      {/* Bodies — every session stays mounted; only the active one is shown. */}
      <div className="relative min-h-0 flex-1">
        {sessions.map((s) => (
          <div key={s.id} className={`absolute inset-0 p-1 ${s.id === activeId ? "" : "hidden"}`}>
            <XTerminal
              ref={(h) => { if (h) refs.current.set(s.id, h); else refs.current.delete(s.id) }}
              serverId={s.server.id}
              onStatusChange={(st) => setStatus(s.id, st)}
              onActivity={() => touch(s.id)}
            />
          </div>
        ))}
        {sessions.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-zinc-500">
            <TerminalIcon size={26} className="opacity-40" />
            <p className="text-sm">No terminals open</p>
            <button
              onClick={() => setPickerOpen(true)}
              className="rounded-md border border-zinc-700 px-3 py-1.5 text-xs text-zinc-300 hover:bg-white/5"
            >
              Pick a server to start a session
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

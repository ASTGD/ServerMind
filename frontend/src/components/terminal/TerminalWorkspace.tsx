import { useEffect, useRef, useState } from "react"
import { useLocation } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Plus, X, Sparkles, Terminal as TerminalIcon, Server as ServerIcon } from "lucide-react"
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

/**
 * The terminal workspace — a full-canvas, tabbed, multi-session terminal (the Termius
 * model). It's mounted once in the app shell so sessions stay connected across all
 * navigation; it fills the content area on the /terminal route and is hidden (but kept
 * mounted) everywhere else.
 */
export default function TerminalWorkspace() {
  const { sessions, activeId, setActive, closeSession, openSession, setStatus, touch } = useTerminalStore()
  const openAlly = useAssistantStore((s) => s.openServer)
  const location = useLocation()
  const visible = location.pathname === "/terminal"

  const [pickerOpen, setPickerOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)
  const refs = useRef<Map<string, XTerminalHandle>>(new Map())

  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers, enabled: visible })

  // Re-fit the active terminal when the workspace is shown or the active tab changes.
  useEffect(() => {
    if (!visible || !activeId) return
    const t = setTimeout(() => refs.current.get(activeId)?.fit(), 40)
    return () => clearTimeout(t)
  }, [visible, activeId, sessions.length])

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

  return (
    <div className={`fixed bottom-0 left-0 right-0 top-14 z-20 flex flex-col bg-[#0d0d0d] md:left-60 ${visible ? "" : "hidden"}`}>
      {/* Tab bar */}
      <div className="flex shrink-0 items-center gap-1 border-b border-black bg-[#1a1a1a] px-3 py-2">
        {sessions.map((s) => (
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

        <button
          onClick={handToAlly}
          title="Hand to Ally"
          className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs text-zinc-400 hover:bg-white/5 hover:text-white"
        >
          <Sparkles size={14} />
          Hand to Ally
        </button>
      </div>

      {/* Bodies — every session stays mounted; only the active one shows. */}
      <div className="relative min-h-0 flex-1">
        {sessions.map((s) => (
          <div key={s.id} className={`absolute inset-0 p-2 ${s.id === activeId ? "" : "hidden"}`}>
            <XTerminal
              ref={(h) => { if (h) refs.current.set(s.id, h); else refs.current.delete(s.id) }}
              serverId={s.server.id}
              sid={s.sid}
              onStatusChange={(st) => setStatus(s.id, st)}
              onActivity={() => touch(s.id)}
            />
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

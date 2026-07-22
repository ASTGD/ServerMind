import { useEffect, useRef, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  Plus, X, Sparkles, Terminal as TerminalIcon, Server as ServerIcon, Square, LayoutGrid, Minus, Maximize2,
} from "lucide-react"
import { listServers } from "@/api/servers"
import { useTerminalStore, type TermStatus, type TermSession } from "@/store/terminalStore"
import { useAssistantStore } from "@/store/assistantStore"
import XTerminal, { type XTerminalHandle } from "./XTerminal"

const IDLE_MS = 30 * 60 * 1000 // close a shell after 30 min of no input/output

// Smallest usable terminal window when resizing by the corner grip.
const MIN_W = 420
const MIN_H = 240

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
  const {
    sessions, activeId, setActive, closeSession, openSession, setStatus, touch,
    open: visible, maximized, minimize, toggleMax,
  } = useTerminalStore()
  const openAlly = useAssistantStore((s) => s.openServer)

  const [mode, setMode] = useState<Mode>("focus")
  const [pickerOpen, setPickerOpen] = useState(false)
  const pickerRef = useRef<HTMLDivElement>(null)
  const refs = useRef<Map<string, XTerminalHandle>>(new Map())

  // ── Draggable window ────────────────────────────────────────────────────────
  // Grab the title bar to move it, like a real window. Desktop only (on mobile the
  // window is full-width, so there's nowhere to drag it to). While a position is set
  // we position explicitly (left/top) instead of the anchored right-5 default.
  const winRef = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null)
  const [dragging, setDragging] = useState(false)
  const dragOff = useRef<{ dx: number; dy: number } | null>(null)

  function onBarPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    if (maximized || window.innerWidth < 768) return
    // Never start a drag from a control (tab, button, picker) inside the bar.
    if ((e.target as HTMLElement).closest("button, input, select, [data-no-drag]")) return
    const el = winRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    dragOff.current = { dx: e.clientX - r.left, dy: e.clientY - r.top }
    setPos({ x: r.left, y: r.top })
    setDragging(true)
    e.currentTarget.setPointerCapture(e.pointerId)
  }
  function onBarPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const off = dragOff.current
    const el = winRef.current
    if (!dragging || !off || !el) return
    const r = el.getBoundingClientRect()
    // Keep it on screen and below the top bar.
    const maxX = Math.max(0, window.innerWidth - r.width)
    const maxY = Math.max(56, window.innerHeight - r.height)
    setPos({
      x: Math.min(Math.max(0, e.clientX - off.dx), maxX),
      y: Math.min(Math.max(56, e.clientY - off.dy), maxY),
    })
  }
  function onBarPointerUp(e: React.PointerEvent<HTMLDivElement>) {
    if (!dragging) return
    setDragging(false)
    dragOff.current = null
    e.currentTarget.releasePointerCapture?.(e.pointerId)
  }

  // ── Resizable window ────────────────────────────────────────────────────────
  // Drag the bottom-right grip. Clamped to a usable minimum and to the viewport.
  const [size, setSize] = useState<{ w: number; h: number } | null>(null)
  const [resizing, setResizing] = useState(false)
  const resizeFrom = useRef<{ x: number; y: number; w: number; h: number } | null>(null)

  function onGripPointerDown(e: React.PointerEvent<HTMLDivElement>) {
    if (maximized || window.innerWidth < 768) return
    const el = winRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    resizeFrom.current = { x: e.clientX, y: e.clientY, w: r.width, h: r.height }
    setSize({ w: r.width, h: r.height })
    setResizing(true)
    e.currentTarget.setPointerCapture(e.pointerId)
    e.stopPropagation()
  }
  function onGripPointerMove(e: React.PointerEvent<HTMLDivElement>) {
    const from = resizeFrom.current
    const el = winRef.current
    if (!resizing || !from || !el) return
    const r = el.getBoundingClientRect()
    const maxW = Math.max(MIN_W, window.innerWidth - r.left - 8)
    const maxH = Math.max(MIN_H, window.innerHeight - r.top - 8)
    setSize({
      w: Math.min(Math.max(MIN_W, from.w + (e.clientX - from.x)), maxW),
      h: Math.min(Math.max(MIN_H, from.h + (e.clientY - from.y)), maxH),
    })
  }
  function onGripPointerUp(e: React.PointerEvent<HTMLDivElement>) {
    if (!resizing) return
    setResizing(false)
    resizeFrom.current = null
    e.currentTarget.releasePointerCapture?.(e.pointerId)
  }

  // Below md the window is full-width (left-3/right-3), so an explicit left/size would
  // collapse it — drop back to the anchored layout.
  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth < 768) { setPos(null); setSize(null) }
    }
    window.addEventListener("resize", onResize)
    return () => window.removeEventListener("resize", onResize)
  }, [])

  const split = mode === "split" && sessions.length > 1

  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers, enabled: visible })

  // Re-fit terminals when the workspace is shown, the mode changes, tabs change, or the
  // window is resized by the grip (the timeout debounces the drag's rapid updates).
  useEffect(() => {
    if (!visible) return
    const t = setTimeout(() => {
      if (split) sessions.forEach((s) => refs.current.get(s.id)?.fit())
      else if (activeId) refs.current.get(activeId)?.fit()
    }, 60)
    return () => clearTimeout(t)
  }, [visible, split, activeId, sessions.length, maximized, size])

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

  function handToAlly(s: TermSession) {
    const out = (refs.current.get(s.id)?.getRecentOutput(40) ?? "").trim()
    const text = out
      ? `I'm in the terminal on ${s.server.name} and hit a problem. Here's the recent output — take a look and fix it:\n\n\`\`\`\n${out}\n\`\`\``
      : `I'm working in the terminal on ${s.server.name} and could use a hand.`
    openAlly(s.server, text)
  }

  const activeSession = sessions.find((x) => x.id === activeId) ?? null

  const cols = sessions.length <= 1 ? 1 : sessions.length <= 4 ? 2 : 3
  const rows = Math.ceil(sessions.length / cols)
  const gridStyle = split
    ? { gridTemplateColumns: `repeat(${cols}, minmax(0,1fr))`, gridTemplateRows: `repeat(${rows}, minmax(0,1fr))` }
    : undefined

  return (
    <>
      {/* Dim the workspace behind the window; click outside tucks it to the sidebar dock. */}
      <div
        onClick={minimize}
        aria-hidden="true"
        className={`fixed left-0 right-0 top-14 bottom-0 z-30 bg-black/30 backdrop-blur-[1px] transition-opacity duration-200 md:left-60 ${
          visible ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />
      {/* The terminal window — a compact floating window that drops out of the Terminal
          button in the top bar (grows from / flies back to the top-right). Maximize expands
          it to the workspace; Minimize tucks it away while every SSH session keeps running.
          Only HIDDEN when closed, never unmounted. */}
      <div
        ref={winRef}
        style={
          maximized
            ? undefined
            : {
                ...(pos ? { left: pos.x, top: pos.y, right: "auto", bottom: "auto" } : {}),
                ...(size ? { width: size.w, height: size.h, maxWidth: "none", maxHeight: "none" } : {}),
              }
        }
        className={`fixed z-40 flex origin-top-right flex-col overflow-hidden rounded-xl border border-black/50 bg-[#0d0d0d] shadow-2xl ${
          dragging || resizing ? "transition-none" : "transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]"
        } ${
          maximized
            ? "left-3 right-3 top-[4.5rem] bottom-4 md:left-[15.75rem] md:right-5"
            : "left-3 right-3 top-[4.5rem] h-[540px] max-h-[calc(100vh-6rem)] md:left-auto md:right-5 md:w-[860px] md:max-w-[calc(100vw-17rem)]"
        } ${visible ? "translate-x-0 translate-y-0 scale-100 opacity-100" : "pointer-events-none translate-x-3 -translate-y-3 scale-90 opacity-0"}`}
      >
      {/* Tab bar — macOS terminal window chrome (deep-indigo titlebar, distinct from the
          near-black terminal body so it clearly reads as a window bar). Doubles as the
          drag handle: grab it to move the window (desktop, when not maximized). */}
      <div
        onPointerDown={onBarPointerDown}
        onPointerMove={onBarPointerMove}
        onPointerUp={onBarPointerUp}
        onPointerCancel={onBarPointerUp}
        className={`flex shrink-0 select-none items-center gap-1 border-b border-black bg-gradient-to-b from-[#1e1b4b] to-[#15132a] px-3 py-2 ${
          maximized ? "" : "md:cursor-move"
        }`}
      >
        {/* Decorative traffic lights (the Mac window frame). */}
        <div className="mr-3 flex shrink-0 items-center gap-2 pl-0.5" aria-hidden="true">
          <span className="h-3 w-3 rounded-full bg-[#ff5f57]" />
          <span className="h-3 w-3 rounded-full bg-[#febc2e]" />
          <span className="h-3 w-3 rounded-full bg-[#28c840]" />
        </div>
        {/* Session tabs — only in focus mode (in split, the pane headers identify each). */}
        {!split && sessions.map((s) => (
          <div
            key={s.id}
            data-no-drag
            onClick={() => setActive(s.id)}
            className={`group flex cursor-pointer items-center gap-2 rounded-t-md px-3 py-2 text-sm ${
              s.id === activeId ? "bg-[#0d0d0d] text-white" : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: DOT[s.status] }} />
            <span className="whitespace-nowrap">{s.label}</span>
            <button
              onClick={(e) => { e.stopPropagation(); closeSession(s.id) }}
              aria-label="Close terminal"
              title="Close terminal"
              className="rounded p-0.5 text-zinc-500 transition-colors hover:bg-white/10 hover:text-zinc-100"
            >
              <X size={14} />
            </button>
          </div>
        ))}

        <div className="relative" ref={pickerRef}>
          <button
            onClick={() => setPickerOpen((o) => !o)}
            aria-label="New terminal"
            title="New terminal"
            className="flex items-center gap-1.5 rounded-md border border-zinc-700 px-2.5 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:border-zinc-500 hover:bg-white/5 hover:text-white"
          >
            <Plus size={14} />
            New
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

        {/* In split mode each pane carries its own "Hand to Ally" (so it's clear which
            server it sends); the single toolbar button only makes sense in focus mode,
            where there's exactly one visible terminal. */}
        {!split && activeSession && (
          <button
            onClick={() => handToAlly(activeSession)}
            title={`Hand ${activeSession.server.name} to Ally`}
            className="flex items-center gap-1.5 rounded-md bg-brand-gradient-r px-2.5 py-1.5 text-xs font-medium text-white transition-opacity hover:opacity-90"
          >
            <Sparkles size={14} />
            Hand to Ally
          </button>
        )}
        {/* Window controls — maximize/restore + minimize to the sidebar dock. */}
        <div className="ml-1 flex items-center gap-0.5">
          <button
            onClick={toggleMax}
            title={maximized ? "Restore size" : "Maximize"}
            className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-white/10 hover:text-zinc-100"
          >
            <Maximize2 size={14} />
          </button>
          <button
            onClick={minimize}
            title="Minimize to dock"
            className="rounded-md p-1.5 text-zinc-400 transition-colors hover:bg-white/10 hover:text-zinc-100"
          >
            <Minus size={15} />
          </button>
        </div>
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
              <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: DOT[s.status] }} />
              <span className="min-w-0 truncate">{s.label}</span>
              <span className="flex-1" />
              <button
                onClick={(e) => { e.stopPropagation(); handToAlly(s) }}
                title={`Hand ${s.server.name} to Ally`}
                className="flex shrink-0 items-center gap-1 rounded bg-brand-gradient-r px-2 py-1 text-white transition-opacity hover:opacity-90"
              >
                <Sparkles size={12} />
                Hand to Ally
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); closeSession(s.id) }}
                aria-label="Close session"
                className="shrink-0 text-zinc-500 hover:text-zinc-100"
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

      {/* Corner grip — drag to resize (desktop; a maximized window has a fixed size). */}
      {!maximized && (
        <div
          onPointerDown={onGripPointerDown}
          onPointerMove={onGripPointerMove}
          onPointerUp={onGripPointerUp}
          onPointerCancel={onGripPointerUp}
          title="Drag to resize"
          className="group absolute bottom-0 right-0 z-10 hidden h-5 w-5 cursor-se-resize md:block"
        >
          {/* two short diagonal strokes, like a native grip */}
          <span className="pointer-events-none absolute bottom-[5px] right-[3px] h-[7px] w-px rotate-45 bg-zinc-600 transition-colors group-hover:bg-zinc-300" />
          <span className="pointer-events-none absolute bottom-[3px] right-[7px] h-[11px] w-px rotate-45 bg-zinc-600 transition-colors group-hover:bg-zinc-300" />
        </div>
      )}
    </div>
    </>
  )
}

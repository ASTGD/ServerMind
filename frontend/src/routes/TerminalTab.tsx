import { useRef, useState } from "react"
import { useOutletContext } from "react-router-dom"
import { Sparkles } from "lucide-react"
import XTerminal, { type XTerminalHandle } from "@/components/terminal/XTerminal"
import type { Server } from "@/types"

type ConnStatus = "connecting" | "connected" | "disconnected" | "error"

const STATUS_META: Record<ConnStatus, { dot: string; label: string }> = {
  connecting:   { dot: "bg-amber-400 animate-pulse",   label: "Connecting…"  },
  connected:    { dot: "bg-emerald-400 animate-pulse", label: "Connected"    },
  disconnected: { dot: "bg-zinc-500",                  label: "Disconnected" },
  error:        { dot: "bg-red-500",                   label: "Error"        },
}

export default function TerminalTab() {
  const { server, openAI } = useOutletContext<{ server: Server; openAI: (seed?: string) => void }>()
  const xtermRef = useRef<XTerminalHandle>(null)
  const [status, setStatus] = useState<ConnStatus>("connecting")

  function handToAI() {
    const out = (xtermRef.current?.getRecentOutput(40) ?? "").trim()
    const text = out
      ? `I'm working in the terminal on this server and hit a problem. Here's the recent output — take a look and fix it:\n\n\`\`\`\n${out}\n\`\`\``
      : "I'm working in the terminal on this server and could use a hand."
    openAI(text)
  }

  const st = STATUS_META[status]

  return (
    <div className="flex flex-col h-[calc(100vh-14rem)] rounded-xl overflow-hidden border border-zinc-800 shadow-2xl shadow-black/60">

      {/* ── Toolbar ─────────────────────────────────────────────── */}
      <div className="flex shrink-0 items-center gap-3 bg-[#1c1c1c] border-b border-zinc-800/80 px-4 h-10">

        {/* Traffic lights */}
        <div className="flex items-center gap-1.5 shrink-0">
          <div className="w-3 h-3 rounded-full bg-red-500/80" />
          <div className="w-3 h-3 rounded-full bg-yellow-400/80" />
          <div className="w-3 h-3 rounded-full bg-emerald-500/80" />
        </div>

        {/* Server identity */}
        <div className="flex items-center gap-1.5 min-w-0 flex-1 ml-1">
          <span className="text-xs font-medium text-zinc-200 truncate">{server.name}</span>
          <span className="text-zinc-600 text-xs select-none">·</span>
          <span className="text-xs font-mono text-zinc-500 truncate">
            {server.username}@{server.host}
          </span>
        </div>

        {/* Live connection status */}
        <div className="flex items-center gap-1.5 shrink-0">
          <div className={`w-2 h-2 rounded-full ${st.dot}`} />
          <span className="text-xs text-zinc-400">{st.label}</span>
        </div>

        {/* Divider */}
        <div className="h-4 w-px bg-zinc-700/60 shrink-0" />

        {/* Hand to AI */}
        <button
          onClick={handToAI}
          title="Send recent terminal output to the AI companion"
          className="flex items-center gap-1.5 rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-xs font-medium text-zinc-300 transition-colors hover:bg-white/10 hover:text-white shrink-0"
        >
          <Sparkles size={12} />
          Hand to AI
        </button>
      </div>

      {/* ── Terminal body ────────────────────────────────────────── */}
      <div className="flex-1 min-h-0 bg-[#0d0d0d] p-1">
        <XTerminal ref={xtermRef} serverId={server.id} onStatusChange={setStatus} />
      </div>
    </div>
  )
}

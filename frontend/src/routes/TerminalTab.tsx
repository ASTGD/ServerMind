import { useRef } from "react"
import { useOutletContext } from "react-router-dom"
import { Sparkles } from "lucide-react"
import XTerminal, { type XTerminalHandle } from "@/components/terminal/XTerminal"
import type { Server } from "@/types"

/** The Terminal tab — lives inside the server hub shell. "Hand to AI" captures the recent
 * scrollback and opens the shell's docked AI companion seeded with it (via outlet context). */
export default function TerminalTab() {
  const { server, openAI } = useOutletContext<{ server: Server; openAI: (seed?: string) => void }>()
  const xtermRef = useRef<XTerminalHandle>(null)

  function handToAI() {
    const out = (xtermRef.current?.getRecentOutput(40) ?? "").trim()
    const text = out
      ? `I'm working in the terminal on this server and hit a problem. Here's the recent output — take a look and fix it:\n\n\`\`\`\n${out}\n\`\`\``
      : "I'm working in the terminal on this server and could use a hand."
    openAI(text)
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-end">
        <button
          onClick={handToAI}
          title="Send what just happened to the AI"
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          <Sparkles size={14} />
          Hand to AI
        </button>
      </div>
      <div className="h-[calc(100vh-15rem)] overflow-hidden p-1">
        <XTerminal ref={xtermRef} serverId={server.id} />
      </div>
    </div>
  )
}

import { useState, useEffect, useRef } from "react"
import { useParams, Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { ChevronLeft, MessageSquare, Sparkles } from "lucide-react"
import { getServer } from "@/api/servers"
import XTerminal, { type XTerminalHandle } from "@/components/terminal/XTerminal"
import ConnectionStatus from "@/components/server/ConnectionStatus"
import AICompanionDrawer from "@/components/server/AICompanionDrawer"
import type { Server } from "@/types"

export default function Terminal() {
  const { id } = useParams<{ id: string }>()
  const xtermRef = useRef<XTerminalHandle>(null)
  const [aiOpen, setAiOpen] = useState(false)
  const [seed, setSeed] = useState<{ text: string; key: number } | null>(null)

  const { data: server } = useQuery<Server>({
    queryKey: ["server", id],
    queryFn: () => getServer(id!),
    enabled: !!id,
  })

  // Toggle the AI companion with ⌘/Ctrl-J; Escape closes it.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
        e.preventDefault()
        setAiOpen((o) => !o)
      } else if (e.key === "Escape") {
        setAiOpen(false)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  // Capture the recent terminal output and hand it to the AI to take over.
  function handToAI() {
    const out = (xtermRef.current?.getRecentOutput(40) ?? "").trim()
    const text = out
      ? `I'm working in the terminal on this server and hit a problem. Here's the recent output — take a look and fix it:\n\n\`\`\`\n${out}\n\`\`\``
      : "I'm working in the terminal on this server and could use a hand."
    setSeed({ text, key: Date.now() })
    setAiOpen(true)
  }

  return (
    <div
      className={`flex h-[calc(100vh-3.5rem)] flex-col transition-[padding] duration-300 ${
        aiOpen ? "md:pr-[28rem]" : ""
      }`}
    >
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-border px-4 py-3">
        <Link
          to={`/servers/${id}`}
          className="rounded p-1 text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft size={18} />
        </Link>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate font-medium text-foreground">{server?.name ?? "Loading…"}</p>
            {server && <ConnectionStatus status={server.status} />}
          </div>
          {server && (
            <p className="text-xs text-muted-foreground">
              {server.username}@{server.host} · Terminal
            </p>
          )}
        </div>
        <button
          onClick={handToAI}
          title="Send what just happened to the AI"
          className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
        >
          <Sparkles size={14} />
          Hand to AI
        </button>
        <button
          onClick={() => setAiOpen((o) => !o)}
          title="AI companion (⌘J)"
          aria-label="Toggle AI companion"
          className={`flex items-center rounded-md border border-border px-2.5 py-1.5 text-sm transition-colors ${
            aiOpen ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          }`}
        >
          <MessageSquare size={14} />
        </button>
      </div>

      {/* Terminal */}
      <div className="flex-1 overflow-hidden p-2">
        {id && <XTerminal ref={xtermRef} serverId={id} />}
      </div>

      {server && (
        <AICompanionDrawer
          server={server}
          open={aiOpen}
          onClose={() => setAiOpen(false)}
          seed={seed}
        />
      )}
    </div>
  )
}

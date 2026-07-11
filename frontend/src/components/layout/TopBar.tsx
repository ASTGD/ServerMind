import { useNavigate } from "react-router-dom"
import { Sparkles, Terminal as TerminalIcon, ScrollText } from "lucide-react"
import Breadcrumbs from "./Breadcrumbs"
import NotificationBell from "./NotificationBell"
import UserMenu from "./UserMenu"
import { useAssistantStore } from "@/store/assistantStore"
import { useTerminalStore } from "@/store/terminalStore"

export default function TopBar() {
  const navigate = useNavigate()
  const toggleAssistant = useAssistantStore((s) => s.toggle)
  const termCount = useTerminalStore((s) => s.sessions.length)

  return (
    <header className="relative z-20 flex h-14 items-center justify-between gap-4 border-b border-border bg-card px-6 shadow-[0_4px_14px_-3px_rgba(15,23,42,0.12)]">
      <Breadcrumbs />
      <div className="flex shrink-0 items-center gap-1.5">
        {/* Terminal — the launcher lives here now (moved off the left panel). A green dot
            means live shell sessions are running; jump in from any page (⌘`). */}
        <button
          onClick={() => navigate("/terminal")}
          title={termCount > 0 ? `${termCount} terminal ${termCount === 1 ? "session" : "sessions"} running (⌘\`)` : "Terminal (⌘\`)"}
          className={`relative flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
            termCount > 0
              ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 hover:bg-emerald-500/20 dark:text-emerald-400"
              : "border-border text-muted-foreground hover:bg-accent hover:text-foreground"
          }`}
        >
          {termCount > 0 && (
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
          )}
          <TerminalIcon size={14} />
          Terminal
        </button>
        <button
          onClick={toggleAssistant}
          title="Ask Ally (⌘K)"
          className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-indigo-500 to-violet-500 px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
        >
          <Sparkles size={14} />
          Ask Ally
        </button>
        <div className="mx-1 h-6 w-px bg-border" />
        <button
          onClick={() => navigate("/logs")}
          title="Activity Log"
          className="relative flex items-center justify-center rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <ScrollText size={16} />
        </button>
        <NotificationBell />
        <div className="mx-1 h-6 w-px bg-border" />
        <UserMenu />
      </div>
    </header>
  )
}

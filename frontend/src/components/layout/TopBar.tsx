import { useNavigate } from "react-router-dom"
import { Sparkles, Terminal as TerminalIcon } from "lucide-react"
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
        {/* Live terminal sessions — a status pill, shown only when shells are actually
            running. This makes it read as "you have N live terminals" (a status you can
            jump to from any page), not a second copy of the left-menu Terminal item. */}
        {termCount > 0 && (
          <button
            onClick={() => navigate("/terminal")}
            title={`${termCount} terminal ${termCount === 1 ? "session" : "sessions"} running (⌘\`)`}
            className="flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 py-1 pl-2 pr-2.5 text-sm font-medium text-emerald-700 transition-colors hover:bg-emerald-500/20 dark:text-emerald-400"
          >
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            <TerminalIcon size={13} />
            {termCount} running
          </button>
        )}
        <button
          onClick={toggleAssistant}
          title="Ask Ally (⌘K)"
          className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-indigo-500 to-violet-500 px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
        >
          <Sparkles size={14} />
          Ask Ally
        </button>
        <div className="mx-1 h-6 w-px bg-border" />
        <NotificationBell />
        <div className="mx-1 h-6 w-px bg-border" />
        <UserMenu />
      </div>
    </header>
  )
}

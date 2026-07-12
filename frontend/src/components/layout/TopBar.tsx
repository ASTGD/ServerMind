import { useNavigate } from "react-router-dom"
import { Terminal as TerminalIcon, ScrollText } from "lucide-react"
import Breadcrumbs from "./Breadcrumbs"
import NotificationBell from "./NotificationBell"
import UserMenu from "./UserMenu"
import { useTerminalStore } from "@/store/terminalStore"

export default function TopBar() {
  const navigate = useNavigate()
  const termCount = useTerminalStore((s) => s.sessions.length)
  const toggleTerminal = useTerminalStore((s) => s.toggle)

  return (
    <header className="relative z-20 flex h-14 items-center justify-between gap-4 border-b border-border bg-card px-6 shadow-[0_4px_14px_-3px_rgba(15,23,42,0.12)]">
      <Breadcrumbs />
      <div className="flex shrink-0 items-center gap-1.5">
        {/* Terminal — a small launcher icon (Ally now lives only in the sidebar). A green
            dot on the icon means live shell sessions are running; jump in from any page (⌘`). */}
        <button
          onClick={toggleTerminal}
          title={termCount > 0 ? `${termCount} terminal ${termCount === 1 ? "session" : "sessions"} running (⌘\`)` : "Terminal (⌘\`)"}
          className={`relative flex items-center justify-center rounded-md p-2 transition-colors ${
            termCount > 0
              ? "text-emerald-600 hover:bg-emerald-500/10 dark:text-emerald-400"
              : "text-muted-foreground hover:bg-accent hover:text-foreground"
          }`}
        >
          {termCount > 0 && (
            <span className="absolute -right-0.5 -top-0.5 flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
          )}
          <TerminalIcon size={16} />
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

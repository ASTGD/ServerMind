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
        <button
          onClick={() => navigate("/terminal")}
          title="Terminal (⌘`)"
          className="relative flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
        >
          <TerminalIcon size={14} />
          Terminal
          {termCount > 0 && (
            <span className="ml-0.5 rounded-full bg-primary px-1.5 text-[11px] font-semibold text-primary-foreground">
              {termCount}
            </span>
          )}
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
        <NotificationBell />
        <div className="mx-1 h-6 w-px bg-border" />
        <UserMenu />
      </div>
    </header>
  )
}

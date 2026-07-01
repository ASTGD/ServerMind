import { Sparkles } from "lucide-react"
import Breadcrumbs from "./Breadcrumbs"
import NotificationBell from "./NotificationBell"
import UserMenu from "./UserMenu"
import { useAssistantStore } from "@/store/assistantStore"

export default function TopBar() {
  const toggle = useAssistantStore((s) => s.toggle)

  return (
    <header className="relative z-20 flex h-14 items-center justify-between gap-4 border-b border-border bg-card px-6 shadow-[0_4px_14px_-3px_rgba(15,23,42,0.12)]">
      <Breadcrumbs />
      <div className="flex shrink-0 items-center gap-1.5">
        <button
          onClick={toggle}
          title="Ask AI (⌘K)"
          className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-indigo-500 to-violet-500 px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
        >
          <Sparkles size={14} />
          Ask AI
        </button>
        <div className="mx-1 h-6 w-px bg-border" />
        <NotificationBell />
        <div className="mx-1 h-6 w-px bg-border" />
        <UserMenu />
      </div>
    </header>
  )
}

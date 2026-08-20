import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { History, Menu, Activity } from "lucide-react"
import Breadcrumbs from "./Breadcrumbs"
import NotificationBell from "./NotificationBell"
import UserMenu from "./UserMenu"
import { useMcpActivity } from "@/hooks/useMcpActivity"
import RunningPill from "@/components/activity/RunningPill"
import { listMcpConnections } from "@/api/mcp"

export default function TopBar({ onMenuClick }: { onMenuClick?: () => void }) {
  const navigate = useNavigate()

  // MCP activity — a top-bar icon that pulses when a connected AI is running something.
  // The drawer is retired: the icon goes to Activity, the one place work is read.
  const { data: conns } = useQuery({ queryKey: ["mcp-connections"], queryFn: listMcpConnections })
  const hasMcp = (conns?.length ?? 0) > 0
  const { data: activity = [] } = useMcpActivity(false, hasMcp)
  const runningCount = activity.filter((a) => a.status === "running").length

  // The drawer is opened by hand, never by itself. It used to slide down whenever a new
  // burst of activity started, which meant it reappeared over the page every few minutes
  // and covered the right-hand side of whatever was being read. The badge below already
  // says something is running — that is the notification; this is the detail, and asking
  // for the detail is the reader's decision.

  return (
    <header className="relative z-20 flex h-14 items-center justify-between gap-4 border-b border-border bg-card px-4 shadow-[0_4px_14px_-3px_rgba(15,23,42,0.12)] sm:px-6">
      <div className="flex min-w-0 items-center gap-1.5">
        {/* Hamburger — opens the navigation drawer on mobile (sidebar is static on lg). */}
        <button
          onClick={onMenuClick}
          aria-label="Open menu"
          className="-ml-1 flex items-center justify-center rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-foreground lg:hidden"
        >
          <Menu size={18} />
        </button>
        <Breadcrumbs />
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <RunningPill />
        {/* MCP activity — pulses green while a connected AI is running something; click to
            slide the live activity drawer down from the bar. */}
        {hasMcp && (
          <button
            data-mcp-toggle
            onClick={() => navigate("/activity")}
            title={
              runningCount > 0
                ? `${runningCount} MCP action${runningCount === 1 ? "" : "s"} running`
                : "MCP activity — what your connected AI is doing"
            }
            className={`relative flex items-center justify-center rounded-md p-2 transition-colors ${
              runningCount > 0
                ? "text-emerald-600 hover:bg-emerald-500/10 dark:text-emerald-400"
                : "text-muted-foreground hover:bg-accent hover:text-foreground"
            }`}
          >
            <span className="relative flex items-center justify-center">
              {runningCount > 0 && (
                <span className="absolute -right-1 -top-1 flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                </span>
              )}
              <Activity size={16} />
            </span>
          </button>
        )}
        <button
          onClick={() => navigate("/logs")}
          title="Activity log"
          className="relative flex items-center justify-center rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <History size={16} />
        </button>
        <NotificationBell />
        <div className="mx-1 h-6 w-px bg-border" />
        <UserMenu />
      </div>
    </header>
  )
}

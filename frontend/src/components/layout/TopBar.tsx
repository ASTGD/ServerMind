import { useEffect, useRef } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { History, Menu, Activity } from "lucide-react"
import Breadcrumbs from "./Breadcrumbs"
import NotificationBell from "./NotificationBell"
import UserMenu from "./UserMenu"
import { useMcpDrawerStore } from "@/store/mcpDrawerStore"
import { useMcpActivity } from "@/hooks/useMcpActivity"
import { listMcpConnections } from "@/api/mcp"

export default function TopBar({ onMenuClick }: { onMenuClick?: () => void }) {
  const navigate = useNavigate()

  // MCP activity — a top-bar icon that pulses when a connected AI is running something, and
  // toggles the floating activity drawer. Only shown to users who've connected an AI client.
  const mcpOpen = useMcpDrawerStore((s) => s.open)
  const toggleMcp = useMcpDrawerStore((s) => s.toggle)
  const setMcpOpen = useMcpDrawerStore((s) => s.setOpen)
  const mcpSuppressed = useMcpDrawerStore((s) => s.suppressed)
  const setMcpSuppressed = useMcpDrawerStore((s) => s.setSuppressed)
  const { data: conns } = useQuery({ queryKey: ["mcp-connections"], queryFn: listMcpConnections })
  const hasMcp = (conns?.length ?? 0) > 0
  const { data: activity = [] } = useMcpActivity(mcpOpen, hasMcp)
  const runningCount = activity.filter((a) => a.status === "running").length

  // Auto-slide the drawer down when a NEW run-burst starts (0 → running), unless the user
  // just collapsed it; reset that suppression once the fleet goes idle again.
  const prevRunning = useRef(0)
  useEffect(() => {
    if (runningCount > 0 && prevRunning.current === 0 && !mcpSuppressed) setMcpOpen(true)
    if (runningCount === 0 && mcpSuppressed) setMcpSuppressed(false)
    prevRunning.current = runningCount
  }, [runningCount, mcpSuppressed, setMcpOpen, setMcpSuppressed])

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
        {/* MCP activity — pulses green while a connected AI is running something; click to
            slide the live activity drawer down from the bar. */}
        {hasMcp && (
          <button
            data-mcp-toggle
            onClick={toggleMcp}
            title={
              runningCount > 0
                ? `${runningCount} MCP action${runningCount === 1 ? "" : "s"} running`
                : "MCP activity — what your connected AI is doing"
            }
            className={`relative flex items-center justify-center rounded-md p-2 transition-colors ${
              runningCount > 0
                ? "text-emerald-600 hover:bg-emerald-500/10 dark:text-emerald-400"
                : mcpOpen
                  ? "bg-accent text-foreground"
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

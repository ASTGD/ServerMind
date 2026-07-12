import { useState } from "react"
import { NavLink } from "react-router-dom"
import { useTranslation } from "react-i18next"
import {
  LayoutDashboard,
  Boxes,
  BookOpen,
  FileCode,
  Users,
  Settings,
  Sparkles,
  ArrowRight,
  Rocket,
  ChevronDown,
  ChevronUp,
  FlaskConical,
  Terminal as TerminalIcon,
} from "lucide-react"
import Logo from "@/components/brand/Logo"
import UpgradeModal from "./UpgradeModal"
import { useAssistantStore } from "@/store/assistantStore"
import { useTerminalStore } from "@/store/terminalStore"
import { useAuthStore } from "@/store/authStore"

const navItems = [
  { to: "/dashboard", icon: LayoutDashboard, key: "dashboard" },
  { to: "/servers", icon: Boxes, key: "servers" },
  { to: "/playbooks", icon: BookOpen, key: "playbooks" },
  { to: "/scripts", icon: FileCode, key: "scripts" },
  { to: "/missions", icon: Rocket, key: "missions" },
  { to: "/team", icon: Users, key: "team" },
  { to: "/settings", icon: Settings, key: "settings" },
] as const

export default function Sidebar() {
  const { t } = useTranslation()
  const [showUpgrade, setShowUpgrade] = useState(false)
  const isAdmin = useAuthStore((s) => s.user?.is_admin)
  const assistantOpen = useAssistantStore((s) => s.open)
  const toggleAssistant = useAssistantStore((s) => s.toggle)
  const terminalOpen = useTerminalStore((s) => s.open)
  const toggleTerminal = useTerminalStore((s) => s.toggle)
  const termCount = useTerminalStore((s) => s.sessions.length)
  // Live status on the Ally button: a mission is running (or paused for your OK).
  const missionActive = useAssistantStore((s) =>
    s.messages.some(
      (m) => m.role === "assistant" && m.kind === "mission" && (m.mission.status === "running" || m.mission.status === "blocked"),
    ),
  )

  return (
    <>
      <aside className="flex w-60 flex-col border-r border-border bg-card px-3 py-5">
        <div className="mb-7 px-2">
          <Logo size="lg" />
        </div>

        <nav className="flex flex-col gap-1">
          {navItems.map(({ to, icon: Icon, key }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] transition-colors ${
                  isActive
                    ? "bg-accent font-medium text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                }`
              }
            >
              <Icon size={19} className="shrink-0" />
              {t(`nav.${key}`)}
            </NavLink>
          ))}
          {/* Admin-only Dev Door — hidden for customers (backend 403s them regardless). */}
          {isAdmin && (
            <NavLink
              to="/dev"
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] transition-colors ${
                  isActive
                    ? "bg-accent font-medium text-accent-foreground"
                    : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                }`
              }
            >
              <FlaskConical size={19} className="shrink-0" />
              Dev
            </NavLink>
          )}
        </nav>

        {/* Pinned to the bottom — Ally + Terminal as standalone action buttons (not
            regular menu items), then the upgrade row, all in one bottom panel. */}
        <div className="mt-auto -mx-3 border-t border-border px-3 pt-3">
          {assistantOpen ? (
            /* The Ally window is open — the composer lives inside it, so here we show the
               round Ally icon with "Ally ⌄" and a "click to minimise" hint. Same rounded-pill
               shape as the composer, so opening/closing just swaps the pill's contents. */
            <button
              onClick={toggleAssistant}
              title="Minimize Ally"
              className="flex w-full items-center gap-2.5 rounded-full border border-border bg-accent/40 py-1.5 pl-1.5 pr-3 text-left transition-colors hover:bg-accent"
            >
              <span className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-white">
                <Sparkles size={16} />
                {missionActive && (
                  <span className="absolute -right-0.5 -top-0.5 flex h-2.5 w-2.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex h-2.5 w-2.5 rounded-full border-2 border-card bg-emerald-500" />
                  </span>
                )}
              </span>
              <span className="min-w-0 flex-1 leading-tight">
                <span className="flex items-center gap-1 text-sm font-medium text-foreground">
                  Ally
                  <ChevronDown size={14} className="text-muted-foreground" />
                </span>
                <span className="block truncate text-xs text-muted-foreground">
                  {missionActive ? "Working on a mission…" : "click to minimise"}
                </span>
              </span>
            </button>
          ) : (
            /* Ally launcher — a plain button (not a text box); click opens the floating
               window (where you type). A live dot on the icon means a mission is running. */
            <button
              onClick={toggleAssistant}
              title="Open Ally"
              className="flex w-full items-center gap-2.5 rounded-full border border-border bg-background py-1.5 pl-1.5 pr-3 text-left transition-colors hover:border-primary/40 hover:bg-accent"
            >
              <span className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-white">
                <Sparkles size={16} />
                {missionActive && (
                  <span className="absolute -right-0.5 -top-0.5 flex h-2.5 w-2.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex h-2.5 w-2.5 rounded-full border-2 border-background bg-emerald-500" />
                  </span>
                )}
              </span>
              <span className="flex-1 text-sm font-medium text-foreground">Ask Ally</span>
              <ChevronUp size={15} className="shrink-0 text-muted-foreground" />
            </button>
          )}

          {/* Terminal dock — mirrors Ally: a floating window that minimizes here. A green
              dot means live SSH sessions are running (they keep running when minimized). */}
          {terminalOpen ? (
            <button
              onClick={toggleTerminal}
              title="Minimize Terminal"
              className="mt-2 flex w-full items-center gap-2.5 rounded-full border border-border bg-accent/40 py-1.5 pl-1.5 pr-3 text-left transition-colors hover:bg-accent"
            >
              <span className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-emerald-300">
                <TerminalIcon size={16} />
                {termCount > 0 && (
                  <span className="absolute -right-0.5 -top-0.5 flex h-2.5 w-2.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex h-2.5 w-2.5 rounded-full border-2 border-card bg-emerald-500" />
                  </span>
                )}
              </span>
              <span className="min-w-0 flex-1 leading-tight">
                <span className="flex items-center gap-1 text-sm font-medium text-foreground">
                  Terminal
                  <ChevronDown size={14} className="text-muted-foreground" />
                </span>
                <span className="block truncate text-xs text-muted-foreground">
                  {termCount > 0 ? `${termCount} session${termCount === 1 ? "" : "s"} running` : "click to minimise"}
                </span>
              </span>
            </button>
          ) : (
            <button
              onClick={toggleTerminal}
              title="Open Terminal"
              className="mt-2 flex w-full items-center gap-2.5 rounded-full border border-border bg-background py-1.5 pl-1.5 pr-3 text-left transition-colors hover:border-primary/40 hover:bg-accent"
            >
              <span className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-zinc-300">
                <TerminalIcon size={16} />
                {termCount > 0 && (
                  <span className="absolute -right-0.5 -top-0.5 flex h-2.5 w-2.5">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex h-2.5 w-2.5 rounded-full border-2 border-background bg-emerald-500" />
                  </span>
                )}
              </span>
              <span className="flex-1 text-sm font-medium text-foreground">Terminal</span>
              <ChevronUp size={15} className="shrink-0 text-muted-foreground" />
            </button>
          )}

          <div className="my-3 border-t border-border" />

          <button
            onClick={() => setShowUpgrade(true)}
            className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
          >
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-indigo-500 to-violet-500 text-white">
              <Sparkles size={13} />
            </span>
            <span className="flex-1 text-left">Upgrade to Pro</span>
            <ArrowRight size={14} className="text-muted-foreground" />
          </button>
        </div>
      </aside>

      {showUpgrade && <UpgradeModal onClose={() => setShowUpgrade(false)} />}
    </>
  )
}

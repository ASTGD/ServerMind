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
  Terminal as TerminalIcon,
} from "lucide-react"
import Logo from "@/components/brand/Logo"
import UpgradeModal from "./UpgradeModal"
import { useTerminalStore } from "@/store/terminalStore"

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
  const termCount = useTerminalStore((s) => s.sessions.length)

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
        </nav>

        {/* Pinned to the bottom — Ally + Terminal as standalone action buttons (not
            regular menu items), then the upgrade row, all in one bottom panel. */}
        <div className="mt-auto -mx-3 border-t border-border px-3 pt-3">
          <div className="grid grid-cols-2 gap-2">
            <NavLink
              to="/assistant"
              className={({ isActive }) =>
                `flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-indigo-500 to-violet-500 py-2.5 text-sm font-medium text-white transition-shadow hover:opacity-90 ${
                  isActive ? "ring-2 ring-indigo-300 dark:ring-indigo-800" : ""
                }`
              }
            >
              <Sparkles size={16} />
              {t("nav.assistant")}
            </NavLink>
            <NavLink
              to="/terminal"
              className={({ isActive }) =>
                `relative flex items-center justify-center gap-1.5 rounded-lg border py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? "border-primary/40 bg-accent text-accent-foreground"
                    : termCount > 0
                    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 hover:bg-emerald-500/20 dark:text-emerald-400"
                    : "border-border text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                }`
              }
            >
              <TerminalIcon size={16} />
              {t("nav.terminal")}
              {termCount > 0 && (
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
                </span>
              )}
            </NavLink>
          </div>

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

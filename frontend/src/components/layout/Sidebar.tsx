import { NavLink, Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import {
  LayoutDashboard,
  Server,
  BookOpen,
  FileCode,
  ScrollText,
  Users,
  Settings,
  Sparkles,
  ArrowRight,
} from "lucide-react"
import Logo from "@/components/brand/Logo"

const navItems = [
  { to: "/dashboard", icon: LayoutDashboard, key: "dashboard" },
  { to: "/servers", icon: Server, key: "servers" },
  { to: "/playbooks", icon: BookOpen, key: "playbooks" },
  { to: "/scripts", icon: FileCode, key: "scripts" },
  { to: "/logs", icon: ScrollText, key: "logs" },
  { to: "/team", icon: Users, key: "team" },
  { to: "/settings", icon: Settings, key: "settings" },
] as const

export default function Sidebar() {
  const { t } = useTranslation()

  return (
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

      {/* Pinned to the bottom — a compact upgrade row, attached as a footer. */}
      <div className="mt-auto -mx-3 border-t border-border px-3 pt-3">
        <Link
          to="/settings"
          className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-accent"
        >
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-gradient-to-br from-indigo-500 to-violet-500 text-white">
            <Sparkles size={13} />
          </span>
          <span className="flex-1">Upgrade to Pro</span>
          <ArrowRight size={14} className="text-muted-foreground" />
        </Link>
      </div>
    </aside>
  )
}

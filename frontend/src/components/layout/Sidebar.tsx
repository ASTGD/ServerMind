import { NavLink } from "react-router-dom"
import { useTranslation } from "react-i18next"
import {
  LayoutDashboard,
  Server,
  BookOpen,
  FileCode,
  ScrollText,
  Users,
  Settings,
} from "lucide-react"

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
    <aside className="flex w-56 flex-col border-r border-border bg-card px-3 py-4">
      <div className="mb-6 px-3">
        <span className="text-lg font-semibold text-foreground">
          {t("app.name")}
        </span>
      </div>
      <nav className="flex flex-col gap-1">
        {navItems.map(({ to, icon: Icon, key }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors ${
                isActive
                  ? "bg-accent text-accent-foreground font-medium"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              }`
            }
          >
            <Icon size={16} />
            {t(`nav.${key}`)}
          </NavLink>
        ))}
      </nav>
    </aside>
  )
}

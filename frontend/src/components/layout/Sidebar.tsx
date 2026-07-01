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

      {/* Pinned to the bottom — Pro upgrade card. */}
      <div className="mt-auto pt-5">
        <div className="overflow-hidden rounded-xl bg-gradient-to-br from-indigo-500 to-violet-600 p-4 text-white shadow-sm">
          <div className="flex items-center gap-1.5">
            <Sparkles size={15} className="shrink-0" />
            <span className="text-sm font-semibold">Upgrade to Pro</span>
          </div>
          <p className="mt-1.5 text-xs leading-relaxed text-white/85">
            Unlock AI automations, unlimited servers, and priority support.
          </p>
          <Link
            to="/settings"
            className="mt-3 flex items-center justify-center gap-1 rounded-lg bg-white/15 py-1.5 text-xs font-medium text-white transition-colors hover:bg-white/25"
          >
            Upgrade
            <ArrowRight size={12} />
          </Link>
        </div>
      </div>
    </aside>
  )
}

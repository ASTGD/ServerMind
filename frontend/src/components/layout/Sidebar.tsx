import { useState, type ReactNode } from "react"
import { NavLink } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import type { LucideIcon } from "lucide-react"
import {
  LayoutDashboard, Boxes, BookOpen, FileCode, Users, Settings, Sparkles,
  Rocket, FileText, FlaskConical, ArrowUpRight, Sun, Moon, Monitor,
} from "lucide-react"
import Logo from "@/components/brand/Logo"
import UpgradeModal from "./UpgradeModal"
import { Card, Button, Badge } from "@/components/ui"
import { useAssistantStore } from "@/store/assistantStore"
import { useAuthStore } from "@/store/authStore"
import { useThemeStore, type Theme } from "@/store/themeStore"
import { getMyUsage } from "@/api/usage"
import { listMissions } from "@/api/missions"
import { cn } from "@/lib/utils"

/** Mission statuses that want the user's attention — surfaced as a badge on the Missions item. */
const NEEDS_YOU = new Set(["blocked", "awaiting_approval", "interrupted"])

/** A single nav row — icon + label, an edge indicator when active, optional attention badge. */
function NavItem({
  to, icon: Icon, label, badge, onClick,
}: { to: string; icon: LucideIcon; label: string; badge?: number; onClick?: () => void }) {
  return (
    <NavLink
      to={to}
      onClick={onClick}
      className={({ isActive }) =>
        cn(
          "group relative flex items-center gap-2.5 rounded-lg px-3 py-2 text-[13.5px] transition-colors",
          isActive
            ? "bg-accent font-medium text-accent-foreground"
            : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
        )
      }
    >
      {({ isActive }) => (
        <>
          {/* Active indicator — a slim bar hugging the sidebar's left edge. */}
          <span
            aria-hidden="true"
            className={cn(
              "absolute -left-3 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-primary transition-opacity",
              isActive ? "opacity-100" : "opacity-0",
            )}
          />
          <Icon
            size={17}
            className={cn(
              "shrink-0 transition-colors",
              isActive ? "text-primary" : "text-muted-foreground/70 group-hover:text-foreground",
            )}
          />
          <span className="flex-1 truncate">{label}</span>
          {badge ? (
            <span className="shrink-0 rounded-full bg-warning/15 px-1.5 py-0.5 text-[10px] font-semibold text-warning">
              {badge > 9 ? "9+" : badge}
            </span>
          ) : null}
        </>
      )}
    </NavLink>
  )
}

/** Uppercase group label for a nav section. */
function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <p className="px-3 pb-1.5 pt-5 text-[10.5px] font-semibold uppercase tracking-[0.09em] text-muted-foreground/60">
      {children}
    </p>
  )
}

const THEME_OPTIONS: { value: Theme; icon: LucideIcon; label: string }[] = [
  { value: "light", icon: Sun, label: "Light" },
  { value: "dark", icon: Moon, label: "Dark" },
  { value: "system", icon: Monitor, label: "System" },
]

/** Compact Light / Dark / System segmented control. */
function ThemeToggle() {
  const theme = useThemeStore((s) => s.theme)
  const setTheme = useThemeStore((s) => s.setTheme)
  return (
    <div className="flex rounded-lg border border-border bg-background p-0.5" role="group" aria-label="Theme">
      {THEME_OPTIONS.map(({ value, icon: Icon, label }) => (
        <button
          key={value}
          onClick={() => setTheme(value)}
          title={label}
          aria-pressed={theme === value}
          className={cn(
            "flex flex-1 items-center justify-center rounded-md py-1 transition-colors",
            theme === value
              ? "bg-muted text-foreground shadow-sm"
              : "text-muted-foreground/60 hover:text-foreground",
          )}
        >
          <Icon size={14} />
        </button>
      ))}
    </div>
  )
}

export default function Sidebar({ open = false, onClose }: { open?: boolean; onClose?: () => void }) {
  const { t } = useTranslation()
  const [showUpgrade, setShowUpgrade] = useState(false)
  const isAdmin = useAuthStore((s) => s.user?.is_admin)
  const assistantOpen = useAssistantStore((s) => s.open)
  const toggleAssistant = useAssistantStore((s) => s.toggle)
  // A live dot on the Ask Ally button when a mission is running (or paused for your OK).
  const missionActive = useAssistantStore((s) =>
    s.messages.some(
      (m) => m.role === "assistant" && m.kind === "mission" && (m.mission.status === "running" || m.mission.status === "blocked"),
    ),
  )

  const { data: usage } = useQuery({ queryKey: ["usage"], queryFn: getMyUsage, staleTime: 60_000 })
  const { data: missions = [] } = useQuery({ queryKey: ["missions"], queryFn: () => listMissions(), refetchInterval: 60_000 })
  const needsYou = missions.filter((m) => NEEDS_YOU.has(m.status)).length
  const isPro = (usage?.plan ?? "free").toLowerCase() === "pro"
  const actionPct = usage ? Math.min(100, Math.round((usage.used / Math.max(1, usage.limit)) * 100)) : 0

  const openAlly = () => {
    toggleAssistant()
    onClose?.()
  }

  return (
    <>
      {/* Mobile backdrop — tap to close the drawer (hidden on lg where the sidebar is static). */}
      <div
        onClick={onClose}
        aria-hidden="true"
        className={cn(
          "fixed inset-0 z-40 bg-black/40 transition-opacity lg:hidden",
          open ? "opacity-100" : "pointer-events-none opacity-0",
        )}
      />
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-60 flex-col overflow-y-auto border-r border-border bg-card px-3 py-4 transition-transform lg:static lg:z-auto lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
        )}
      >
        <div className="mb-5 px-2 pt-0.5">
          <Logo size="lg" />
        </div>

        <nav className="flex flex-col gap-0.5">
          <NavItem to="/dashboard" icon={LayoutDashboard} label={t("nav.dashboard")} onClick={onClose} />
          <NavItem to="/servers" icon={Boxes} label={t("nav.servers")} onClick={onClose} />

          <SectionLabel>Automate</SectionLabel>
          <NavItem to="/missions" icon={Rocket} label={t("nav.missions")} badge={needsYou || undefined} onClick={onClose} />
          <NavItem to="/reports" icon={FileText} label={t("nav.reports")} onClick={onClose} />
          <NavItem to="/playbooks" icon={BookOpen} label={t("nav.playbooks")} onClick={onClose} />
          <NavItem to="/scripts" icon={FileCode} label={t("nav.scripts")} onClick={onClose} />

          <SectionLabel>Account</SectionLabel>
          <NavItem to="/team" icon={Users} label={t("nav.team")} onClick={onClose} />
          <NavItem to="/settings" icon={Settings} label={t("nav.settings")} onClick={onClose} />
          {isAdmin && <NavItem to="/dev" icon={FlaskConical} label="Dev" onClick={onClose} />}
        </nav>

        {/* Pinned to the bottom — Ask Ally (the hero) sits just above the plan card. The
            floating window grows out of / flies back into this button. */}
        <div className="mt-auto flex flex-col gap-3 pt-4">
          <button
            onClick={openAlly}
            title={assistantOpen ? "Minimize Ally" : "Ask Ally (⌘K)"}
            className={cn(
              "flex w-full items-center gap-2.5 rounded-xl bg-brand-gradient px-3 py-2.5 text-white shadow-md shadow-primary/20 transition hover:opacity-95",
              assistantOpen && "ring-2 ring-primary/40",
            )}
          >
            <span className="relative flex h-6 w-6 items-center justify-center">
              <Sparkles size={17} />
              {missionActive && (
                <span className="absolute -right-1 -top-1 flex h-2.5 w-2.5">
                  {/* Fixed emerald on the fixed gradient — same contrast in both themes. */}
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full border-2 border-indigo-500 bg-emerald-400" />
                </span>
              )}
            </span>
            <span className="flex-1 text-left text-sm font-medium">Ask Ally</span>
            <kbd className="rounded bg-white/15 px-1.5 py-0.5 text-[10px] font-medium tracking-wide">⌘K</kbd>
          </button>

          {/* Plan card — the upgrade CTA with the context of your live usage. */}
          <Card className="bg-background p-3">
            <div className="mb-2 flex items-center justify-between">
              <Badge variant={isPro ? "brand" : "outline"} className="px-2 py-px">
                {isPro ? "Pro plan" : "Free plan"}
              </Badge>
              {usage && (
                <span className="text-[10px] text-muted-foreground">
                  {usage.servers_used} of {usage.servers_limit} servers
                </span>
              )}
            </div>
            <div className="mb-1 flex items-center justify-between text-[10.5px] text-muted-foreground">
              <span>Actions this month</span>
              <span className="tabular-nums">{usage ? `${usage.used} / ${usage.limit}` : "—"}</span>
            </div>
            <div className="mb-2.5 h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-brand-gradient-r transition-[width] duration-500"
                style={{ width: `${actionPct}%` }}
              />
            </div>
            {!isPro && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setShowUpgrade(true)}
                className="w-full border-primary/40 bg-primary/5 text-xs text-primary hover:bg-primary/10"
              >
                <ArrowUpRight size={14} /> Upgrade to Pro
              </Button>
            )}
          </Card>

          <ThemeToggle />
        </div>
      </aside>

      {showUpgrade && <UpgradeModal onClose={() => setShowUpgrade(false)} />}
    </>
  )
}

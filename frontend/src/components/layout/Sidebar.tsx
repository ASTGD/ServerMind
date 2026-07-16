import { useState } from "react"
import { NavLink } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { useTranslation } from "react-i18next"
import type { LucideIcon } from "lucide-react"
import {
  LayoutDashboard, Boxes, BookOpen, FileCode, Users, Settings, Sparkles,
  Rocket, FileText, FlaskConical, ArrowUpRight,
} from "lucide-react"
import Logo from "@/components/brand/Logo"
import UpgradeModal from "./UpgradeModal"
import { useAssistantStore } from "@/store/assistantStore"
import { useAuthStore } from "@/store/authStore"
import { getMyUsage } from "@/api/usage"
import { listMissions } from "@/api/missions"
import { cn } from "@/lib/utils"

/** Mission statuses that want the user's attention — surfaced as a badge on the Missions item. */
const NEEDS_YOU = new Set(["blocked", "awaiting_approval", "interrupted"])

/** A single nav row (icon + label, optional attention badge). */
function NavItem({
  to, icon: Icon, label, badge, onClick,
}: { to: string; icon: LucideIcon; label: string; badge?: number; onClick?: () => void }) {
  return (
    <NavLink
      to={to}
      onClick={onClick}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-lg px-3 py-2 text-[14px] transition-colors",
          isActive
            ? "bg-accent font-medium text-accent-foreground"
            : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
        )
      }
    >
      <Icon size={18} className="shrink-0" />
      <span className="flex-1 truncate">{label}</span>
      {badge ? (
        <span className="shrink-0 rounded-full bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-600 dark:text-amber-400">
          {badge > 9 ? "9+" : badge}
        </span>
      ) : null}
    </NavLink>
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
        <div className="mb-4 px-2">
          <Logo size="lg" />
        </div>

        {/* Ask Ally — the hero action. The floating window grows out of this button. */}
        <button
          onClick={openAlly}
          title={assistantOpen ? "Minimize Ally" : "Ask Ally (⌘K)"}
          className={cn(
            "mb-4 flex w-full items-center gap-2.5 rounded-xl bg-gradient-to-br from-indigo-500 to-violet-500 px-3 py-2.5 text-white shadow-sm transition hover:opacity-95",
            assistantOpen && "ring-2 ring-primary/40",
          )}
        >
          <span className="relative flex h-6 w-6 items-center justify-center">
            <Sparkles size={17} />
            {missionActive && (
              <span className="absolute -right-1 -top-1 flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full border-2 border-indigo-500 bg-emerald-400" />
              </span>
            )}
          </span>
          <span className="flex-1 text-left text-sm font-medium">Ask Ally</span>
          <kbd className="rounded bg-white/15 px-1.5 py-0.5 text-[10px] font-medium tracking-wide">⌘K</kbd>
        </button>

        <nav className="flex flex-col gap-0.5">
          <NavItem to="/dashboard" icon={LayoutDashboard} label={t("nav.dashboard")} onClick={onClose} />
          <NavItem to="/servers" icon={Boxes} label={t("nav.servers")} onClick={onClose} />

          <p className="px-3 pb-1 pt-4 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Automate</p>
          <NavItem to="/missions" icon={Rocket} label={t("nav.missions")} badge={needsYou || undefined} onClick={onClose} />
          <NavItem to="/reports" icon={FileText} label={t("nav.reports")} onClick={onClose} />
          <NavItem to="/playbooks" icon={BookOpen} label={t("nav.playbooks")} onClick={onClose} />
          <NavItem to="/scripts" icon={FileCode} label={t("nav.scripts")} onClick={onClose} />
        </nav>

        {/* Pinned to the bottom — account nav + the plan card. */}
        <div className="mt-auto flex flex-col gap-0.5 pt-3">
          <div className="mx-2 mb-1 border-t border-border" />
          <NavItem to="/team" icon={Users} label={t("nav.team")} onClick={onClose} />
          <NavItem to="/settings" icon={Settings} label={t("nav.settings")} onClick={onClose} />
          {isAdmin && <NavItem to="/dev" icon={FlaskConical} label="Dev" onClick={onClose} />}

          {/* Plan card — the upgrade CTA with the context of your live usage. */}
          <div className="mt-3 rounded-xl border border-border bg-background p-3">
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium text-foreground">{isPro ? "Pro plan" : "Free plan"}</span>
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
                className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-[width] duration-500"
                style={{ width: `${actionPct}%` }}
              />
            </div>
            {!isPro && (
              <button
                onClick={() => setShowUpgrade(true)}
                className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-primary/40 bg-primary/5 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/10"
              >
                <ArrowUpRight size={14} /> Upgrade to Pro
              </button>
            )}
          </div>
        </div>
      </aside>

      {showUpgrade && <UpgradeModal onClose={() => setShowUpgrade(false)} />}
    </>
  )
}

import { Link } from "react-router-dom"
import { Plus, BookOpen, Wand2, Users, ChevronRight } from "lucide-react"
import type { LucideIcon } from "lucide-react"

const actions: { icon: LucideIcon; label: string; desc: string; to: string }[] = [
  { icon: Plus, label: "Add a server", desc: "Connect a server or host", to: "/servers" },
  { icon: BookOpen, label: "Browse playbooks", desc: "One-click installs & setups", to: "/playbooks" },
  { icon: Wand2, label: "Generate a script", desc: "AI-built for your task", to: "/scripts/generate" },
  { icon: Users, label: "Invite your team", desc: "Share server access", to: "/team" },
]

/** Shortcut links to the most common starting points. */
export default function QuickActions() {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <h2 className="text-sm font-semibold text-foreground">Quick actions</h2>
      <div className="mt-3 -mx-2 space-y-0.5">
        {actions.map((a) => (
          <Link
            key={a.to}
            to={a.to}
            className="group flex items-center gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-muted/60"
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground/70 group-hover:text-foreground">
              <a.icon size={16} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground">{a.label}</p>
              <p className="truncate text-xs text-muted-foreground">{a.desc}</p>
            </div>
            <ChevronRight size={15} className="text-muted-foreground/50 group-hover:text-muted-foreground" />
          </Link>
        ))}
      </div>
    </div>
  )
}

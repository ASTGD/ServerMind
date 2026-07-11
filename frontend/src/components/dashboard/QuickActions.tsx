import { Link } from "react-router-dom"
import { Plus, BookOpen, Wand2, Users } from "lucide-react"
import type { LucideIcon } from "lucide-react"

const actions: { icon: LucideIcon; label: string; to: string }[] = [
  { icon: Plus, label: "Add server", to: "/servers" },
  { icon: BookOpen, label: "Playbooks", to: "/playbooks" },
  { icon: Wand2, label: "Generate script", to: "/scripts/generate" },
  { icon: Users, label: "Invite team", to: "/team" },
]

/** Compact icon-tile shortcuts to the most common starting points. */
export default function QuickActions() {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <h2 className="mb-3 text-sm font-semibold text-foreground">Quick actions</h2>
      <div className="grid grid-cols-2 gap-2">
        {actions.map((a) => (
          <Link
            key={a.to}
            to={a.to}
            className="flex flex-col items-start gap-1.5 rounded-lg bg-muted/60 p-2.5 transition-colors hover:bg-muted"
          >
            <a.icon size={17} className="text-primary" />
            <span className="text-xs text-foreground">{a.label}</span>
          </Link>
        ))}
      </div>
    </div>
  )
}

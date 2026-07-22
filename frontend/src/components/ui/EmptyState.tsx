import type { ReactNode } from "react"
import type { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

interface EmptyStateProps {
  icon?: LucideIcon
  title: ReactNode
  description?: ReactNode
  /** Call-to-action, e.g. a <Button>. */
  action?: ReactNode
  className?: string
}

/** Friendly empty state — dashed frame, muted icon, title + hint + optional CTA. */
export default function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center rounded-xl border border-dashed border-border px-6 py-16 text-center",
        className,
      )}
    >
      {Icon && <Icon className="mb-3 h-10 w-10 text-muted-foreground/30" />}
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description && <p className="mt-1 max-w-sm text-xs text-muted-foreground/70">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

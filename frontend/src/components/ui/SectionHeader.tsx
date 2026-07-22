import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

interface SectionHeaderProps {
  title: ReactNode
  description?: ReactNode
  /** Right-aligned actions (buttons, filters). */
  actions?: ReactNode
  /** "page" = the route's main header (h1); "section" = a block inside a page (h2). */
  level?: "page" | "section"
  className?: string
}

/** Consistent page/section heading: title + optional description, actions on the right. */
export default function SectionHeader({ title, description, actions, level = "page", className }: SectionHeaderProps) {
  const Tag = level === "page" ? "h1" : "h2"
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        <Tag className={cn("text-foreground", level === "page" ? "text-h1" : "text-h3")}>{title}</Tag>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

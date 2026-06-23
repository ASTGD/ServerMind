import { Link } from "react-router-dom"
import type { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

type Tone = "default" | "green" | "amber" | "blue"

const toneClasses: Record<Tone, string> = {
  default: "bg-primary/10 text-primary",
  green: "bg-green-500/10 text-green-600",
  amber: "bg-amber-500/10 text-amber-600",
  blue: "bg-blue-500/10 text-blue-600",
}

interface Props {
  icon: LucideIcon
  label: string
  value: string | number
  sub?: string
  tone?: Tone
  to?: string
  loading?: boolean
}

/** A KPI tile for the dashboard. Becomes a link when `to` is provided. */
export default function StatCard({ icon: Icon, label, value, sub, tone = "default", to, loading }: Props) {
  const inner = (
    <>
      <div className="flex items-center justify-between">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className={cn("flex h-9 w-9 items-center justify-center rounded-lg", toneClasses[tone])}>
          <Icon size={18} />
        </span>
      </div>
      {loading ? (
        <div className="mt-3 h-8 w-14 animate-pulse rounded bg-muted" />
      ) : (
        <p className="mt-3 text-3xl font-semibold tabular-nums text-foreground">{value}</p>
      )}
      {sub && <p className="mt-1 text-xs text-muted-foreground">{sub}</p>}
    </>
  )

  const className = cn(
    "block rounded-xl border border-border bg-card p-5",
    to && "transition-all hover:border-primary/40 hover:shadow-sm",
  )

  return to ? (
    <Link to={to} className={className}>
      {inner}
    </Link>
  ) : (
    <div className={className}>{inner}</div>
  )
}

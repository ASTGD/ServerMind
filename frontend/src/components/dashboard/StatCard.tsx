import { Link } from "react-router-dom"
import type { LucideIcon } from "lucide-react"
import { cn } from "@/lib/utils"

type Tone = "default" | "green" | "amber" | "red"

const valueTone: Record<Tone, string> = {
  default: "text-foreground",
  green: "text-success",
  amber: "text-warning",
  red: "text-destructive",
}

interface Props {
  icon: LucideIcon
  label: string
  value: string | number
  tone?: Tone
  to?: string
  loading?: boolean
}

/** A compact KPI tile for the dashboard strip. Becomes a link when `to` is provided. */
export default function StatCard({ icon: Icon, label, value, tone = "default", to, loading }: Props) {
  const inner = (
    <>
      <div className="flex items-center gap-1.5 text-muted-foreground">
        <Icon size={15} />
        <span className="text-xs">{label}</span>
      </div>
      {loading ? (
        <div className="mt-2.5 h-6 w-10 animate-pulse rounded bg-muted" />
      ) : (
        <p className={cn("mt-1.5 text-[22px] font-semibold tabular-nums", valueTone[tone])}>{value}</p>
      )}
    </>
  )

  const className = cn(
    "block rounded-xl border border-border bg-card px-4 py-3.5",
    to && "transition-colors hover:border-primary/40",
  )

  return to ? (
    <Link to={to} className={className}>
      {inner}
    </Link>
  ) : (
    <div className={className}>{inner}</div>
  )
}

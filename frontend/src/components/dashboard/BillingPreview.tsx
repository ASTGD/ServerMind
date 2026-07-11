import { DollarSign, Users, Receipt } from "lucide-react"
import type { LucideIcon } from "lucide-react"

const tiles: { icon: LucideIcon; label: string }[] = [
  { icon: DollarSign, label: "Revenue" },
  { icon: Users, label: "Customers" },
  { icon: Receipt, label: "Orders" },
]

/** A dimmed preview of the business metrics coming once billing ships — shows the
 *  KPI grid is built to grow into a SaaS dashboard without faking numbers today. */
export default function BillingPreview() {
  return (
    <div>
      <p className="mb-2 text-xs text-muted-foreground">Coming with billing</p>
      <div className="grid grid-cols-3 gap-3">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-lg border border-dashed border-border px-3.5 py-3">
            <div className="flex items-center gap-1.5 text-muted-foreground">
              <t.icon size={15} />
              <span className="text-xs">{t.label}</span>
            </div>
            <p className="mt-1.5 text-[22px] font-semibold text-muted-foreground">—</p>
          </div>
        ))}
      </div>
    </div>
  )
}

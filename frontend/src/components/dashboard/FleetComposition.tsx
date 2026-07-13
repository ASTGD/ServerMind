import { useMemo } from "react"
import type { Server } from "@/types"
import { ASSET_CATEGORIES, categoryForServer, type AssetCategoryId } from "@/lib/assetCategories"
import { cn } from "@/lib/utils"

const CATEGORY_BAR: Record<AssetCategoryId, string> = {
  bare_metal: "bg-slate-500",
  vps: "bg-indigo-500",
  hosting: "bg-emerald-500",
  windows: "bg-sky-500",
  windows_rdp: "bg-cyan-500",
  cloud: "bg-violet-500",
}

/** Fleet breakdown by asset category, as a single glanceable color bar + legend
 *  instead of a plain number list — computed client-side from data the Dashboard
 *  already loaded (no new requests). Grade distribution now lives exclusively in
 *  the Fleet health donut, so this panel stays purely about asset type. */
export default function FleetComposition({ servers }: { servers: Server[] }) {
  const counts = useMemo(() => {
    const c = new Map<AssetCategoryId, number>()
    for (const s of servers) {
      const id = categoryForServer(s).id
      c.set(id, (c.get(id) ?? 0) + 1)
    }
    return ASSET_CATEGORIES.map((cat) => ({ id: cat.id, label: cat.label, count: c.get(cat.id) ?? 0 })).filter(
      (c) => c.count > 0,
    )
  }, [servers])

  if (servers.length === 0 || counts.length === 0) return null
  const total = servers.length

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <h2 className="mb-3 text-sm font-semibold text-foreground">Fleet composition</h2>
      <div className="mb-3 flex h-2.5 overflow-hidden rounded-full bg-muted">
        {counts.map((c) => (
          <div
            key={c.id}
            className={CATEGORY_BAR[c.id]}
            style={{ width: `${(c.count / total) * 100}%` }}
            title={`${c.label}: ${c.count}`}
          />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs text-foreground">
        {counts.map((c) => (
          <div key={c.id} className="flex items-center gap-2">
            <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", CATEGORY_BAR[c.id])} />
            {c.label}, {c.count}
          </div>
        ))}
      </div>
    </div>
  )
}

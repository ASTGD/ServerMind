import { useMemo } from "react"
import type { Server } from "@/types"
import { ASSET_GROUPS, groupFor, type AssetGroupId } from "@/lib/assetGroups"
import { Card } from "@/components/ui"
import { cn } from "@/lib/utils"

const GROUP_BAR: Record<AssetGroupId, string> = {
  server: "bg-indigo-500",
  windows: "bg-sky-500",
}

/** Fleet breakdown by asset group, as a single glanceable color bar + legend
 *  instead of a plain number list — computed client-side from data the Dashboard
 *  already loaded (no new requests). Grade distribution now lives exclusively in
 *  the Fleet health donut, so this panel stays purely about asset type. */
export default function FleetComposition({ servers }: { servers: Server[] }) {
  const counts = useMemo(() => {
    const c = new Map<AssetGroupId, number>()
    for (const s of servers) {
      const id = groupFor(s)
      c.set(id, (c.get(id) ?? 0) + 1)
    }
    return ASSET_GROUPS.map((g) => ({ id: g.id, label: g.label, count: c.get(g.id) ?? 0 })).filter(
      (c) => c.count > 0,
    )
  }, [servers])

  if (servers.length === 0 || counts.length === 0) return null
  const total = servers.length

  return (
    <Card className="p-5">
      <h2 className="mb-3 text-sm font-semibold text-foreground">Fleet composition</h2>
      <div className="mb-3 flex h-2.5 overflow-hidden rounded-full bg-muted">
        {counts.map((c) => (
          <div
            key={c.id}
            className={GROUP_BAR[c.id]}
            style={{ width: `${(c.count / total) * 100}%` }}
            title={`${c.label}: ${c.count}`}
          />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs text-foreground">
        {counts.map((c) => (
          <div key={c.id} className="flex items-center gap-2">
            <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", GROUP_BAR[c.id])} />
            {c.label}, {c.count}
          </div>
        ))}
      </div>
    </Card>
  )
}

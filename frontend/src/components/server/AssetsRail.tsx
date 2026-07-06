import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, LayoutPanelTop, Cloud, Plus, ArrowUpRight } from "lucide-react"
import type { Server } from "@/types"
import type { CloudAccount } from "@/api/cloud"
import { getFleetHealth } from "@/api/fleet"
import { getMyUsage } from "@/api/usage"

interface Props {
  servers: Server[]
  cloudAccounts: CloudAccount[]
  onFilter: (category: string) => void
  onAddHosting: () => void
  onConnectCloud: () => void
}

function isHosting(s: Server) {
  return s.connection_type === "hosting" || Boolean(s.panel_type)
}

/** The Assets companion rail: an at-a-glance fleet pulse, dedicated Hosting and Cloud stat
 *  widgets (with add/connect empty states), and plan usage. Runs on data we already have
 *  (fleet health + usage + the asset lists). */
export default function AssetsRail({ servers, cloudAccounts, onFilter, onAddHosting, onConnectCloud }: Props) {
  const navigate = useNavigate()
  const { data: fleet } = useQuery({ queryKey: ["fleet-health"], queryFn: getFleetHealth, staleTime: 60000 })
  const { data: usage } = useQuery({ queryKey: ["my-usage"], queryFn: getMyUsage })

  const total = servers.length
  const online = servers.filter((s) => s.status === "online").length
  const attention = fleet?.summary.needs_attention ?? 0

  const panels = servers.filter(isHosting).length
  const importedByAccount = new Map<string, number>()
  for (const s of servers) if (s.cloud_account_id) importedByAccount.set(s.cloud_account_id, (importedByAccount.get(s.cloud_account_id) ?? 0) + 1)
  const totalImported = [...importedByAccount.values()].reduce((a, b) => a + b, 0)

  return (
    <aside className="w-80 shrink-0 space-y-5 border-l border-border pl-6">
      {/* Fleet pulse */}
      <div>
        <p className="mb-2.5 text-sm font-medium text-foreground">Fleet pulse</p>
        <div className="grid grid-cols-3 gap-1.5">
          <div className="rounded-lg bg-muted/60 px-2 py-1.5"><p className="text-lg font-semibold text-foreground">{total}</p><p className="text-[11px] text-muted-foreground">Total</p></div>
          <div className="rounded-lg bg-muted/60 px-2 py-1.5"><p className="text-lg font-semibold text-green-600 dark:text-green-500">{online}</p><p className="text-[11px] text-muted-foreground">Online</p></div>
          <div className="rounded-lg bg-muted/60 px-2 py-1.5"><p className={`text-lg font-semibold ${attention > 0 ? "text-red-500" : "text-foreground"}`}>{attention}</p><p className="text-[11px] text-muted-foreground">Attention</p></div>
        </div>
        {attention > 0 && (
          <button onClick={() => navigate("/dashboard")} className="mt-2.5 flex w-full items-center gap-2 rounded-lg bg-amber-500/10 px-2.5 py-2 text-left text-xs text-amber-700 hover:bg-amber-500/20 dark:text-amber-400">
            <AlertTriangle size={14} />
            <span className="flex-1">{attention} {attention === 1 ? "thing needs" : "things need"} attention</span>
            <span className="font-medium">Review</span>
          </button>
        )}
      </div>

      {/* Hosting stat widget */}
      <div className="rounded-xl border border-border p-3.5">
        <div className="mb-2.5 flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-sm font-medium text-foreground"><LayoutPanelTop size={15} className="text-emerald-600 dark:text-emerald-400" /> Hosting</span>
          {panels > 0 && <button onClick={() => onFilter("hosting")} className="text-xs text-primary hover:underline">View</button>}
        </div>
        {panels > 0 ? (
          <div className="text-center">
            <p className="text-2xl font-semibold text-foreground">{panels}</p>
            <p className="text-[11px] text-muted-foreground">{panels === 1 ? "hosting panel" : "hosting panels"}</p>
          </div>
        ) : (
          <div className="py-1 text-center">
            <p className="text-xs font-medium text-foreground">No hosting panel yet</p>
            <button onClick={onAddHosting} className="mt-2 inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-foreground hover:bg-accent"><Plus size={12} /> Add new</button>
          </div>
        )}
      </div>

      {/* Cloud accounts stat widget */}
      <div className="rounded-xl border border-border p-3.5">
        <div className="mb-2.5 flex items-center justify-between">
          <span className="flex items-center gap-1.5 text-sm font-medium text-foreground"><Cloud size={15} className="text-violet-600 dark:text-violet-400" /> Cloud accounts</span>
          {cloudAccounts.length > 0 && <button onClick={() => onFilter("cloud")} className="text-xs text-primary hover:underline">View</button>}
        </div>
        {cloudAccounts.length > 0 ? (
          <div className="flex justify-around text-center">
            <div><p className="text-xl font-semibold text-foreground">{cloudAccounts.length}</p><p className="text-[11px] text-muted-foreground">{cloudAccounts.length === 1 ? "Account" : "Accounts"}</p></div>
            <div><p className="text-xl font-semibold text-foreground">{totalImported}</p><p className="text-[11px] text-muted-foreground">Imported</p></div>
          </div>
        ) : (
          <div className="py-1 text-center">
            <p className="text-xs font-medium text-foreground">No cloud account yet</p>
            <button onClick={onConnectCloud} className="mt-2 inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-foreground hover:bg-accent"><ArrowUpRight size={12} /> Connect</button>
          </div>
        )}
      </div>

      {/* Plan usage */}
      {usage && (
        <div>
          <p className="mb-2 text-sm font-medium text-foreground">Your plan</p>
          <div className="mb-2.5">
            <div className="flex justify-between text-xs"><span className="text-muted-foreground">Servers</span><span className="text-muted-foreground">{usage.servers_used} / {usage.servers_limit}</span></div>
            <div className="mt-1 h-1 rounded bg-muted"><div className="h-full rounded bg-foreground/60" style={{ width: `${Math.min(100, (usage.servers_used / Math.max(1, usage.servers_limit)) * 100)}%` }} /></div>
          </div>
          <div>
            <div className="flex justify-between text-xs"><span className="text-muted-foreground">Ally actions</span><span className="text-muted-foreground">{usage.used} / {usage.limit}</span></div>
            <div className="mt-1 h-1 rounded bg-muted"><div className="h-full rounded bg-foreground/60" style={{ width: `${Math.min(100, (usage.used / Math.max(1, usage.limit)) * 100)}%` }} /></div>
          </div>
        </div>
      )}
    </aside>
  )
}

import { useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, LayoutPanelTop, Cloud, Plus, ArrowUpRight, ChevronRight } from "lucide-react"
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

/** The Assets companion rail — same card language as the Dashboard sidebar
 *  (rounded-xl / border / bg-card / p-5 cards, semibold headings, tabular
 *  numbers, primary progress bars). At-a-glance fleet pulse, dedicated Hosting
 *  and Cloud stat cards (with add/connect empty states), and plan usage. Runs on
 *  data we already have (fleet health + usage + the asset lists). */
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

  const pct = (used: number, limit: number) => Math.min(100, (used / Math.max(1, limit)) * 100)

  return (
    <aside className="w-80 shrink-0 space-y-5">
      {/* Fleet pulse */}
      <div className="rounded-xl border border-border bg-card p-5">
        <h2 className="text-sm font-semibold text-foreground">Fleet pulse</h2>
        <div className="mt-4 grid grid-cols-3 gap-3 text-center">
          <div>
            <p className="text-2xl font-semibold tabular-nums text-foreground">{total}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">Total</p>
          </div>
          <div>
            <p className="text-2xl font-semibold tabular-nums text-green-600 dark:text-green-500">{online}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">Online</p>
          </div>
          <div>
            <p className={`text-2xl font-semibold tabular-nums ${attention > 0 ? "text-amber-500" : "text-foreground"}`}>{attention}</p>
            <p className="mt-0.5 text-xs text-muted-foreground">Attention</p>
          </div>
        </div>
        {attention > 0 && (
          <button
            onClick={() => navigate("/dashboard")}
            className="group mt-4 flex w-full items-center gap-2 rounded-lg bg-amber-500/10 px-3 py-2 text-left text-xs text-amber-700 transition-colors hover:bg-amber-500/15 dark:text-amber-400"
          >
            <AlertTriangle size={14} className="shrink-0" />
            <span className="flex-1">{attention} {attention === 1 ? "thing needs" : "things need"} attention</span>
            <ChevronRight size={14} className="text-amber-700/50 group-hover:text-amber-700 dark:text-amber-400/50 dark:group-hover:text-amber-400" />
          </button>
        )}
      </div>

      {/* Hosting */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <span className="flex h-6 w-6 items-center justify-center rounded-md bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"><LayoutPanelTop size={14} /></span>
            Hosting
          </h2>
          {panels > 0 && <button onClick={() => onFilter("hosting")} className="text-xs text-muted-foreground hover:text-foreground">View</button>}
        </div>
        {panels > 0 ? (
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-2xl font-semibold tabular-nums text-foreground">{panels}</span>
            <span className="text-xs text-muted-foreground">{panels === 1 ? "hosting panel" : "hosting panels"}</span>
          </div>
        ) : (
          <div className="mt-3">
            <p className="text-xs text-muted-foreground">No hosting panel yet</p>
            <button onClick={onAddHosting} className="mt-2.5 flex w-full items-center justify-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-muted/60"><Plus size={13} /> Add new</button>
          </div>
        )}
      </div>

      {/* Cloud accounts */}
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <span className="flex h-6 w-6 items-center justify-center rounded-md bg-violet-500/10 text-violet-600 dark:text-violet-400"><Cloud size={14} /></span>
            Cloud accounts
          </h2>
          {cloudAccounts.length > 0 && <button onClick={() => onFilter("cloud")} className="text-xs text-muted-foreground hover:text-foreground">View</button>}
        </div>
        {cloudAccounts.length > 0 ? (
          <div className="mt-4 flex gap-8">
            <div>
              <p className="text-2xl font-semibold tabular-nums text-foreground">{cloudAccounts.length}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">{cloudAccounts.length === 1 ? "Account" : "Accounts"}</p>
            </div>
            <div>
              <p className="text-2xl font-semibold tabular-nums text-foreground">{totalImported}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">Imported</p>
            </div>
          </div>
        ) : (
          <div className="mt-3">
            <p className="text-xs text-muted-foreground">No cloud account yet</p>
            <button onClick={onConnectCloud} className="mt-2.5 flex w-full items-center justify-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-muted/60"><ArrowUpRight size={13} /> Connect</button>
          </div>
        )}
      </div>

      {/* Your plan */}
      {usage && (
        <div className="rounded-xl border border-border bg-card p-5">
          <h2 className="text-sm font-semibold text-foreground">Your plan</h2>
          <div className="mt-4 space-y-3">
            <div>
              <div className="mb-1 flex justify-between text-xs"><span className="text-foreground">Servers</span><span className="tabular-nums text-muted-foreground">{usage.servers_used} / {usage.servers_limit}</span></div>
              <div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary/70" style={{ width: `${pct(usage.servers_used, usage.servers_limit)}%` }} /></div>
            </div>
            <div>
              <div className="mb-1 flex justify-between text-xs"><span className="text-foreground">Ally actions</span><span className="tabular-nums text-muted-foreground">{usage.used} / {usage.limit}</span></div>
              <div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary/70" style={{ width: `${pct(usage.used, usage.limit)}%` }} /></div>
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}

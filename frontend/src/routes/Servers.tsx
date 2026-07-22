import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Plus, ServerOff } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
import { listServers } from "@/api/servers"
import { listCloudAccounts, type CloudAccount } from "@/api/cloud"
import { ASSET_CATEGORIES, categoryForServer } from "@/lib/assetCategories"
import { useAssistantStore } from "@/store/assistantStore"
import MachineCard from "@/components/server/MachineCard"
import HostingCard from "@/components/server/HostingCard"
import CloudAccountCard from "@/components/server/CloudAccountCard"
import AssetsRail from "@/components/server/AssetsRail"
import AddServerModal from "@/components/server/AddServerModal"
import ConnectCloudModal from "@/components/server/ConnectCloudModal"
import RdpDesktopModal from "@/components/server/RdpDesktopModal"
import CloudAccountModal from "@/components/server/CloudAccountModal"
import { Button, EmptyState } from "@/components/ui"
import type { Server } from "@/types"

export default function Servers() {
  const { t } = useTranslation()
  const [showAdd, setShowAdd] = useState(false)
  const [showCloud, setShowCloud] = useState(false)
  const [desktopServer, setDesktopServer] = useState<Server | null>(null)
  const [manageAccount, setManageAccount] = useState<CloudAccount | null>(null)
  const [filter, setFilter] = useState<string>("all")

  const { data: servers = [], isLoading } = useQuery<Server[]>({ queryKey: ["servers"], queryFn: listServers })
  const { data: cloudAccounts = [] } = useQuery<CloudAccount[]>({ queryKey: ["cloud-accounts"], queryFn: listCloudAccounts })
  // The Ally drawer overlays (fixed position) rather than shrinking this column's actual
  // box, so the "fits 3 not 4" cap has to be driven by JS state, not a CSS breakpoint alone.
  const drawerOpen = useAssistantStore((s) => s.open)
  // 1600px is where 4 columns first measures out bigger than the old 220px card floor
  // (this column's real width, net of the nav + the 320px asset rail, is viewport-647px;
  // 4 cards + 3 gaps needs >=928px of that, i.e. a >=1575px viewport — 1600 clears it with
  // margin). Below that, 3 columns already beats the old floor from 1024px up.
  const gridCols = drawerOpen
    ? "grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3"
    : "grid gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 min-[1600px]:grid-cols-4"

  // Group assets by category (imported cloud instances land in vps/windows; hosting has its own).
  const byCat: Record<string, Server[]> = {}
  for (const s of servers) (byCat[categoryForServer(s).id] ??= []).push(s)
  const importedFor = (id: string) => servers.filter((s) => s.cloud_account_id === id).length

  // Filter pills: only categories that have something (cloud counts its accounts).
  const pills = ASSET_CATEGORIES.map((c) => ({
    id: c.id,
    label: c.label,
    count: c.id === "cloud" ? cloudAccounts.length : (byCat[c.id]?.length ?? 0),
  })).filter((p) => p.count > 0)

  const empty = servers.length === 0 && cloudAccounts.length === 0
  const visible = (id: string) => filter === "all" || filter === id

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-h1 text-foreground">{t("nav.servers")}</h1>
        <Button onClick={() => setShowAdd(true)}>
          <Plus size={15} />
          {t("servers.add")}
        </Button>
      </div>

      {isLoading ? (
        <div className={gridCols}>
          {[...Array(4)].map((_, i) => <div key={i} className="aspect-square animate-pulse rounded-2xl border border-border bg-card" />)}
        </div>
      ) : empty ? (
        <EmptyState
          icon={ServerOff}
          title="No assets yet"
          description="Add your first server, hosting panel, or cloud account to manage it with AI."
          className="py-20"
          action={
            <Button onClick={() => setShowAdd(true)}>
              <Plus size={14} /> {t("servers.add")}
            </Button>
          }
        />
      ) : (
        <>
          {/* Filter pills — hoisted above the two-column split so both columns start flush */}
          {pills.length > 1 && (
            <div className="flex flex-wrap gap-2">
              <FilterPill label="All" active={filter === "all"} onClick={() => setFilter("all")} />
              {pills.map((p) => (
                <FilterPill key={p.id} label={p.label} count={p.count} active={filter === p.id} onClick={() => setFilter(p.id)} />
              ))}
            </div>
          )}

          <div className="flex gap-6">
            <div className="min-w-0 flex-1 space-y-7">
              {/* Sections in category order */}
              {ASSET_CATEGORIES.map((cat) => {
                if (!visible(cat.id)) return null
                const Icon = cat.icon

                if (cat.id === "cloud") {
                  if (cloudAccounts.length === 0) return null
                  return (
                    <section key="cloud">
                      <SectionHeader Icon={Icon} label="Cloud accounts" count={cloudAccounts.length} accent={cat.accent} />
                      <div className={gridCols}>
                        {cloudAccounts.map((a) => (
                          <CloudAccountCard key={a.id} account={a} importedCount={importedFor(a.id)} onManage={setManageAccount} />
                        ))}
                      </div>
                    </section>
                  )
                }

                const list = byCat[cat.id]
                if (!list?.length) return null
                return (
                  <section key={cat.id}>
                    <SectionHeader Icon={Icon} label={cat.label} count={list.length} accent={cat.accent} />
                    <div className={gridCols}>
                      {list.map((s) =>
                        cat.id === "hosting"
                          ? <HostingCard key={s.id} server={s} />
                          : <MachineCard key={s.id} server={s} onOpenDesktop={setDesktopServer} />,
                      )}
                    </div>
                  </section>
                )
              })}
            </div>

            <div className="hidden xl:block">
              <AssetsRail
                servers={servers}
                cloudAccounts={cloudAccounts}
                onFilter={setFilter}
                onAddHosting={() => setShowAdd(true)}
                onConnectCloud={() => setShowCloud(true)}
              />
            </div>
          </div>
        </>
      )}

      {showAdd && <AddServerModal onClose={() => setShowAdd(false)} onPickCloud={() => { setShowAdd(false); setShowCloud(true) }} />}
      {showCloud && <ConnectCloudModal onClose={() => setShowCloud(false)} />}
      {desktopServer && <RdpDesktopModal server={desktopServer} onClose={() => setDesktopServer(null)} />}
      {manageAccount && <CloudAccountModal account={manageAccount} onClose={() => setManageAccount(null)} />}
    </div>
  )
}

function FilterPill({ label, count, active, onClick }: { label: string; count?: number; active: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-sm transition-colors ${active ? "bg-primary text-primary-foreground" : "border border-border text-muted-foreground hover:bg-accent hover:text-foreground"}`}
    >
      {label}{count !== undefined && <span className={active ? "ml-1.5 opacity-80" : "ml-1.5 text-muted-foreground"}>{count}</span>}
    </button>
  )
}

function SectionHeader({ Icon, label, count, accent }: { Icon: LucideIcon; label: string; count: number; accent: string }) {
  return (
    <div className="mb-3 flex items-center gap-2.5">
      <div className={`flex h-7 w-7 items-center justify-center rounded-md ${accent}`}>
        <Icon size={15} />
      </div>
      <span className="text-sm font-semibold text-foreground">{label}</span>
      <span className="rounded-full bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{count}</span>
    </div>
  )
}

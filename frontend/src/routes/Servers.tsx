import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Cloud, Plus, Search, ServerOff } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { useTranslation } from "react-i18next"
import { listServers } from "@/api/servers"
import { listCloudAccounts, type CloudAccount } from "@/api/cloud"
import { listSites } from "@/api/sites"
import { getFleetHealth } from "@/api/fleet"
import { ASSET_GROUPS, availableFilters, filterById, groupFor } from "@/lib/assetGroups"
import AssetRow from "@/components/server/AssetRow"
import CloudAccountRow from "@/components/server/CloudAccountRow"
import AddServerModal from "@/components/server/AddServerModal"
import ConnectCloudModal from "@/components/server/ConnectCloudModal"
import RdpDesktopModal from "@/components/server/RdpDesktopModal"
import CloudAccountModal from "@/components/server/CloudAccountModal"
import { Button, EmptyState } from "@/components/ui"
import { cn } from "@/lib/utils"
import type { Server } from "@/types"

/**
 * Assets — everything you manage, as one grouped list.
 *
 * A list rather than a grid of cards because the question this page answers is "is anything
 * wrong, and where", and that is a scanning job: one line per asset, the same fields in the
 * same column every time. Cards make the eye re-find each fact in a new place.
 *
 * The summary numbers that used to live in a right-hand rail sit under the title instead. A
 * rail spends a whole column of width to say three numbers, and it squeezed the list into
 * less room than the rows need.
 */
export default function Servers() {
  const { t } = useTranslation()
  const [showAdd, setShowAdd] = useState(false)
  const [showCloud, setShowCloud] = useState(false)
  const [desktopServer, setDesktopServer] = useState<Server | null>(null)
  const [manageAccount, setManageAccount] = useState<CloudAccount | null>(null)
  const [filter, setFilter] = useState<string>("all")
  const [q, setQ] = useState("")

  const { data: servers = [], isLoading } = useQuery<Server[]>({
    queryKey: ["servers"], queryFn: listServers,
  })
  const { data: cloudAccounts = [] } = useQuery<CloudAccount[]>({
    queryKey: ["cloud-accounts"], queryFn: listCloudAccounts,
  })
  // Both of these are already fetched elsewhere in the app under the same query keys, so
  // joining health grades and site counts here costs the API nothing new.
  const { data: fleet } = useQuery({ queryKey: ["fleet-health"], queryFn: getFleetHealth })
  const { data: siteData } = useQuery({
    queryKey: ["sites", "", false], queryFn: () => listSites({}),
  })

  const gradeFor = useMemo(() => {
    const m: Record<string, string> = {}
    for (const s of fleet?.servers ?? []) m[s.server_id] = s.grade
    return m
  }, [fleet])

  const sitesFor = useMemo(() => {
    const m: Record<string, number> = {}
    for (const s of siteData?.sites ?? []) {
      if (s.server_id) m[s.server_id] = (m[s.server_id] ?? 0) + 1
    }
    return m
  }, [siteData])

  // Where each asset lives is DERIVED (see lib/assetGroups) — a stored column would go stale
  // the day somebody installs a panel by hand.
  const byGroup: Record<string, Server[]> = {}
  for (const s of servers) (byGroup[groupFor(s)] ??= []).push(s)
  const importedFor = (id: string) => servers.filter((s) => s.cloud_account_id === id).length

  // Filters slice ACROSS the groups rather than replacing them, so a filtered view still
  // says where each result lives. One with nothing to show is absent, not disabled.
  const filters = availableFilters(servers)

  const empty = servers.length === 0 && cloudAccounts.length === 0

  // Search matches name OR address, because someone chasing an alert usually has the IP.
  const needle = q.trim().toLowerCase()
  // A filter whose last match has gone is no longer offered, so honour it only while it is
  // still on the row — otherwise the pill vanishes with the filter still applied and there
  // is nothing left to click to get back.
  const active = filters.some((f) => f.filter.id === filter) ? filterById(filter) : undefined
  const filterId = active ? filter : "all"
  const matches = (s: Server) => (!active || active.match(s))
    && (!needle
      || s.name.toLowerCase().includes(needle)
      || s.host.toLowerCase().includes(needle)
      || (s.panel_type ?? "").toLowerCase().includes(needle)
      || (s.os_type ?? "").toLowerCase().includes(needle))

  const online = servers.filter((s) => s.status === "online").length
  const attention = servers.filter(
    (s) => s.status === "auth_failed" || s.status === "host_changed" || s.status === "offline",
  ).length

  // A cloud ACCOUNT is not an asset, so no asset filter can describe one — while a filter is
  // on, showing the accounts anyway would be answering a question nobody asked.
  const shownAccounts = active ? [] : cloudAccounts.filter(
    (a) => !needle
      || a.label.toLowerCase().includes(needle)
      || a.provider.toLowerCase().includes(needle))
  const anyShown = shownAccounts.length > 0
    || ASSET_GROUPS.some((g) => (byGroup[g.id] ?? []).some(matches))

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-h1 text-foreground">{t("nav.servers")}</h1>
          {!empty && (
            <p className="mt-1 text-sm text-muted-foreground">
              {servers.length} asset{servers.length === 1 ? "" : "s"}
              {" · "}
              <span className="text-emerald-600 dark:text-emerald-400">{online} online</span>
              {attention > 0 && (
                <>
                  {" · "}
                  <span className="text-red-600 dark:text-red-400">{attention} need attention</span>
                </>
              )}
              {cloudAccounts.length > 0
                && ` · ${cloudAccounts.length} cloud account${cloudAccounts.length === 1 ? "" : "s"}`}
            </p>
          )}
        </div>
        <Button onClick={() => setShowAdd(true)}>
          <Plus size={15} />
          {t("servers.add")}
        </Button>
      </div>

      {isLoading ? (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-[57px] animate-pulse border-t border-border first:border-t-0" />
          ))}
        </div>
      ) : empty ? (
        <EmptyState
          icon={ServerOff}
          title="No assets yet"
          description="Add your first server or cloud account to manage it with AI."
          className="py-20"
          action={
            <Button onClick={() => setShowAdd(true)}>
              <Plus size={14} /> {t("servers.add")}
            </Button>
          }
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            {filters.length > 0 && (
              <>
                <FilterPill label="All" count={servers.length}
                  active={filterId === "all"} onClick={() => setFilter("all")} />
                {filters.map(({ filter: f, count }) => (
                  <FilterPill key={f.id} label={f.label} count={count}
                    active={filterId === f.id} onClick={() => setFilter(f.id)} />
                ))}
              </>
            )}
            <div className="relative ml-auto min-w-[200px] flex-1 sm:max-w-xs sm:flex-none">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                value={q} onChange={(e) => setQ(e.target.value)}
                placeholder="Search by name or address"
                className="w-full rounded-lg border border-border bg-background py-1.5 pl-8 pr-3 text-sm outline-none focus:border-primary"
              />
            </div>
          </div>

          <div className="space-y-5">
            {ASSET_GROUPS.map((group) => {
              const list = (byGroup[group.id] ?? []).filter(matches)
              if (!list.length) return null
              return (
                <section key={group.id}>
                  <SectionHeader Icon={group.icon} label={group.label}
                    count={list.length} accent={group.accent} />
                  <div className="overflow-hidden rounded-xl border border-border bg-card">
                    {list.map((s) => (
                      <AssetRow key={s.id} server={s}
                        grade={gradeFor[s.id]} sites={sitesFor[s.id]}
                        onOpenDesktop={setDesktopServer} />
                    ))}
                  </div>
                </section>
              )
            })}

            {shownAccounts.length > 0 && (
              <section key="cloud">
                <SectionHeader Icon={Cloud} label="Cloud accounts"
                  count={shownAccounts.length}
                  accent="bg-violet-500/10 text-violet-600 dark:text-violet-400" />
                <div className="overflow-hidden rounded-xl border border-border bg-card">
                  {shownAccounts.map((a) => (
                    <CloudAccountRow key={a.id} account={a}
                      importedCount={importedFor(a.id)} onManage={setManageAccount} />
                  ))}
                </div>
              </section>
            )}

            {!anyShown && (
              // Says which of the two narrowed it down, because "nothing matches" with an
              // empty search box reads as the page being broken.
              <p className="py-10 text-center text-sm text-muted-foreground">
                {active
                  ? <>Nothing under <b>{active.label}</b> matches “{q}”.</>
                  : <>Nothing matches “{q}”.</>}
              </p>
            )}
          </div>
        </>
      )}

      {showAdd && (
        <AddServerModal
          onClose={() => setShowAdd(false)}
          onPickCloud={() => { setShowAdd(false); setShowCloud(true) }}
        />
      )}
      {showCloud && <ConnectCloudModal onClose={() => setShowCloud(false)} />}
      {desktopServer && <RdpDesktopModal server={desktopServer} onClose={() => setDesktopServer(null)} />}
      {manageAccount && <CloudAccountModal account={manageAccount} onClose={() => setManageAccount(null)} />}
    </div>
  )
}

function FilterPill({ label, count, active, onClick }: {
  label: string; count?: number; active: boolean; onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "rounded-full px-3 py-1 text-sm transition-colors",
        active
          ? "bg-primary text-primary-foreground"
          : "border border-border text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
    >
      {label}
      {count !== undefined && (
        <span className={active ? "ml-1.5 opacity-80" : "ml-1.5 text-muted-foreground"}>{count}</span>
      )}
    </button>
  )
}

function SectionHeader({ Icon, label, count, accent }: {
  Icon: LucideIcon; label: string; count: number; accent: string
}) {
  return (
    <div className="mb-2 flex items-center gap-2.5">
      <div className={cn("flex h-6 w-6 items-center justify-center rounded-md", accent)}>
        <Icon size={13} />
      </div>
      <span className="text-sm font-semibold text-foreground">{label}</span>
      <span className="rounded-full bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">{count}</span>
    </div>
  )
}

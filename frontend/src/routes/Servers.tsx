import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Plus, ServerOff } from "lucide-react"
import { useTranslation } from "react-i18next"
import { listServers } from "@/api/servers"
import ServerCard from "@/components/server/ServerCard"
import AddServerModal from "@/components/server/AddServerModal"
import ConnectCloudModal from "@/components/server/ConnectCloudModal"
import type { Server } from "@/types"

export default function Servers() {
  const { t } = useTranslation()
  const [showAdd, setShowAdd] = useState(false)
  const [showCloud, setShowCloud] = useState(false)

  const { data: servers = [], isLoading } = useQuery<Server[]>({
    queryKey: ["servers"],
    queryFn: listServers,
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">{t("nav.servers")}</h1>
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          <Plus size={15} />
          {t("servers.add")}
        </button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-lg border border-border bg-card" />
          ))}
        </div>
      ) : servers.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-20 text-center">
          <ServerOff size={36} className="mb-4 text-muted-foreground/50" />
          <p className="font-medium text-foreground">No servers yet</p>
          <p className="mt-1 text-sm text-muted-foreground">
            Add your first server to start managing it with AI.
          </p>
          <button
            onClick={() => setShowAdd(true)}
            className="mt-5 flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <Plus size={14} />
            {t("servers.add")}
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {servers.map((server) => (
            <ServerCard key={server.id} server={server} />
          ))}
        </div>
      )}

      {showAdd && (
        <AddServerModal
          onClose={() => setShowAdd(false)}
          onPickCloud={() => {
            setShowAdd(false)
            setShowCloud(true)
          }}
        />
      )}
      {showCloud && <ConnectCloudModal onClose={() => setShowCloud(false)} />}
    </div>
  )
}

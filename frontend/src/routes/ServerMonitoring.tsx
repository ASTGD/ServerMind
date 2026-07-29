import { useOutletContext } from "react-router-dom"
import { Activity } from "lucide-react"
import ServerMetrics from "@/components/server/ServerMetrics"
import type { Server } from "@/types"

/**
 * How this server has been behaving.
 *
 * Deliberately renders the same `ServerMetrics` the Overview uses rather than a second
 * implementation — the difference is the room. On Overview it sits in a narrow column
 * where the history charts are barely readable; here it gets the full width, which is the
 * whole reason to open a monitoring section at all.
 */
export default function ServerMonitoring() {
  const { server } = useOutletContext<{ server: Server }>()

  return (
    <div className="space-y-4">
      <div>
        <h2 className="flex items-center gap-2 text-[17px] font-medium text-foreground">
          <Activity size={16} className="text-primary" /> Monitoring
        </h2>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Live load, history, and the alerts that tell you when it changes.
        </p>
      </div>
      <ServerMetrics serverId={server.id} />
    </div>
  )
}

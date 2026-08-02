import { useOutletContext } from "react-router-dom"
import { Activity } from "lucide-react"
import ServerMetrics from "@/components/server/ServerMetrics"
import UptimePanel from "@/components/monitoring/UptimePanel"
import type { Server } from "@/types"

/**
 * How this server has been behaving.
 *
 * Deliberately renders the same `ServerMetrics` the Overview uses rather than a second
 * implementation — the difference is the room. On Overview it sits in a narrow column
 * where the history charts are barely readable; here it gets the full width, which is the
 * whole reason to open a monitoring section at all.
 *
 * The uptime checks live here too. They used to be on Overview only, and Overview is
 * dropped once a server has Sites — on the grounds that everything on it duplicates
 * another section. That was true of the metrics, the services and the installed list, and
 * NOT true of this: it is the only place a check can be seen, edited or removed. So on the
 * ordinary case — a Linux server with websites — a check could be created and then never
 * reached again, which is how a check for a deleted site ends up running forever.
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
      <UptimePanel serverId={server.id} />
    </div>
  )
}

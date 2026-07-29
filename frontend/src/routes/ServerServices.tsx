import { useOutletContext } from "react-router-dom"
import { HeartPulse } from "lucide-react"
import ServicesPanel from "@/components/monitoring/ServicesPanel"
import type { Server } from "@/types"

/**
 * The services this server runs, and what happens when one stops.
 *
 * A server can sit at 5% CPU with its database dead — uptime checks only catch that if it
 * takes a website down with it. This is the section that notices a cache, a queue worker or
 * a mail daemon going away.
 */
export default function ServerServices() {
  const { server } = useOutletContext<{ server: Server }>()

  return (
    <div className="space-y-4">
      <div>
        <h2 className="flex items-center gap-2 text-[17px] font-medium text-foreground">
          <HeartPulse size={16} className="text-primary" /> Services
        </h2>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Watch a service and get told when it stops — optionally restarting it, within a
          limit so a service that keeps crashing escalates instead of being hammered.
        </p>
      </div>
      <ServicesPanel serverId={server.id} />
    </div>
  )
}

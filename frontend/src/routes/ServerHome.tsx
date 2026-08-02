import { Navigate, useOutletContext } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { getServerRole } from "@/api/servers"
import ServerRoleCard from "@/components/server/ServerRoleCard"
import ServerOverview from "./ServerOverview"
import type { Server } from "@/types"

/**
 * What you land on when you open an asset.
 *
 * For a Linux server this page exists **once**, on a clean machine, and asks the only
 * question that decides everything else: is ServerAlly the control panel here, or are we
 * installing a real one and watching it? Once that is answered the page is finished — it
 * leaves the menu, and the server's home becomes Sites.
 *
 * It deliberately carries nothing else. Specs, installed software, metrics and the rest all
 * have their own sections, and a fresh server has nothing to say about most of them anyway;
 * putting them here made the decision share a page with a stale summary of a machine that
 * has not been set up yet.
 *
 * An asset that cannot host — Windows, Remote Desktop, a hosting account — never faces the
 * question, and Overview is the only page it has, so it keeps the full one.
 */
export default function ServerHome() {
  const { server } = useOutletContext<{ server: Server }>()

  const { data, isLoading } = useQuery({
    queryKey: ["server-role", server.id],
    queryFn: () => getServerRole(server.id),
    enabled: server.connection_type === "ssh",
  })

  if (server.connection_type !== "ssh") return <ServerOverview />

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-16 text-muted-foreground">
        <Loader2 size={16} className="animate-spin" /> Loading…
      </div>
    )
  }

  // Decided. Nothing left to ask, so this page steps aside rather than showing a summary of
  // pages that are one click away in the menu.
  if (data?.applies && data.role !== "undecided") return <Navigate to="sites" replace />

  return <ServerRoleCard server={server} />
}

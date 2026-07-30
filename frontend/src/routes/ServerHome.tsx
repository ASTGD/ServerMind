import { Navigate, useOutletContext } from "react-router-dom"
import ServerOverview from "./ServerOverview"
import { homePathFor } from "@/lib/assetMenu"
import type { Server } from "@/types"

/**
 * What you land on when you open an asset.
 *
 * A server exists to serve something, so anything that CAN host lands on Sites. An asset
 * that cannot — a Windows box, a Remote Desktop machine — lands on Overview, which is the
 * only page it has. One canonical URL either way: the redirect means a Linux server's home
 * is always /sites rather than two addresses showing the same thing.
 */
export default function ServerHome() {
  const ctx = useOutletContext<{ server: Server }>()
  if (homePathFor(ctx.server) === "sites") return <Navigate to="sites" replace />
  return <ServerOverview />
}

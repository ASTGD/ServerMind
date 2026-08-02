import { useEffect, useState } from "react"
import { useParams, Link, Outlet } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle, KeyRound, Loader2, Monitor, Sparkles, Terminal as TerminalIcon,
} from "lucide-react"
import { getServer, getServerRole, trustKey } from "@/api/servers"
import AssetSidebar from "@/components/server/AssetSidebar"
import UpdateCredentialsModal from "@/components/server/UpdateCredentialsModal"
import RdpDesktopModal from "@/components/server/RdpDesktopModal"
import { actionsFor } from "@/lib/assetMenu"
import { useAssistantStore } from "@/store/assistantStore"
import { useTerminalStore } from "@/store/terminalStore"
import type { Server } from "@/types"

/**
 * The asset hub — a shell wrapping every section of one asset.
 *
 * The sections used to be a horizontal tab strip, which caps how many there can be before it
 * scrolls sideways and hides its own contents. A vertical menu has room to grow, and it puts
 * the asset's identity and facts beside its sections instead of above them.
 *
 * Which sections appear is decided by `menuFor`, from what the asset can actually do. The
 * outlet context is unchanged, so every child page keeps working exactly as before.
 */
export default function ServerDetail() {
  const { id } = useParams<{ id: string }>()
  const qc = useQueryClient()
  const [showCreds, setShowCreds] = useState(false)
  const [showDesktop, setShowDesktop] = useState(false)
  const openServer = useAssistantStore((s) => s.openServer)
  const openTerminal = useTerminalStore((s) => s.openSession)

  const { data: server, isLoading } = useQuery<Server>({
    queryKey: ["server", id],
    queryFn: () => getServer(id!),
    enabled: !!id,
  })

  // The Start-here look records a panel it finds on the machine (see the role endpoint).
  // When it does, the server object in hand is a moment out of date — and it is the one
  // the menu, the site form and the guards all read — so it is refetched rather than left
  // disagreeing with the page beside it.
  const { data: role } = useQuery({
    queryKey: ["server-role", id],
    queryFn: () => getServerRole(id!),
    enabled: !!id && server?.connection_type === "ssh",
  })
  useEffect(() => {
    if (role?.panel && server && !server.panel_type) {
      qc.invalidateQueries({ queryKey: ["server", id] })
    }
  }, [role?.panel, server, id, qc])

  const trustMutation = useMutation({
    mutationFn: () => trustKey(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["server", id] })
      qc.invalidateQueries({ queryKey: ["servers"] })
    },
  })

  // Open the global assistant scoped to this asset, optionally seeded with a prompt
  // (e.g. the terminal's "Hand to Ally"). The window itself lives in the app shell.
  function openAI(seedText?: string) {
    if (server) openServer(server, seedText)
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 py-16 text-muted-foreground">
        <Loader2 size={16} className="animate-spin" /> Loading…
      </div>
    )
  }
  if (!server) {
    return (
      <div className="py-16 text-center">
        <p className="text-muted-foreground">This asset could not be loaded.</p>
        <Link to="/servers" className="text-primary hover:underline">Back to assets</Link>
      </div>
    )
  }

  const actions = actionsFor(server)

  return (
    <div className="space-y-4">
      {/* No breadcrumb here: the top bar already derives one from the URL, and the
          sidebar carries "All assets". A third trail would be clutter, not orientation. */}
      <div className="flex items-center justify-end gap-2">
          {actions.desktop && (
            <button
              onClick={() => setShowDesktop(true)}
              title="Open the Windows desktop over RDP"
              className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
            >
              <Monitor size={14} /> Open desktop
            </button>
          )}
          {actions.terminal && (
            <button
              onClick={() => openTerminal(server)}
              title="Open a terminal for this asset"
              className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-accent"
            >
              <TerminalIcon size={14} /> Terminal
            </button>
          )}
          {actions.ally && (
            <button
              onClick={() => openServer(server)}
              title="Ask Ally about this asset"
              className="flex items-center gap-1.5 rounded-md border border-primary/50 px-3 py-1.5 text-sm font-medium text-primary transition-colors hover:bg-primary/10"
            >
              <Sparkles size={14} /> Ask Ally
            </button>
          )}
      </div>

      {/* Anything blocking every section belongs above the split, not inside one of them. */}
      {server.status === "auth_failed" && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3">
          <div className="flex items-start gap-2">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-500" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-foreground">Login is being rejected</p>
              <p className="mt-1 text-sm text-muted-foreground">
                This server is refusing the saved login — most likely its password changed. Update it
                under Credentials. If you also rebuilt or reinstalled the server, you’ll be asked to
                trust its new identity right after.
              </p>
              <button
                onClick={() => setShowCreds(true)}
                className="mt-3 flex items-center gap-2 rounded-md bg-amber-500/90 px-4 py-1.5 text-sm font-medium text-white hover:bg-amber-500"
              >
                <KeyRound size={13} /> Update credentials
              </button>
            </div>
          </div>
        </div>
      )}

      {server.status === "host_changed" && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3">
          <div className="flex items-start gap-2">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-red-500" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-foreground">Server identity changed</p>
              <p className="mt-1 text-sm text-muted-foreground">
                This server’s SSH host key no longer matches the one ServerAlly trusted on first
                connect, so connections are blocked. If you rebuilt or replaced this server that’s
                expected — trust the new key. If you didn’t, the connection may be intercepted; do
                not trust it and investigate.
              </p>
              <button
                onClick={() => trustMutation.mutate()}
                disabled={trustMutation.isPending}
                className="mt-3 flex items-center gap-2 rounded-md bg-red-500/90 px-4 py-1.5 text-sm font-medium text-white hover:bg-red-500 disabled:opacity-50"
              >
                {trustMutation.isPending && <Loader2 size={13} className="animate-spin" />}
                Trust new key
              </button>
              {trustMutation.data && (
                <p className="mt-2 text-xs text-muted-foreground">
                  {trustMutation.data.ok
                    ? "New key trusted — reconnected successfully."
                    : `Couldn’t reconnect: ${trustMutation.data.error ?? "unknown error"}`}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-4 md:flex-row md:items-start">
        <AssetSidebar server={server} />
        <div className="min-w-0 flex-1">
          <Outlet context={{ server, openAI }} />
        </div>
      </div>

      {showCreds && <UpdateCredentialsModal server={server} onClose={() => setShowCreds(false)} />}
      {showDesktop && <RdpDesktopModal server={server} onClose={() => setShowDesktop(false)} />}
    </div>
  )
}

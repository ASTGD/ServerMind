import { useState } from "react"
import { useParams, useNavigate, Link, NavLink } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { ChevronLeft, Loader2, MessageSquare, AlertTriangle, KeyRound } from "lucide-react"
import { getServer, deleteServer, testConnection, detectOs, trustKey } from "@/api/servers"
import ConnectionStatus from "@/components/server/ConnectionStatus"
import ServerMetrics from "@/components/server/ServerMetrics"
import UpdateCredentialsModal from "@/components/server/UpdateCredentialsModal"
import EditServerModal from "@/components/server/EditServerModal"
import ServerActionsMenu from "@/components/server/ServerActionsMenu"
import InstalledWidget from "@/components/server/widgets/InstalledWidget"
import SecurityWidget from "@/components/server/widgets/SecurityWidget"
import BackupsWidget from "@/components/server/widgets/BackupsWidget"
import RecentActivityWidget from "@/components/server/widgets/RecentActivityWidget"
import type { Server } from "@/types"

export default function ServerDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [showCreds, setShowCreds] = useState(false)
  const [showEdit, setShowEdit] = useState(false)

  const { data: server, isLoading } = useQuery<Server>({
    queryKey: ["server", id],
    queryFn: () => getServer(id!),
    enabled: !!id,
  })

  const testMutation = useMutation({
    mutationFn: () => testConnection(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["server", id] }),
  })
  const detectMutation = useMutation({
    mutationFn: () => detectOs(id!),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["server", id] }),
  })
  const deleteMutation = useMutation({
    mutationFn: () => deleteServer(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["servers"] })
      navigate("/servers", { replace: true })
    },
  })
  const trustMutation = useMutation({
    mutationFn: () => trustKey(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["server", id] })
      qc.invalidateQueries({ queryKey: ["servers"] })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-muted-foreground">
        <Loader2 size={20} className="animate-spin" />
      </div>
    )
  }

  if (!server) {
    return (
      <div className="py-20 text-center text-muted-foreground">
        Server not found.{" "}
        <Link to="/servers" className="text-primary hover:underline">
          Back to servers
        </Link>
      </div>
    )
  }

  const tabs = [
    { to: `/servers/${server.id}`, label: "Overview", end: true },
    { to: `/servers/${server.id}/terminal`, label: "Terminal", end: false },
    { to: `/servers/${server.id}/files`, label: "Files", end: false },
    { to: `/servers/${server.id}/monitoring`, label: "Monitoring", end: false },
    { to: `/servers/${server.id}/security`, label: "Security", end: false },
    { to: `/servers/${server.id}/backups`, label: "Backups", end: false },
    { to: `/servers/${server.id}/scheduler`, label: "Scheduler", end: false },
    ...(server.connection_type === "hosting"
      ? [{ to: `/servers/${server.id}/hosting`, label: "Hosting", end: false }]
      : []),
  ]

  const info: { label: string; value: string }[] = [
    { label: "OS", value: server.os_type ? `${server.os_type}${server.os_version ? ` ${server.os_version}` : ""}` : "—" },
    { label: "Architecture", value: server.arch ?? "—" },
    { label: "Shell", value: server.shell },
    { label: "Connection", value: server.connection_type.toUpperCase() },
    { label: "Host", value: server.host },
    { label: "Port", value: String(server.port) },
    { label: "Username", value: server.username },
    { label: "Auth", value: server.auth_type },
  ]

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link to="/servers" className="flex items-center rounded p-1 text-muted-foreground hover:text-foreground">
          <ChevronLeft size={18} />
        </Link>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-3">
            <h1 className="truncate text-2xl font-semibold text-foreground">{server.name}</h1>
            <ConnectionStatus status={server.status} />
          </div>
          <p className="text-sm text-muted-foreground">
            {server.username}@{server.host}:{server.port}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to={`/servers/${server.id}/chat`}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            <MessageSquare size={14} />
            AI Chat
          </Link>
          <ServerActionsMenu
            onTest={() => testMutation.mutate()}
            onDetect={() => detectMutation.mutate()}
            onEdit={() => setShowEdit(true)}
            onCredentials={() => setShowCreds(true)}
            onDelete={() => setConfirmDelete(true)}
            testPending={testMutation.isPending}
            detectPending={detectMutation.isPending}
          />
        </div>
      </div>

      {/* Tab navigation */}
      <div className="flex gap-5 overflow-x-auto border-b border-border">
        {tabs.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            end={t.end}
            className={({ isActive }) =>
              `whitespace-nowrap border-b-2 pb-2.5 text-sm transition-colors ${
                isActive
                  ? "border-foreground font-medium text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`
            }
          >
            {t.label}
          </NavLink>
        ))}
      </div>

      {showEdit && <EditServerModal server={server} onClose={() => setShowEdit(false)} />}
      {showCreds && <UpdateCredentialsModal server={server} onClose={() => setShowCreds(false)} />}

      {/* Login rejected (stale credentials) */}
      {server.status === "auth_failed" && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3">
          <div className="flex items-start gap-2">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-500" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-foreground">Login is being rejected</p>
              <p className="mt-1 text-sm text-muted-foreground">
                This server is refusing the saved login — most likely its password changed. Update it
                under Credentials. If you also rebuilt or reinstalled the server, you'll be asked to
                trust its new identity right after.
              </p>
              <button
                onClick={() => setShowCreds(true)}
                className="mt-3 flex items-center gap-2 rounded-md bg-amber-500/90 px-4 py-1.5 text-sm font-medium text-white hover:bg-amber-500"
              >
                <KeyRound size={13} />
                Update credentials
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Server identity changed (host-key mismatch) */}
      {server.status === "host_changed" && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3">
          <div className="flex items-start gap-2">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-red-500" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-foreground">Server identity changed</p>
              <p className="mt-1 text-sm text-muted-foreground">
                This server's SSH host key no longer matches the one ServerAlly trusted on first
                connect, so connections are blocked. If you rebuilt or replaced this server that's
                expected — trust the new key. If you didn't, the connection may be intercepted; do
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
                    : `Couldn't reconnect: ${trustMutation.data.error ?? "unknown error"}`}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Action result banners (from the ⋯ menu) */}
      {testMutation.data && (
        <div
          className={`rounded-md px-4 py-2.5 text-sm ${testMutation.data.ok ? "bg-green-500/10 text-green-600 dark:text-green-400" : "bg-destructive/10 text-destructive"}`}
        >
          {testMutation.data.ok
            ? `Connected in ${testMutation.data.latency_ms}ms`
            : `Connection failed: ${testMutation.data.error}`}
        </div>
      )}
      {detectMutation.data && (
        <div className="rounded-md bg-muted px-4 py-2.5 text-sm text-muted-foreground">
          Detected: {detectMutation.data.pretty_name} · {detectMutation.data.arch}
        </div>
      )}

      {/* Overview — widget dashboard */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="rounded-lg border border-border bg-card p-4">
            <h3 className="mb-3 text-sm font-medium text-foreground">Server info</h3>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm sm:grid-cols-4">
              {info.map((f) => (
                <div key={f.label}>
                  <dt className="text-xs text-muted-foreground">{f.label}</dt>
                  <dd className="truncate font-mono text-foreground capitalize">{f.value}</dd>
                </div>
              ))}
            </dl>
          </div>

          <InstalledWidget serverId={server.id} />
          <RecentActivityWidget serverId={server.id} />

          {server.notes && (
            <div className="rounded-lg border border-border bg-card p-4">
              <h3 className="mb-2 text-sm font-medium text-foreground">Notes</h3>
              <p className="whitespace-pre-wrap text-sm text-muted-foreground">{server.notes}</p>
            </div>
          )}

          {server.tags && server.tags.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {server.tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-full border border-border px-3 py-0.5 text-xs text-muted-foreground"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="space-y-4">
          <ServerMetrics serverId={server.id} />
          <SecurityWidget serverId={server.id} />
          <BackupsWidget serverId={server.id} />
        </div>
      </div>

      {/* Delete confirm */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-sm rounded-xl border border-border bg-card p-6 shadow-xl">
            <h3 className="font-semibold text-foreground">Delete "{server.name}"?</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              This will permanently remove the server. All command history will be deleted.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setConfirmDelete(false)}
                className="rounded-md px-4 py-2 text-sm text-muted-foreground hover:bg-accent"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="flex items-center gap-2 rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50"
              >
                {deleteMutation.isPending && <Loader2 size={13} className="animate-spin" />}
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

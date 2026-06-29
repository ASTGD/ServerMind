import { useState } from "react"
import { useParams, useNavigate, Link } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { ChevronLeft, Trash2, RefreshCw, Search, Loader2, MessageSquare, Terminal as TerminalIcon, Clock, Activity, FolderOpen, Shield, HardDriveDownload, Globe, KeyRound, Pencil, AlertTriangle, Package } from "lucide-react"
import { getServer, deleteServer, testConnection, detectOs, trustKey } from "@/api/servers"
import ConnectionStatus from "@/components/server/ConnectionStatus"
import ServerMetrics from "@/components/server/ServerMetrics"
import UpdateCredentialsModal from "@/components/server/UpdateCredentialsModal"
import EditServerModal from "@/components/server/EditServerModal"
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
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["server", id] })
    },
  })

  const detectMutation = useMutation({
    mutationFn: () => detectOs(id!),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["server", id] })
    },
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Link
          to="/servers"
          className="flex items-center gap-1 rounded p-1 text-muted-foreground hover:text-foreground"
        >
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
            <MessageSquare size={13} />
            AI Chat
          </Link>
          {server.connection_type === "hosting" && (
            <Link
              to={`/servers/${server.id}/hosting`}
              className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            >
              <Globe size={13} />
              Hosting
            </Link>
          )}
          <Link
            to={`/servers/${server.id}/terminal`}
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <TerminalIcon size={13} />
            Terminal
          </Link>
          <Link
            to={`/servers/${server.id}/scheduler`}
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <Clock size={13} />
            Scheduler
          </Link>
          <Link
            to={`/servers/${server.id}/monitoring`}
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <Activity size={13} />
            Monitoring
          </Link>
          <Link
            to={`/servers/${server.id}/files`}
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <FolderOpen size={13} />
            Files
          </Link>
          <Link
            to={`/servers/${server.id}/security`}
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <Shield size={13} />
            Security
          </Link>
          <Link
            to={`/servers/${server.id}/backups`}
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <HardDriveDownload size={13} />
            Backups
          </Link>
          <Link
            to={`/servers/${server.id}/installed`}
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <Package size={13} />
            Installed
          </Link>
          <button
            onClick={() => testMutation.mutate()}
            disabled={testMutation.isPending}
            title="Test connection"
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground disabled:opacity-50"
          >
            {testMutation.isPending ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
            Test
          </button>
          <button
            onClick={() => detectMutation.mutate()}
            disabled={detectMutation.isPending}
            title="Detect OS"
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground disabled:opacity-50"
          >
            {detectMutation.isPending ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
            Detect OS
          </button>
          <button
            onClick={() => setShowEdit(true)}
            title="Edit server"
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <Pencil size={13} />
            Edit
          </button>
          <button
            onClick={() => setShowCreds(true)}
            title="Update credentials"
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <KeyRound size={13} />
            Credentials
          </button>
          <button
            onClick={() => setConfirmDelete(true)}
            className="flex items-center gap-1.5 rounded-md border border-destructive/30 px-3 py-1.5 text-sm text-destructive hover:bg-destructive/10 disabled:opacity-50"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {showEdit && (
        <EditServerModal server={server} onClose={() => setShowEdit(false)} />
      )}
      {showCreds && (
        <UpdateCredentialsModal server={server} onClose={() => setShowCreds(false)} />
      )}

      {/* Login rejected (stale credentials) — guide to Credentials, then trust */}
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

      {/* Server identity changed (host-key mismatch) — Risk 3 */}
      {server.status === "host_changed" && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3">
          <div className="flex items-start gap-2">
            <AlertTriangle size={16} className="mt-0.5 shrink-0 text-red-500" />
            <div className="flex-1">
              <p className="text-sm font-semibold text-foreground">Server identity changed</p>
              <p className="mt-1 text-sm text-muted-foreground">
                This server's SSH host key no longer matches the one ServerMind trusted on first
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

      {/* Test result */}
      {testMutation.data && (
        <div className={`rounded-md px-4 py-2.5 text-sm ${testMutation.data.ok ? "bg-green-500/10 text-green-600 dark:text-green-400" : "bg-destructive/10 text-destructive"}`}>
          {testMutation.data.ok
            ? `Connected in ${testMutation.data.latency_ms}ms`
            : `Connection failed: ${testMutation.data.error}`}
        </div>
      )}

      {/* Detect result */}
      {detectMutation.data && (
        <div className="rounded-md bg-muted px-4 py-2.5 text-sm text-muted-foreground">
          Detected: {detectMutation.data.pretty_name} · {detectMutation.data.arch}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Server info */}
        <div className="lg:col-span-2 space-y-4">
          <div className="rounded-lg border border-border bg-card p-4">
            <h3 className="mb-3 text-sm font-medium text-foreground">Server Info</h3>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <div>
                <dt className="text-muted-foreground">Host</dt>
                <dd className="font-mono text-foreground">{server.host}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Port</dt>
                <dd className="font-mono text-foreground">{server.port}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Username</dt>
                <dd className="font-mono text-foreground">{server.username}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Auth</dt>
                <dd className="text-foreground capitalize">{server.auth_type}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">OS</dt>
                <dd className="text-foreground">
                  {server.os_type
                    ? `${server.os_type}${server.os_version ? ` ${server.os_version}` : ""}`
                    : "—"}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Architecture</dt>
                <dd className="text-foreground">{server.arch ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Shell</dt>
                <dd className="font-mono text-foreground">{server.shell}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">Connection</dt>
                <dd className="uppercase font-mono text-foreground">{server.connection_type}</dd>
              </div>
            </dl>
          </div>

          {server.notes && (
            <div className="rounded-lg border border-border bg-card p-4">
              <h3 className="mb-2 text-sm font-medium text-foreground">Notes</h3>
              <p className="text-sm text-muted-foreground whitespace-pre-wrap">{server.notes}</p>
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

        {/* Metrics sidebar */}
        <div>
          <ServerMetrics serverId={server.id} />
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

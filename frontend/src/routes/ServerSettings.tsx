import { useState } from "react"
import { useNavigate, useOutletContext } from "react-router-dom"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Loader2, KeyRound, Pencil, Search, Trash2, Wifi } from "lucide-react"
import { deleteServer, detectOs, testConnection } from "@/api/servers"
import EditServerModal from "@/components/server/EditServerModal"
import UpdateCredentialsModal from "@/components/server/UpdateCredentialsModal"
import { Button } from "@/components/ui"
import type { Server } from "@/types"

/**
 * Everything about the asset itself, rather than about what runs on it.
 *
 * These actions used to hide behind a "⋯" in the header. They belong on a page: an owner
 * looking for "how do I change the password we saved" should find it by reading the menu,
 * not by discovering a menu inside a menu.
 */
export default function ServerSettings() {
  const { server } = useOutletContext<{ server: Server }>()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showEdit, setShowEdit] = useState(false)
  const [showCreds, setShowCreds] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const test = useMutation({
    mutationFn: () => testConnection(server.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["server", server.id] }),
  })
  const detect = useMutation({
    mutationFn: () => detectOs(server.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["server", server.id] }),
  })
  const remove = useMutation({
    mutationFn: () => deleteServer(server.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["servers"] })
      navigate("/servers", { replace: true })
    },
  })

  return (
    <div className="max-w-2xl space-y-5">
      <section className="rounded-xl border border-border bg-card p-4">
        <h2 className="text-[15px] font-medium text-foreground">Connection</h2>
        <dl className="mt-3 space-y-2 text-sm">
          <Row label="Address" value={`${server.host}:${server.port}`} />
          <Row label="Username" value={server.username} />
          <Row label="Connects over" value={server.connection_type.toUpperCase()} />
          {server.os_type && (
            <Row label="Operating system"
              value={server.os_version ? `${server.os_type} ${server.os_version}` : server.os_type} />
          )}
          {server.arch && <Row label="Architecture" value={server.arch} />}
          {server.panel_type && <Row label="Control panel" value={server.panel_type} />}
        </dl>

        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" variant="outline" disabled={test.isPending} onClick={() => test.mutate()}>
            {test.isPending ? <Loader2 size={13} className="animate-spin" /> : <Wifi size={13} />}
            Test connection
          </Button>
          <Button size="sm" variant="outline" disabled={detect.isPending} onClick={() => detect.mutate()}>
            {detect.isPending ? <Loader2 size={13} className="animate-spin" /> : <Search size={13} />}
            Detect system
          </Button>
          <Button size="sm" variant="outline" onClick={() => setShowEdit(true)}>
            <Pencil size={13} /> Edit details
          </Button>
          <Button size="sm" variant="outline" onClick={() => setShowCreds(true)}>
            <KeyRound size={13} /> Update credentials
          </Button>
        </div>

        {test.data && (
          <p className={`mt-3 rounded-md px-3 py-2 text-sm ${test.data.ok
            ? "bg-green-500/10 text-green-600 dark:text-green-400"
            : "bg-destructive/10 text-destructive"}`}>
            {test.data.ok
              ? `Connected in ${test.data.latency_ms}ms`
              : `Connection failed: ${test.data.error}`}
          </p>
        )}
        {detect.data && (
          <p className="mt-3 rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground">
            Detected: {detect.data.pretty_name} · {detect.data.arch}
          </p>
        )}
      </section>

      <section className="rounded-xl border border-red-500/30 bg-red-500/[0.03] p-4">
        <h2 className="text-[15px] font-medium text-foreground">Remove this asset</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          This removes it from ServerAlly along with its history, scans and backups records.
          The server itself is not touched and keeps running.
        </p>
        {confirmDelete ? (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button size="sm" variant="danger" disabled={remove.isPending}
              onClick={() => remove.mutate()}>
              {remove.isPending && <Loader2 size={13} className="animate-spin" />}
              Yes, remove {server.name}
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setConfirmDelete(false)}>Cancel</Button>
          </div>
        ) : (
          <Button size="sm" variant="outline" className="mt-3" onClick={() => setConfirmDelete(true)}>
            <Trash2 size={13} /> Remove asset
          </Button>
        )}
      </section>

      {showEdit && <EditServerModal server={server} onClose={() => setShowEdit(false)} />}
      {showCreds && <UpdateCredentialsModal server={server} onClose={() => setShowCreds(false)} />}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="truncate text-right text-foreground" title={value}>{value}</dd>
    </div>
  )
}

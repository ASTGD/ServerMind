import { useState } from "react"
import { Link } from "react-router-dom"
import { Server as ServerIcon, Cpu, AlertTriangle } from "lucide-react"
import type { Server } from "@/types"
import ConnectionStatus from "./ConnectionStatus"

interface Props {
  server: Server
}

export default function ServerCard({ server }: Props) {
  const [showMsg, setShowMsg] = useState(false)
  return (
    <Link
      to={`/servers/${server.id}`}
      className="block rounded-lg border border-border bg-card p-4 hover:border-primary/50 hover:shadow-sm transition-all"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted">
            <ServerIcon size={18} className="text-muted-foreground" />
          </div>
          <div className="min-w-0">
            <p className="truncate font-medium text-foreground">{server.name}</p>
            <p className="truncate text-xs text-muted-foreground">{server.host}:{server.port}</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {server.status === "auth_failed" && (
            <div className="relative">
              <button
                type="button"
                aria-label="Action needed — password may have changed"
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); setShowMsg((v) => !v) }}
                className="flex h-6 w-6 items-center justify-center rounded-full text-red-500 hover:bg-red-500/10"
              >
                <AlertTriangle size={15} />
              </button>
              {showMsg && (
                <div className="absolute right-0 top-7 z-20 w-60 rounded-lg border border-border bg-card p-3 text-left shadow-lg">
                  <p className="text-xs font-semibold text-foreground">Password may have changed</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    This server is rejecting the saved login. If you changed its password,
                    open it and use <span className="font-medium text-foreground">Credentials</span> to update it.
                  </p>
                  <span className="mt-2 inline-block text-xs font-medium text-primary">Open server to fix →</span>
                </div>
              )}
            </div>
          )}
          {server.status === "host_changed" && (
            <div className="relative">
              <button
                type="button"
                aria-label="Server identity changed — host key no longer matches"
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); setShowMsg((v) => !v) }}
                className="flex h-6 w-6 items-center justify-center rounded-full text-red-500 hover:bg-red-500/10"
              >
                <AlertTriangle size={15} />
              </button>
              {showMsg && (
                <div className="absolute right-0 top-7 z-20 w-64 rounded-lg border border-border bg-card p-3 text-left shadow-lg">
                  <p className="text-xs font-semibold text-foreground">Server identity changed</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    This server's SSH key no longer matches the one we trusted. It may have been
                    rebuilt — or the connection may be intercepted. Open it to review and trust the new key.
                  </p>
                  <span className="mt-2 inline-block text-xs font-medium text-primary">Open server to review →</span>
                </div>
              )}
            </div>
          )}
          <ConnectionStatus status={server.status} />
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
        {server.os_type && (
          <span className="flex items-center gap-1">
            <Cpu size={11} />
            {server.os_type}{server.os_version ? ` ${server.os_version}` : ""}
            {server.arch ? ` · ${server.arch}` : ""}
          </span>
        )}
        {server.connection_type && (
          <span className="rounded bg-muted px-1.5 py-0.5 uppercase font-mono">
            {server.connection_type}
          </span>
        )}
      </div>

      {server.tags && server.tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {server.tags.map((tag) => (
            <span
              key={tag}
              className="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </Link>
  )
}

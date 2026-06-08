import { Link } from "react-router-dom"
import { Server as ServerIcon, Cpu } from "lucide-react"
import type { Server } from "@/types"
import ConnectionStatus from "./ConnectionStatus"

interface Props {
  server: Server
}

export default function ServerCard({ server }: Props) {
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
        <ConnectionStatus status={server.status} className="shrink-0" />
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

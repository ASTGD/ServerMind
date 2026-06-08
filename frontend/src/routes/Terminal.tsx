import { useParams, Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { ChevronLeft, MessageSquare } from "lucide-react"
import { getServer } from "@/api/servers"
import XTerminal from "@/components/terminal/XTerminal"
import ConnectionStatus from "@/components/server/ConnectionStatus"
import type { Server } from "@/types"

export default function Terminal() {
  const { id } = useParams<{ id: string }>()

  const { data: server } = useQuery<Server>({
    queryKey: ["server", id],
    queryFn: () => getServer(id!),
    enabled: !!id,
  })

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Header */}
      <div className="flex items-center gap-3 border-b border-border px-4 py-3">
        <Link
          to={`/servers/${id}`}
          className="rounded p-1 text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft size={18} />
        </Link>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="truncate font-medium text-foreground">
              {server?.name ?? "Loading…"}
            </p>
            {server && <ConnectionStatus status={server.status} />}
          </div>
          {server && (
            <p className="text-xs text-muted-foreground">
              {server.username}@{server.host} · Terminal
            </p>
          )}
        </div>
        <Link
          to={`/servers/${id}/chat`}
          className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <MessageSquare size={12} />
          AI Chat
        </Link>
      </div>

      {/* Terminal */}
      <div className="flex-1 overflow-hidden p-2">
        {id && <XTerminal serverId={id} />}
      </div>
    </div>
  )
}

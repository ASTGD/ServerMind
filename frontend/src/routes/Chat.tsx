import { useParams, Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { ChevronLeft, Terminal as TerminalIcon } from "lucide-react"
import { getServer } from "@/api/servers"
import ChatWindow from "@/components/chat/ChatWindow"
import ConnectionStatus from "@/components/server/ConnectionStatus"
import type { Server } from "@/types"

export default function Chat() {
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
              {server.os_type ?? "Linux"} · AI Chat
            </p>
          )}
        </div>
        <Link
          to={`/servers/${id}/terminal`}
          className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <TerminalIcon size={12} />
          Terminal
        </Link>
      </div>

      {/* Chat */}
      <div className="flex-1 overflow-hidden">
        {id && <ChatWindow serverId={id} />}
      </div>
    </div>
  )
}

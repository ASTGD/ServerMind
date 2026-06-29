import { useQuery } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import { History, CheckCircle2, XCircle, MessageSquare, PlayCircle } from "lucide-react"
import { listActivity } from "@/api/activity"

/** Read-only feed of recent AI commands + playbook runs for this server. */
export default function RecentActivityWidget({ serverId }: { serverId: string }) {
  const { data: all = [], isLoading } = useQuery({
    queryKey: ["activity", "server", serverId],
    queryFn: () => listActivity(50),
  })
  const items = all.filter((a) => a.server_id === serverId).slice(0, 5)

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h3 className="mb-3 flex items-center gap-1.5 text-sm font-medium text-foreground">
        <History size={14} /> Recent activity
      </h3>
      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-xs text-muted-foreground">No activity yet.</p>
      ) : (
        <div className="space-y-2">
          {items.map((a) => (
            <div key={a.id} className="flex items-center gap-2 text-xs">
              {a.status === "success" ? (
                <CheckCircle2 size={13} className="shrink-0 text-green-500" />
              ) : a.status === "failed" ? (
                <XCircle size={13} className="shrink-0 text-red-500" />
              ) : a.kind === "command" ? (
                <MessageSquare size={13} className="shrink-0 text-muted-foreground" />
              ) : (
                <PlayCircle size={13} className="shrink-0 text-muted-foreground" />
              )}
              <span className="truncate text-foreground">{a.title}</span>
              <span className="ml-auto shrink-0 text-muted-foreground">
                {formatDistanceToNow(new Date(a.created_at), { addSuffix: true })}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

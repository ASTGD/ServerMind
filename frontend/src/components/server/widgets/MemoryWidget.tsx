import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Brain, Trash2 } from "lucide-react"
import { listServerMemories, deleteMemory } from "@/api/memories"

/** What Ally remembers about this server — transparent and deletable (no hidden brain). */
export default function MemoryWidget({ serverId }: { serverId: string }) {
  const qc = useQueryClient()
  const { data: memories = [], isLoading } = useQuery({
    queryKey: ["server-memories", serverId],
    queryFn: () => listServerMemories(serverId),
  })
  const forgetMutation = useMutation({
    mutationFn: deleteMemory,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["server-memories", serverId] }),
  })

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-sm font-medium text-foreground">
          <Brain size={14} /> Ally remembers
        </h3>
        {memories.length > 0 && (
          <span className="text-xs text-muted-foreground">{memories.length}</span>
        )}
      </div>

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : memories.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          Nothing yet — Ally saves short notes about this server as you work together.
        </p>
      ) : (
        <div className="space-y-1.5">
          {memories.slice(0, 6).map((m) => (
            <div key={m.id} className="group flex items-start gap-2 text-xs">
              <span className="min-w-0 flex-1 text-foreground">{m.content}</span>
              <button
                onClick={() => forgetMutation.mutate(m.id)}
                title="Forget this"
                aria-label="Forget this note"
                className="shrink-0 rounded p-0.5 text-muted-foreground opacity-0 transition-opacity hover:text-red-500 group-hover:opacity-100"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
          {memories.length > 6 && (
            <p className="pt-0.5 text-[11px] text-muted-foreground">
              +{memories.length - 6} more
            </p>
          )}
        </div>
      )}
    </div>
  )
}

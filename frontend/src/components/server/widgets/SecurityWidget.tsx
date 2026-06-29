import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import { Shield, Loader2, RefreshCw } from "lucide-react"
import { listSecurityScans, runSecurityScan } from "@/api/security"

function gradeClasses(g: string): string {
  switch (g) {
    case "A": return "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
    case "B": return "bg-lime-500/15 text-lime-600 dark:text-lime-400"
    case "C": return "bg-amber-500/15 text-amber-600 dark:text-amber-400"
    case "D": return "bg-orange-500/15 text-orange-600 dark:text-orange-400"
    default: return "bg-red-500/15 text-red-600 dark:text-red-400"
  }
}

/** Read-only security posture: latest grade/score + re-scan, inline. */
export default function SecurityWidget({ serverId }: { serverId: string }) {
  const qc = useQueryClient()
  const { data: scans = [], isLoading } = useQuery({
    queryKey: ["security-scans", serverId],
    queryFn: () => listSecurityScans(serverId),
  })
  const scan = useMutation({
    mutationFn: () => runSecurityScan(serverId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["security-scans", serverId] }),
  })
  const latest = scans.find((s) => s.status === "completed") ?? scans[0]

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-sm font-medium text-foreground">
          <Shield size={14} /> Security
        </h3>
        <button
          onClick={() => scan.mutate()}
          disabled={scan.isPending}
          className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-accent disabled:opacity-50"
        >
          {scan.isPending ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />}
          {latest ? "Re-scan" : "Scan"}
        </button>
      </div>

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : scan.isPending ? (
        <p className="text-xs text-muted-foreground">Running scan… this can take a minute.</p>
      ) : !latest ? (
        <p className="text-xs text-muted-foreground">Not scanned yet — run a scan to get a grade.</p>
      ) : (
        <div className="flex items-center gap-3">
          <div className={`flex h-10 w-10 items-center justify-center rounded-full text-lg font-semibold ${gradeClasses(latest.grade)}`}>
            {latest.grade}
          </div>
          <div className="min-w-0">
            <div className="text-sm font-medium text-foreground">
              {latest.score}
              <span className="text-xs text-muted-foreground"> /100</span>
            </div>
            <div className="text-xs text-muted-foreground">
              scanned {formatDistanceToNow(new Date(latest.created_at), { addSuffix: true })}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

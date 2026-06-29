import { useQuery } from "@tanstack/react-query"
import { Link } from "react-router-dom"
import { formatDistanceToNow } from "date-fns"
import { HardDriveDownload, Check, Clock, AlertTriangle } from "lucide-react"
import { listBackups } from "@/api/backups"

/** Read-only backup status (last run / next schedule). Management lives behind "Manage"
 * (creating jobs and restores are interactive). */
export default function BackupsWidget({ serverId }: { serverId: string }) {
  const { data: backups = [], isLoading } = useQuery({
    queryKey: ["backups", serverId],
    queryFn: () => listBackups(serverId),
  })

  const lastRun = backups
    .filter((b) => b.last_run)
    .sort((a, b) => (b.last_run! > a.last_run! ? 1 : -1))[0]
  const nextJob = backups
    .filter((b) => b.is_active && b.next_run)
    .sort((a, b) => (a.next_run! > b.next_run! ? 1 : -1))[0]

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-sm font-medium text-foreground">
          <HardDriveDownload size={14} /> Backups
        </h3>
        <Link to={`/servers/${serverId}/backups`} className="text-xs text-primary hover:underline">
          Manage
        </Link>
      </div>

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : backups.length === 0 ? (
        <p className="text-xs text-muted-foreground">No backups configured.</p>
      ) : (
        <div className="space-y-1.5 text-xs">
          <div className="flex items-center gap-2">
            {lastRun?.last_status === "success" ? (
              <Check size={13} className="text-green-500" />
            ) : lastRun ? (
              <AlertTriangle size={13} className="text-amber-500" />
            ) : (
              <Clock size={13} className="text-muted-foreground" />
            )}
            <span className="text-muted-foreground">Last backup</span>
            <span className="ml-auto text-foreground">
              {lastRun?.last_run ? formatDistanceToNow(new Date(lastRun.last_run), { addSuffix: true }) : "never"}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Clock size={13} className="text-muted-foreground" />
            <span className="text-muted-foreground">Next</span>
            <span className="ml-auto text-foreground">
              {nextJob?.human_schedule ??
                (nextJob?.next_run ? formatDistanceToNow(new Date(nextJob.next_run), { addSuffix: true }) : "not scheduled")}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Jobs</span>
            <span className="ml-auto text-foreground">{backups.length}</span>
          </div>
        </div>
      )}
    </div>
  )
}

import { Link, useOutletContext } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { FileText, Loader2 } from "lucide-react"
import { getSiteLogs, type SiteDetail } from "@/api/sites"
import { EmptyState } from "@/components/ui"

/** This site's own logs, rather than the whole machine's. */
export default function SiteLogs() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  const { data, isLoading } = useQuery({
    queryKey: ["site-logs", site.id],
    queryFn: () => getSiteLogs(site.id),
  })

  if (isLoading) {
    return <div className="flex justify-center py-12 text-muted-foreground">
      <Loader2 size={18} className="animate-spin" /></div>
  }

  const logs = data?.logs ?? []
  if (!logs.length) {
    return (
      <EmptyState
        icon={FileText}
        title="No log files for this site yet"
        description="A site gets its own web-server log the first time someone visits it. Its application log appears once the application writes one."
      />
    )
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      {logs.map((log) => (
        <div key={log.path}
          className="flex flex-wrap items-center gap-3 border-t border-border px-4 py-2.5 first:border-t-0">
          <FileText size={14} className="shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <p className="text-sm text-foreground">{log.label}</p>
            <p className="truncate font-mono text-caption text-muted-foreground">{log.path}</p>
          </div>
          <span className="shrink-0 text-caption tabular-nums text-muted-foreground">
            {formatSize(log.size_bytes)}
          </span>
        </div>
      ))}
      <div className="border-t border-border px-4 py-2.5">
        <Link to={`/servers/${site.server.id}/logs`}
          className="text-caption text-muted-foreground hover:text-foreground">
          Open the log viewer for this server →
        </Link>
      </div>
    </div>
  )
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`
  return `${bytes} B`
}

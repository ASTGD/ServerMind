import { Link, useOutletContext } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { Clock, Loader2 } from "lucide-react"
import { getSiteCron, type SiteDetail } from "@/api/sites"
import { EmptyState } from "@/components/ui"

/**
 * The scheduled jobs that belong to this site.
 *
 * The crontab is the server's, so this is a filtered view of it — and it says so, because
 * hiding that would make someone think deleting a job here could not affect anything else.
 */
export default function SiteCron() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  const { data, isLoading } = useQuery({
    queryKey: ["site-cron", site.id],
    queryFn: () => getSiteCron(site.id),
  })

  if (isLoading) {
    return <div className="flex justify-center py-12 text-muted-foreground">
      <Loader2 size={18} className="animate-spin" /></div>
  }

  const jobs = data?.jobs ?? []
  const manage = (
    <Link to={`/servers/${site.server.id}/cron`}
      className="text-caption text-muted-foreground hover:text-foreground">
      Add or remove jobs on this server →
    </Link>
  )

  if (!jobs.length) {
    return (
      <div className="space-y-3">
        <EmptyState
          icon={Clock}
          title="Nothing scheduled for this site"
          description="Laravel needs a job every minute to run its scheduled work, and WordPress runs its own better on a timer than during a visitor's page load."
        />
        <div className="px-1">{manage}</div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-xl border border-border bg-card">
        {jobs.map((job, i) => (
          <div key={`${job.raw}-${i}`}
            className="flex items-start gap-3 border-t border-border px-4 py-3 first:border-t-0">
            <Clock size={14} className="mt-0.5 shrink-0 text-muted-foreground" />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-foreground">
                {job.description || job.schedule || "Schedule not recognised"}
              </p>
              <p className="mt-0.5 break-all font-mono text-caption text-muted-foreground">
                {job.command}
              </p>
              {job.note && <p className="mt-0.5 text-caption text-muted-foreground/80">{job.note}</p>}
            </div>
            <span className="shrink-0 text-caption text-muted-foreground">as {job.user}</span>
          </div>
        ))}
      </div>
      <p className="px-1 text-caption text-muted-foreground">
        These are the server's scheduled jobs that mention this site. {manage}
      </p>
    </div>
  )
}

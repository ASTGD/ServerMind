import { useOutletContext } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2, Database, Loader2, XCircle } from "lucide-react"
import { getSiteDatabase, type SiteDetail } from "@/api/sites"
import { EmptyState } from "@/components/ui"

/**
 * Which database this site uses, and whether it can reach it.
 *
 * The connection check is the point. "The site is down" is very often "the site cannot
 * reach its database" — a password changed after a migration, a database dropped, a MySQL
 * that is not running — and without this there is no way to tell that apart from an
 * application bug except by opening a terminal.
 *
 * Read-only by design. Dropping a site's own database from its own page is a footgun with
 * no undo anywhere in this system; the server's database screen does it, behind a typed
 * name, where the person doing it has the whole machine in view.
 */
export default function SiteDatabase() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  const { data, isLoading } = useQuery({
    queryKey: ["site-database", site.id],
    queryFn: () => getSiteDatabase(site.id),
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <Loader2 size={20} className="animate-spin" />
      </div>
    )
  }

  if (!data?.ok) {
    return (
      <EmptyState
        icon={Database}
        title="No database for this site"
        description={data?.reason ?? "We could not read this site's database settings."}
      />
    )
  }

  const size = data.size_mb == null ? null
    : data.size_mb >= 1024 ? `${(data.size_mb / 1024).toFixed(1)} GB`
    : data.size_mb >= 1 ? `${data.size_mb.toFixed(1)} MB`
    : "under 1 MB"

  return (
    <div className="space-y-4">
      {/* The answer to "is the database why my site is broken", stated first. */}
      <div className={`flex items-start gap-3 rounded-xl border p-4 ${
        !data.tested ? "border-border bg-card"
          : data.reachable ? "border-border bg-card"
          : "border-destructive/40 bg-destructive/5"}`}>
        {!data.tested
          ? <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-500" />
          : data.reachable
            ? <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
            : <XCircle size={16} className="mt-0.5 shrink-0 text-destructive" />}
        <div>
          <p className="text-sm font-medium text-foreground">
            {!data.tested ? "We could not test the connection"
              : data.reachable ? "The site can reach its database"
              : "The site cannot reach its database"}
          </p>
          <p className="mt-0.5 text-small text-muted-foreground">
            {!data.tested
              ? "There is no database client installed on this server, so we could not "
                + "check. That is not the same as it being broken."
              : data.reachable
                ? "Connected using the site's own settings, so this is what the site itself "
                  + "gets."
                : "We connected with the details in this site's own configuration and were "
                  + "refused. That is usually a password that no longer matches, or a "
                  + "database that has been removed — and it would make the site fail "
                  + "in a way that looks like a bug in the code."}
          </p>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card">
        <p className="border-b border-border px-4 py-3 text-sm font-medium text-foreground">
          What this site is configured to use
        </p>
        {[
          ["Database", data.name],
          ["Username", data.user],
          ["Host", data.host],
          ["Tables", data.tables == null ? null : String(data.tables)],
          ["Size", size],
        ].map(([label, value]) => (
          <div key={label as string}
               className="flex items-baseline justify-between gap-4 border-t border-border px-4 py-2.5 first:border-t-0">
            <span className="text-small text-muted-foreground">{label}</span>
            {value
              ? <span className="font-mono text-small text-foreground">{value}</span>
              : <span className="text-small text-muted-foreground/60">not known</span>}
          </div>
        ))}
      </div>

      <p className="text-caption text-muted-foreground">
        The password stays on the server. It is read there to make the connection attempt
        and is never sent here, stored, or written to any log.
      </p>
    </div>
  )
}

import { useState } from "react"
import { useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle, CheckCircle2, Database, Loader2, Plus, XCircle,
} from "lucide-react"
import {
  createSiteDatabase, getSiteDatabase, type NewSiteDatabase, type SiteDetail,
} from "@/api/sites"
import { Button, EmptyState } from "@/components/ui"

/**
 * Which database this site uses, and whether it can reach it.
 *
 * The connection check is the point. "The site is down" is very often "the site cannot
 * reach its database" — a password changed after a migration, a database dropped, a MySQL
 * that is not running — and without this there is no way to tell that apart from an
 * application bug except by opening a terminal.
 *
 * A site with none can be given one here. Deleting is deliberately not offered: dropping a
 * site's own database from its own page is a footgun with no undo anywhere in this system,
 * and the server's database screen does it behind a typed name, where the person doing it
 * has the whole machine in view.
 */
export default function SiteDatabase() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  const qc = useQueryClient()
  const [made, setMade] = useState<NewSiteDatabase | null>(null)
  const [error, setError] = useState("")

  const { data, isLoading } = useQuery({
    queryKey: ["site-database", site.id],
    queryFn: () => getSiteDatabase(site.id),
  })

  const create = useMutation({
    mutationFn: () => createSiteDatabase(site.id),
    onSuccess: (r) => {
      setMade(r); setError("")
      qc.invalidateQueries({ queryKey: ["site-database", site.id] })
    },
    onError: (e) => setError(
      (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      || "That database could not be created."),
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <Loader2 size={20} className="animate-spin" />
      </div>
    )
  }

  if (made) return <Credentials made={made} />

  if (!data?.ok) {
    return (
      <div className="space-y-3">
        {error && (
          <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-foreground">
            {error}
          </p>
        )}
        <EmptyState
          icon={Database}
          title="No database in this site's settings"
          description={data?.reason ?? "We could not read this site's database settings."}
        />
        {/* A site with no configuration we can read cannot tell us what it uses — not even
            a database we made for it ourselves. Saying what is there, and being clear it
            is a guess, beats offering to make a second one that fails on the name. */}
        {data?.named_after_site ? (
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-sm font-medium text-foreground">
              There is a database called{" "}
              <span className="font-mono">{data.named_after_site.name}</span> on this server
            </p>
            <p className="mt-1 text-small text-muted-foreground">
              It is named after this site, so it is probably this site's — but this site's
              own settings do not name a database, so we cannot be sure from here. Put its
              details into the application's settings and this page will read them back.
            </p>
          </div>
        ) : (
          <div className="rounded-xl border border-border bg-card p-4">
            <p className="text-sm font-medium text-foreground">Make one for this site</p>
            <p className="mt-1 text-small text-muted-foreground">
              A database of its own, with its own account and password, named after this
              site. Nothing else on the server can sign in to it.
            </p>
            <Button size="sm" className="mt-2.5" disabled={create.isPending}
              onClick={() => create.mutate()}>
              {create.isPending
                ? <Loader2 size={13} className="animate-spin" />
                : <Plus size={13} />}
              Create a database
            </Button>
          </div>
        )}
      </div>
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

/**
 * The one time these details are ever shown.
 *
 * We keep no copy — not in our database, not in the log, not in the audit entry, which
 * records that a database was made rather than how to get into it. So this says so
 * plainly, instead of offering a "show it again" that would have to be a lie.
 */
function Credentials({ made }: { made: NewSiteDatabase }) {
  const block = [
    `DB_DATABASE=${made.name}`,
    `DB_USERNAME=${made.user}`,
    `DB_PASSWORD=${made.password}`,
    `DB_HOST=${made.host}`,
  ].join("\n")

  return (
    <div className="space-y-3">
      <div className="flex items-start gap-3 rounded-xl border border-emerald-500/40 bg-emerald-500/5 p-4">
        <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
        <div>
          <p className="text-sm font-medium text-foreground">
            The database “{made.name}” is ready
          </p>
          <p className="mt-0.5 text-small text-muted-foreground">
            Put these into your application's settings. This is the only time the password
            is shown — we keep no copy of it anywhere, so there is nothing to show again.
          </p>
        </div>
      </div>

      <pre className="overflow-x-auto rounded-xl border border-border bg-muted/40 p-4 font-mono text-small text-foreground">
        {block}
      </pre>

      <Button size="sm" variant="outline"
        onClick={() => navigator.clipboard?.writeText(block)}>
        Copy these details
      </Button>
    </div>
  )
}

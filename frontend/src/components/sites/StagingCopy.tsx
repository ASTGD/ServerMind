import { useEffect, useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { FlaskConical, Loader2 } from "lucide-react"
import { createStaging, getStagingOptions, type SiteDetail } from "@/api/sites"
import { Button } from "@/components/ui"

/**
 * A safe copy of this site to try changes on — Ploi's "staging".
 *
 * **Ploi's version copies nothing.** It creates a second empty site with a `staging.`
 * prefix and search engines blocked; in the owner's own trial that produced a half-installed
 * WordPress beside a Laravel site. An empty staging site is not a staging site — it is a
 * second empty site with a longer name. So this card promises a real copy, and the wording
 * leads with the thing that makes it safe rather than with the thing that makes it a copy:
 * it gets its OWN database, so nothing done on it can reach the live site.
 *
 * That promise is kept by refusing rather than warning. If the copy cannot be given its own
 * database — because we cannot find the file that says which one this site uses, or cannot
 * tell which database holds its data — nothing is created at all, and the server says so.
 */
export default function StagingCopy({ site }: { site: SiteDetail }) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [domain, setDomain] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [started, setStarted] = useState<{ id: string; domain: string } | null>(null)

  const options = useQuery({
    queryKey: ["site-staging", site.id],
    queryFn: () => getStagingOptions(site.id),
  })

  useEffect(() => {
    if (options.data?.suggested_domain) {
      setDomain((d) => d || options.data.suggested_domain)
    }
  }, [options.data])

  const run = useMutation({
    mutationFn: () => createStaging(site.id, domain.trim()),
    onSuccess: (r) => {
      setStarted({ id: r.id, domain: r.domain })
      setError(null)
      queryClient.invalidateQueries({ queryKey: ["site-staging", site.id] })
      queryClient.invalidateQueries({ queryKey: ["sites"] })
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "The copy could not be started."),
  })

  const opts = options.data
  const existing = opts?.existing ?? []

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <FlaskConical size={15} className="text-muted-foreground" />
        <h3 className="text-h3 text-foreground">Staging copy</h3>
      </div>
      <p className="mt-1 text-small text-muted-foreground">
        A copy of this site to try changes on — the same files
        {opts?.needs_database !== false && <>, and its own database with your data in it</>}.
        Nothing you do on the copy can reach the live site.
      </p>

      {existing.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {existing.map((c) => (
            <div key={c.id}
                 className="flex items-center justify-between rounded-lg border border-border
                            bg-muted/30 px-3 py-2">
              <Link to={`/sites/${c.id}`}
                    className="font-mono text-small text-foreground hover:underline">
                {c.domain}
              </Link>
              <span className="text-caption text-muted-foreground">
                {c.status === "installing" ? "Setting up…"
                  : c.status === "failed" ? "Setup failed" : "Ready"}
              </span>
            </div>
          ))}
        </div>
      )}

      {started ? (
        <div className="mt-3 rounded-lg border-l-2 border-emerald-500 bg-emerald-500/5
                        px-3 py-2.5">
          <p className="text-small text-foreground">
            Making the copy at <span className="font-mono">{started.domain}</span>. It
            carries on in the background — the copy shows as <em>Setting up</em> until its
            files and data are both there.
          </p>
          <div className="mt-3 flex gap-2">
            <Button size="sm" variant="outline"
                    onClick={() => navigate(`/sites/${started.id}`)}>
              Open the copy
            </Button>
            <Button size="sm" variant="ghost"
                    onClick={() => { setStarted(null); setOpen(false) }}>Done</Button>
          </div>
        </div>
      ) : options.isLoading ? (
        <p className="mt-3 text-small text-muted-foreground">Checking…</p>
      ) : opts && !opts.can_stage ? (
        // Absent reasons are worse than stated ones: without this the button is simply
        // missing and nobody knows whether the feature exists.
        <p className="mt-3 rounded-lg border-l-2 border-border bg-muted/30 px-3 py-2
                      text-small text-muted-foreground">{opts.reason}</p>
      ) : !open ? (
        <div className="mt-3">
          <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
            {existing.length > 0 ? "Make another copy" : "Create a staging copy"}
          </Button>
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          <label className="block sm:max-w-sm">
            <span className="text-caption text-muted-foreground">Domain for the copy</span>
            <input
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder={opts?.suggested_domain || "staging.example.com"}
              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2
                         text-small text-foreground"
            />
          </label>

          <div className="rounded-lg border border-border bg-muted/30 px-3 py-2.5">
            <p className="text-caption font-medium text-foreground">What you get</p>
            <p className="mt-0.5 text-caption text-muted-foreground">
              Every file in this site{opts?.needs_database !== false && <>, its own database
              holding a copy of your data, its own settings pointing at that database</>}, and
              search engines asked to stay away so the copy never competes with the live site
              in results.{opts?.needs_database !== false && <> The data comes across whether
              you want it or not — a copy of this site with an empty database would show the
              installer, not your site. For the files alone, use Clone site.</>}
            </p>
            <p className="mt-2 text-caption font-medium text-foreground">What does not</p>
            <p className="mt-0.5 text-caption text-muted-foreground">
              Caches, installed dependencies and the HTTPS certificate. If we cannot point
              the copy at its own database, nothing is created — a copy still writing to your
              live site is worse than no copy at all.
            </p>
          </div>

          <div className="flex gap-2">
            <Button size="sm" onClick={() => run.mutate()}
                    disabled={run.isPending || !domain.trim()}>
              {run.isPending && <Loader2 size={14} className="animate-spin" />}
              Create the copy
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          </div>
        </div>
      )}

      {error && (
        <p className="mt-2 rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                      text-small text-destructive">{error}</p>
      )}
    </div>
  )
}

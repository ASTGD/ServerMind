import { useState } from "react"
import { Link } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { ArrowUpFromLine, GitCommitHorizontal, Loader2 } from "lucide-react"
import { getPromoteOptions, promoteSite, type SiteDetail } from "@/api/sites"
import { Button } from "@/components/ui"

/**
 * Putting this staging copy live — the reason the copy exists.
 *
 * Sits at the top of the staging site's own page rather than inside Manage. A staging site
 * has exactly one purpose, and a customer who cannot find the button does it by hand, which
 * is the outcome this whole feature exists to replace.
 *
 * **Two paths, and the card is honest about which one this site gets.** With a repository,
 * the exact commit the copy is serving is deployed to the live site — safe, reversible, and
 * nothing about the customer's data is touched. Without one, the files are copied, which
 * replaces a live website's files and cannot be undone from here. So the second path asks
 * for the live domain to be typed, shows what will NOT be copied, and leads with the thing
 * people are surprised by afterwards: plugins arrive switched off, because the database
 * deliberately stays behind.
 *
 * Renders nothing at all on a site that is not a staging copy — an "unavailable" card on
 * every ordinary site would be noise on the first screen anyone opens.
 */
export default function PromoteToLive({ site }: { site: SiteDetail }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState<"git" | "files" | null>(null)
  const [typed, setTyped] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<{ method: string; commit?: string } | null>(null)

  const options = useQuery({
    queryKey: ["site-promote", site.id],
    queryFn: () => getPromoteOptions(site.id),
  })

  const run = useMutation({
    mutationFn: (method: "git" | "files") => promoteSite(site.id, method, typed.trim()),
    onSuccess: (r) => {
      setDone({ method: r.method, commit: r.commit })
      setError(null)
      setOpen(null)
      queryClient.invalidateQueries({ queryKey: ["sites"] })
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "This could not be started."),
  })

  const opts = options.data
  if (options.isLoading || !opts?.is_staging) return null

  const live = opts.live
  const git = opts.git
  const files = opts.files

  return (
    <section className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <ArrowUpFromLine size={15} className="text-primary" />
        <h3 className="text-h3 text-foreground">Put this copy live</h3>
      </div>
      <p className="mt-1 text-small text-muted-foreground">
        {live
          ? <>This is a staging copy of{" "}
              <Link to={`/sites/${live.id}`} className="font-mono hover:underline">
                {live.domain}
              </Link>. When you are happy with it, put these changes on the live site.</>
          : opts.reason}
      </p>

      {done ? (
        <div className="mt-3 rounded-lg border-l-2 border-emerald-500 bg-emerald-500/5 px-3 py-2.5">
          <p className="text-small text-foreground">
            {done.method === "git"
              ? <>Deploying <span className="font-mono">{done.commit?.slice(0, 8)}</span> to{" "}
                  {live?.domain}. It builds in a folder nobody is serving and only goes live
                  when the build succeeds — watch it on the live site's Deployments screen.</>
              : <>Copying the files onto {live?.domain}. The live site is backed up first and
                  is not touched until a complete copy is ready.</>}
          </p>
          <Button className="mt-3" size="sm" variant="ghost"
                  onClick={() => { setDone(null); options.refetch() }}>Done</Button>
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          {/* ── the safe path ───────────────────────────────────────────── */}
          <div className="rounded-lg border border-border bg-muted/30 px-3 py-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-small font-medium text-foreground">
                Deploy this copy&rsquo;s code
              </p>
              {git?.available && open !== "git" && (
                <Button size="sm" onClick={() => { setOpen("git"); setError(null) }}>
                  Deploy to {live?.domain}
                </Button>
              )}
            </div>
            {git?.available ? (
              <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-caption
                            text-muted-foreground">
                <GitCommitHorizontal size={13} />
                Deploys exactly{" "}
                <span className="font-mono text-foreground">{git.commit.slice(0, 8)}</span>
                — the commit this copy is running — so nothing pushed since can slip in.
                Your data is not touched, and you can roll back.
              </p>
            ) : (
              <p className="mt-0.5 text-caption text-muted-foreground">{git?.reason}</p>
            )}

            {open === "git" && (
              <div className="mt-2.5 flex gap-2">
                <Button size="sm" disabled={run.isPending}
                        onClick={() => run.mutate("git")}>
                  {run.isPending && <Loader2 size={14} className="animate-spin" />}
                  Yes, deploy it
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setOpen(null)}>Cancel</Button>
              </div>
            )}
          </div>

          {/* ── the one that cannot be undone ───────────────────────────── */}
          <div className="rounded-lg border border-border bg-muted/30 px-3 py-2.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-small font-medium text-foreground">Copy this copy&rsquo;s files</p>
              {files?.available && open !== "files" && (
                <Button size="sm" variant="outline"
                        onClick={() => { setOpen("files"); setTyped(""); setError(null) }}>
                  Copy files to {live?.domain}
                </Button>
              )}
            </div>
            <p className="mt-0.5 text-caption text-muted-foreground">
              {files?.available
                ? <>For a site with no repository. Replaces the live site&rsquo;s files with
                    these. <span className="text-foreground">This cannot be undone from
                    here</span> — the live site is backed up on the server first.</>
                : files?.reason}
            </p>

            {open === "files" && (
              <div className="mt-3 space-y-3">
                <div className="rounded-lg border-l-2 border-amber-500 bg-amber-500/5 px-3 py-2">
                  <p className="text-caption text-foreground">{files?.caveat}</p>
                </div>
                <div>
                  <p className="text-caption font-medium text-foreground">Never copied</p>
                  <p className="mt-0.5 text-caption text-muted-foreground">
                    <span className="font-mono">{files?.excluded.join("  ·  ")}</span>
                    {" "}— your live settings keep pointing at your live database, and files
                    your visitors have uploaded since this copy was made stay where they are.
                  </p>
                </div>
                <label className="block sm:max-w-sm">
                  <span className="text-caption text-muted-foreground">
                    Type <span className="font-mono text-foreground">{live?.domain}</span> to
                    confirm
                  </span>
                  <input
                    value={typed}
                    onChange={(e) => setTyped(e.target.value)}
                    placeholder={live?.domain}
                    className="mt-1 w-full rounded-lg border border-border bg-background px-3
                               py-2 font-mono text-small text-foreground"
                  />
                </label>
                <div className="flex gap-2">
                  <Button size="sm" variant="danger" disabled={run.isPending || !typed.trim()}
                          onClick={() => run.mutate("files")}>
                    {run.isPending && <Loader2 size={14} className="animate-spin" />}
                    Replace the live site&rsquo;s files
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setOpen(null)}>Cancel</Button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {error && (
        <p className="mt-2 rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                      text-small text-destructive">{error}</p>
      )}
    </section>
  )
}

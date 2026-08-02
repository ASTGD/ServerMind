import { Link } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import {
  CheckCircle2, CircleAlert, FolderUp, GitBranch, Loader2, Rocket,
} from "lucide-react"
import { getSiteDeploy, type SiteDetail } from "@/api/sites"
import { cn } from "@/lib/utils"

/**
 * How code gets onto this site.
 *
 * It used to be a menu item and nothing else, so the site's own home page — the first thing
 * anyone sees — could not tell you the one thing a developer opens a site to do. Worse, on a
 * site that already ran something the home page said only what could NOT be done there.
 *
 * Deploying applies whether or not something is installed: putting a new version of a
 * Laravel app on a domain that already runs Laravel is the normal case, not the exception.
 * So this is always here, and it reports the real state — connected or not, and whether the
 * site is actually being SERVED from the deployed code, which is a separate fact and a real
 * source of "I deployed and nothing changed".
 */
export default function SiteCode({ site }: { site: SiteDetail }) {
  const { data, isLoading } = useQuery({
    // The same key the Deploy tab uses, so opening one warms the other and neither can show
    // a different answer to the same question.
    queryKey: ["site-deploy", site.id],
    queryFn: () => getSiteDeploy(site.id),
    enabled: site.server.connection_type === "ssh" && !site.server.panel_type,
  })

  if (site.server.connection_type !== "ssh" || site.server.panel_type) return null

  const target = data?.target ?? null
  const to = `/sites/${site.id}/deploy`

  return (
    <section className="rounded-xl border border-border bg-card">
      <header className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <h3 className="text-sm font-medium text-foreground">Deploy from code</h3>
          <p className="text-caption text-muted-foreground">
            {target
              ? "This site builds from a repository."
              : "Get your own code onto this site."}
          </p>
        </div>
        {target && (
          <Link to={to} className="shrink-0 rounded-lg border border-border px-2.5 py-1 text-caption font-medium text-muted-foreground hover:border-primary/40 hover:bg-primary/5 hover:text-foreground">
            Manage
          </Link>
        )}
      </header>

      {isLoading ? (
        <div className="flex justify-center py-10 text-muted-foreground">
          <Loader2 size={16} className="animate-spin" />
        </div>
      ) : target ? (
        <div className="space-y-2 p-4">
          <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm text-foreground">
            <GitBranch size={14} className="text-muted-foreground" />
            <span className="truncate font-mono">{target.repo}</span>
            <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-caption text-muted-foreground">
              {target.branch}
            </span>
          </p>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-caption">
            <DeployState status={target.last_status} release={target.current_release} />
            {/* Deployed and SERVED are different states, and the gap between them is the
                whole "I deployed and nothing changed" complaint. */}
            {target.serving ? (
              <span className="text-muted-foreground">the site serves this code</span>
            ) : (
              <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400">
                <CircleAlert size={11} />
                the site is not pointed at it yet
              </span>
            )}
          </div>
        </div>
      ) : (
        <div className="grid gap-2 p-4 sm:grid-cols-2">
          <Tile
            to={to}
            icon={GitBranch}
            title="Connect a repository"
            blurb="GitHub, GitLab, Bitbucket or any Git URL. Deploys build aside and switch over, so a failed build never reaches your visitors."
          />
          <Tile
            to={`/servers/${site.server.id}/files`}
            icon={FolderUp}
            title="Upload your files"
            blurb="No repository? Put files straight into the site's folder with the file manager."
          />
        </div>
      )}
    </section>
  )
}

function DeployState({ status, release }: { status: string | null; release: string | null }) {
  if (status === "running") {
    return (
      <span className="inline-flex items-center gap-1 text-muted-foreground">
        <Loader2 size={11} className="animate-spin" /> deploying now
      </span>
    )
  }
  if (status === "failed") {
    return (
      <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400">
        <CircleAlert size={11} /> last deploy failed
      </span>
    )
  }
  if (status === "success") {
    return (
      <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
        <CheckCircle2 size={11} /> release {release ?? "—"}
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-muted-foreground">
      <Rocket size={11} /> never deployed
    </span>
  )
}

function Tile({ to, icon: Icon, title, blurb }: {
  to: string
  icon: typeof GitBranch
  title: string
  blurb: string
}) {
  return (
    <Link
      to={to}
      className={cn(
        "flex flex-col items-start gap-1 rounded-lg border border-border p-3",
        "transition-colors hover:border-primary/60 hover:bg-accent",
      )}
    >
      <Icon size={16} className="text-primary" />
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="text-caption text-muted-foreground">{blurb}</p>
    </Link>
  )
}

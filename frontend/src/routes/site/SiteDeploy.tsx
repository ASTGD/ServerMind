import { useState } from "react"
import { useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle, CheckCircle2, GitBranch, Loader2, RotateCcw, Rocket,
} from "lucide-react"
import {
  connectSiteDeploy, getSiteDeploy, serveSiteFromDeploy, type SiteDetail,
} from "@/api/sites"
import { deployNow, listDeployRuns, rollback } from "@/api/deployments"
import { Button, EmptyState, Input, Label } from "@/components/ui"

/**
 * Getting code from a repository onto this website.
 *
 * The order here is the safety property, not a workflow preference. A deploy builds into
 * `releases/<stamp>` and moves a `current` symlink, and NONE of that reaches a visitor
 * until the web server is pointed through `current`. So:
 *
 *   connect  →  deploy (site still serving its old files)  →  point the site at it
 *
 * The site keeps working through as many failed first deploys as it takes, and the one step
 * a visitor can see is separate, deliberate, and reversible.
 */
export default function SiteDeploy() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  const qc = useQueryClient()
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["site-deploy", site.id],
    queryFn: () => getSiteDeploy(site.id),
  })

  const target = data?.target ?? null
  const { data: runs } = useQuery({
    queryKey: ["deploy-runs", target?.id],
    queryFn: () => listDeployRuns(target!.id),
    enabled: !!target,
    refetchInterval: target?.last_status === "running" ? 3000 : false,
  })

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["site-deploy", site.id] })
    qc.invalidateQueries({ queryKey: ["deploy-runs", target?.id] })
  }
  const fail = (e: { response?: { data?: { detail?: string } } }) =>
    setNote({ ok: false, text: e.response?.data?.detail ?? "That did not work." })

  const run = useMutation({
    mutationFn: () => deployNow(target!.id),
    onSuccess: () => { setNote({ ok: true, text: "Deploying — the log updates below." }); refresh() },
    onError: fail,
  })
  const back = useMutation({
    mutationFn: () => rollback(target!.id),
    onSuccess: () => { setNote({ ok: true, text: "Rolling back to the previous release." }); refresh() },
    onError: fail,
  })
  const serve = useMutation({
    mutationFn: () => serveSiteFromDeploy(site.id),
    onSuccess: (r) => { setNote({ ok: true, text: r.message }); refresh() },
    onError: fail,
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <Loader2 size={20} className="animate-spin" />
      </div>
    )
  }

  if (data && !data.can_deploy) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Deploying is not available for this site"
        description={site.server.panel_type
          ? `This site is managed by ${site.server.panel_type}, which owns its web-server `
            + `settings. Deploy through the panel instead.`
          : "Deploying code needs a Linux server we can reach over SSH."}
      />
    )
  }

  if (!target) {
    return (
      <ConnectForm
        siteId={site.id}
        suggested={data?.suggested}
        panel={site.server.panel_type}
        onDone={() => { setNote({ ok: true, text: "Repository connected." }); refresh() }}
      />
    )
  }

  const busy = run.isPending || back.isPending || serve.isPending
  const deployed = !!target.current_release

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-card">
        <div className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
          <div className="min-w-0">
            <p className="flex items-center gap-2 text-sm font-medium text-foreground">
              <GitBranch size={14} className="text-muted-foreground" />
              <span className="truncate">{target.repo}</span>
              <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-caption">
                {target.branch}
              </span>
            </p>
            <p className="mt-0.5 truncate text-small text-muted-foreground">
              Deployed to <span className="font-mono">{target.path}</span>
              {target.current_release && <> · release {target.current_release}</>}
            </p>
          </div>
          <div className="flex gap-2">
            <Button size="sm" disabled={busy} onClick={() => run.mutate()}>
              {run.isPending ? <Loader2 size={14} className="animate-spin" /> : <Rocket size={14} />}
              Deploy now
            </Button>
            {deployed && (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => back.mutate()}>
                <RotateCcw size={14} /> Roll back
              </Button>
            )}
          </div>
        </div>
      </div>

      {note && (
        <p className={`rounded-lg border-l-2 px-3 py-2 text-small ${
          note.ok
            ? "border-emerald-500 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
            : "border-destructive bg-destructive/5 text-destructive"}`}>
          {note.text}
        </p>
      )}

      {/* The step a visitor can see, and the only one that can take the site down — so it
          is separate and asked for, never a side effect of deploying. */}
      {target.serving ? (
        <div className="flex items-start gap-3 rounded-xl border border-border bg-card px-4 py-3">
          <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
          <div>
            <p className="text-sm text-foreground">Visitors are seeing the deployed code</p>
            <p className="mt-0.5 text-small text-muted-foreground">
              Served from <span className="font-mono">{target.served_from}</span>. Every
              deploy from now on goes live the moment it finishes building.
            </p>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4">
          <p className="text-sm font-medium text-foreground">
            Visitors are still seeing the old files
          </p>
          <p className="mt-1 text-small text-muted-foreground">
            {deployed
              ? <>The code is on the server but the site is not serving it yet. This points
                 the web server at <span className="font-mono">{target.served_from}</span>,
                 checks the site still works, and puts it back if it does not.</>
              : <>Deploy once first. Nothing a visitor sees changes until there is a
                 finished release to point at — so a failed first deploy costs nothing.</>}
          </p>
          <Button size="sm" className="mt-3" disabled={busy || !deployed}
                  onClick={() => serve.mutate()}>
            {serve.isPending ? <Loader2 size={13} className="animate-spin" /> : null}
            Serve the site from this code
          </Button>
        </div>
      )}

      <div className="rounded-xl border border-border bg-card">
        <p className="border-b border-border px-4 py-3 text-sm font-medium text-foreground">
          Deploys
        </p>
        {!runs?.runs.length ? (
          <p className="px-4 py-5 text-small text-muted-foreground">Nothing deployed yet.</p>
        ) : (
          runs.runs.slice(0, 8).map((r) => (
            <div key={r.id}
                 className="flex items-baseline justify-between gap-4 border-t border-border px-4 py-2.5 first:border-t-0">
              <span className="text-small text-foreground">
                {r.kind === "rollback" ? "Rolled back" : "Deployed"}
                {r.release && <span className="ml-2 font-mono text-caption text-muted-foreground">
                  {r.release}
                </span>}
                {r.trigger === "push" && (
                  <span className="ml-2 text-caption text-muted-foreground">from a push</span>
                )}
              </span>
              <span className={`text-small ${
                r.status === "success" ? "text-emerald-600 dark:text-emerald-400"
                  : r.status === "failed" ? "text-destructive" : "text-muted-foreground"}`}>
                {r.status === "running" ? "running…" : r.status}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

function ConnectForm({ siteId, suggested, panel, onDone }: {
  siteId: string
  suggested?: { path: string; web_dir: string }
  panel?: string | null
  onDone: () => void
}) {
  const [repo, setRepo] = useState("")
  const [branch, setBranch] = useState("main")
  const [webDir, setWebDir] = useState(suggested?.web_dir ?? "")
  const [error, setError] = useState<string | null>(null)

  const connect = useMutation({
    mutationFn: () => connectSiteDeploy(siteId, { repo, branch, web_dir: webDir }),
    onSuccess: onDone,
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "That repository could not be connected."),
  })

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-sm font-medium text-foreground">Deploy your own code here</p>
      <p className="mt-0.5 text-small text-muted-foreground">
        Connect a Git repository. Each deploy builds in its own folder and only goes live
        when it has finished, so a broken build never reaches visitors.
      </p>
      {panel && (
        <p className="mt-2 rounded-lg border-l-2 border-primary bg-primary/5 px-3 py-2
                      text-caption text-muted-foreground">
          <span className="font-medium text-foreground">This server runs {panel}.</span>{" "}
          Its settings are left alone — we never edit the panel&rsquo;s configuration,
          because it rewrites that file on its own schedule and would undo us. Going live
          instead points the folder {panel} already serves at your deployed code. Your
          current files are moved aside, never deleted.
        </p>
      )}

      <div className="mt-4 space-y-3">
        <div>
          <Label htmlFor="repo">Repository</Label>
          <Input id="repo" value={repo} onChange={(e) => setRepo(e.target.value)}
                 placeholder="git@github.com:you/your-project.git" />
          <p className="mt-1 text-caption text-muted-foreground">
            The server needs read access to it — for a private repository, add its deploy
            key on the server first.
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="branch">Branch</Label>
            <Input id="branch" value={branch} onChange={(e) => setBranch(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="webdir">Web directory</Label>
            <Input id="webdir" value={webDir} onChange={(e) => setWebDir(e.target.value)}
                   placeholder="leave empty for the repository root" />
            <p className="mt-1 text-caption text-muted-foreground">
              Laravel and Symfony serve from <span className="font-mono">public</span>.
            </p>
          </div>
        </div>

        {suggested?.path && (
          <p className="text-caption text-muted-foreground">
            Deploys will live in <span className="font-mono">{suggested.path}</span>, beside
            this site's current files. Nothing visitors see changes until you ask for it.
          </p>
        )}

        {error && (
          <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-destructive">
            {error}
          </p>
        )}

        <Button disabled={!repo.trim() || connect.isPending}
                onClick={() => { setError(null); connect.mutate() }}>
          {connect.isPending ? <Loader2 size={14} className="animate-spin" /> : <GitBranch size={14} />}
          Connect repository
        </Button>
      </div>
    </div>
  )
}

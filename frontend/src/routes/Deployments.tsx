import { useEffect, useMemo, useRef, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Rocket, Loader2, Plus, Trash2, Undo2, GitBranch, Check, Copy, Webhook,
  CircleAlert, History, ShieldCheck,
} from "lucide-react"
import {
  listDeployTargets, createDeployTarget, updateDeployTarget, deleteDeployTarget,
  revealWebhookSecret, listReleases, deployNow, rollback, listDeployRuns, getDeployRun,
  type DeployTarget, type DeployRun, type TargetInput,
} from "@/api/deployments"
import { listServers } from "@/api/servers"
import { Button, EmptyState } from "@/components/ui"
import { cn } from "@/lib/utils"

const BLANK: TargetInput = {
  name: "", repo: "", branch: "main", path: "", environment: "production",
  shared_paths: [], build_commands: [], after_commands: [],
  auto_deploy: false, keep_releases: 5,
}

const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean)
const detail = (e: unknown) =>
  (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail

function Field({ label, hint, children }: {
  label: string; hint?: string; children: React.ReactNode
}) {
  return (
    <label className="block">
      <span className="text-[12.5px] font-medium text-foreground">{label}</span>
      {hint && <span className="ml-2 text-[12px] text-muted-foreground">{hint}</span>}
      <div className="mt-1">{children}</div>
    </label>
  )
}

const inputCls =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none " +
  "focus:border-primary font-mono"

function TargetForm({ target, servers, onDone, onCancel }: {
  target?: DeployTarget
  servers: { id: string; name: string; connection_type: string }[]
  onDone: () => void
  onCancel: () => void
}) {
  const [serverId, setServerId] = useState(target?.server_id ?? servers[0]?.id ?? "")
  const [f, setF] = useState<TargetInput>(target
    ? { ...target, shared_paths: target.shared_paths, build_commands: target.build_commands,
        after_commands: target.after_commands }
    : BLANK)
  const [shared, setShared] = useState((target?.shared_paths ?? []).join("\n"))
  const [build, setBuild] = useState((target?.build_commands ?? []).join("\n"))
  const [after, setAfter] = useState((target?.after_commands ?? []).join("\n"))
  const [secret, setSecret] = useState<string | null>(null)

  const save = useMutation({
    mutationFn: () => {
      const body: TargetInput = {
        ...f, shared_paths: lines(shared), build_commands: lines(build),
        after_commands: lines(after),
      }
      return target ? updateDeployTarget(target.id, body) : createDeployTarget(serverId, body)
    },
    onSuccess: (t) => {
      // The webhook details are only worth showing to someone who asked for push-to-deploy;
      // otherwise this screen hands over a secret for something they never turned on.
      if (!target && t.auto_deploy && t.webhook_secret) setSecret(t.webhook_secret)
      else onDone()
    },
  })

  if (secret) {
    return (
      <div className="rounded-xl border border-border bg-card p-4">
        <h2 className="text-h3 text-foreground">Push-to-deploy is ready</h2>
        <p className="mt-1 text-[12.5px] text-muted-foreground">
          In your repository go to <strong>Settings → Webhooks → Add webhook</strong> and
          paste these two values. The secret is what stops the URL being a public deploy
          button, so copy it now — you can reveal it again later from the target.
        </p>
        <CopyRow label="Payload URL"
          value={`${window.location.origin}/api/deploy/hook/${(save.data as DeployTarget).id}`} />
        <CopyRow label="Secret" value={secret} />
        <p className="mt-2 text-[12px] text-muted-foreground">
          Content type <code className="font-mono">application/json</code>, just the push
          event.
        </p>
        <div className="mt-3"><Button onClick={onDone}>Done</Button></div>
      </div>
    )
  }

  const err = detail(save.error)
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <h2 className="text-h3 text-foreground">
        {target ? "Edit deploy target" : "New deploy target"}
      </h2>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Field label="Name">
          <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })}
            placeholder="Marketing site" className={cn(inputCls, "font-sans")} />
        </Field>
        <Field label="Server">
          <select value={serverId} disabled={!!target}
            onChange={(e) => setServerId(e.target.value)}
            className={cn(inputCls, "font-sans disabled:opacity-60")}>
            {servers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </Field>
        <Field label="Repository">
          <input value={f.repo} onChange={(e) => setF({ ...f, repo: e.target.value })}
            placeholder="https://github.com/you/app.git" className={inputCls} />
        </Field>
        <Field label="Branch">
          <input value={f.branch} onChange={(e) => setF({ ...f, branch: e.target.value })}
            placeholder="main" className={inputCls} />
        </Field>
        <Field label="Deploy into" hint="a folder of its own">
          <input value={f.path} onChange={(e) => setF({ ...f, path: e.target.value })}
            placeholder="/var/www/app" className={inputCls} />
        </Field>
        <Field label="Environment">
          <select value={f.environment}
            onChange={(e) => setF({ ...f, environment: e.target.value })}
            className={cn(inputCls, "font-sans")}>
            <option value="production">Production</option>
            <option value="staging">Staging</option>
          </select>
        </Field>
        <Field label="Files to keep between deploys" hint="one per line">
          <textarea value={shared} onChange={(e) => setShared(e.target.value)} rows={3}
            placeholder={".env\nstorage/uploads"} className={inputCls} />
        </Field>
        <Field label="Build commands" hint="one per line, run before going live">
          <textarea value={build} onChange={(e) => setBuild(e.target.value)} rows={3}
            placeholder={"npm ci\nnpm run build"} className={inputCls} />
        </Field>
        <Field label="After going live" hint="restarts, cache warming">
          <textarea value={after} onChange={(e) => setAfter(e.target.value)} rows={2}
            placeholder="sudo systemctl restart app" className={inputCls} />
        </Field>
        <div className="space-y-3">
          <Field label="Releases to keep">
            <input type="number" min={2} max={20} value={f.keep_releases}
              onChange={(e) => setF({ ...f, keep_releases: Number(e.target.value) })}
              className={cn(inputCls, "font-sans")} />
          </Field>
          <label className="flex items-start gap-2 text-[12.5px] text-foreground">
            <input type="checkbox" checked={f.auto_deploy} className="mt-0.5"
              onChange={(e) => setF({ ...f, auto_deploy: e.target.checked })} />
            <span>
              Deploy on every push to <strong>{f.branch || "main"}</strong>
              <span className="block text-[12px] text-muted-foreground">
                We give you a signed webhook URL for your repository.
              </span>
            </span>
          </label>
        </div>
      </div>
      <p className="mt-3 rounded-lg bg-muted/50 px-3 py-2 text-[12px] text-muted-foreground">
        <ShieldCheck size={13} className="mr-1 inline align-[-2px]" />
        Each deploy is built in a new folder and only goes live once it has finished
        building, so a broken build leaves your site running exactly as it was.
      </p>
      {err && <p className="mt-2 text-[12.5px] text-red-600 dark:text-red-400">{err}</p>}
      <div className="mt-3 flex gap-2">
        <Button disabled={!f.name || !f.repo || !f.path || !serverId || save.isPending}
          onClick={() => save.mutate()}>
          {save.isPending && <Loader2 size={14} className="animate-spin" />}
          {target ? "Save changes" : "Create target"}
        </Button>
        <Button variant="ghost" onClick={onCancel}>Cancel</Button>
      </div>
    </div>
  )
}

function CopyRow({ label, value }: { label: string; value: string }) {
  const [done, setDone] = useState(false)
  return (
    <div className="mt-2">
      <span className="text-[12px] text-muted-foreground">{label}</span>
      <div className="mt-1 flex items-center gap-2">
        <code className="flex-1 overflow-x-auto rounded-lg border border-border bg-muted/40
                         px-3 py-2 font-mono text-[12.5px]">{value}</code>
        <Button variant="outline" size="sm" onClick={() => {
          navigator.clipboard.writeText(value); setDone(true); setTimeout(() => setDone(false), 1500)
        }}>
          {done ? <Check size={13} /> : <Copy size={13} />}
        </Button>
      </div>
    </div>
  )
}

function statusTone(s: string | null) {
  if (s === "success") return "text-emerald-600 dark:text-emerald-400"
  if (s === "failed") return "text-red-600 dark:text-red-400"
  if (s === "rolled-back") return "text-amber-600 dark:text-amber-400"
  return "text-muted-foreground"
}

function RunLog({ run }: { run: DeployRun }) {
  const box = useRef<HTMLPreElement>(null)
  useEffect(() => { box.current?.scrollTo({ top: box.current.scrollHeight }) }, [run.log])
  return (
    <div className="mt-3">
      <div className="flex items-center gap-2 text-[12.5px]">
        <span className={cn("font-medium", statusTone(run.status))}>
          {run.status === "running" ? "Deploying…" : run.status}
        </span>
        {run.release && <span className="font-mono text-muted-foreground">{run.release}</span>}
        {run.failed_step && (
          <span className="text-red-600 dark:text-red-400">
            <CircleAlert size={12} className="mr-1 inline align-[-2px]" />
            stopped at “{run.failed_step}”
          </span>
        )}
      </div>
      <pre ref={box} className="mt-2 max-h-72 overflow-auto rounded-lg bg-slate-950 p-3
                                font-mono text-[12px] leading-relaxed text-slate-200">
        {run.log || "Starting…"}
      </pre>
    </div>
  )
}

function TargetPanel({ target, onEdit }: { target: DeployTarget; onEdit: () => void }) {
  const qc = useQueryClient()
  const [runId, setRunId] = useState<string | null>(null)
  const [secret, setSecret] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const releases = useQuery({
    queryKey: ["deploy-releases", target.id],
    queryFn: () => listReleases(target.id),
    retry: false,
  })
  const runs = useQuery({
    queryKey: ["deploy-runs", target.id],
    queryFn: () => listDeployRuns(target.id),
  })
  // A deploy takes minutes, so the log is polled while it moves and the polling stops
  // the moment the run settles. It keeps polling on a hidden tab: someone who starts a
  // deploy and switches away should come back to the finished log, not to a snapshot
  // frozen at the moment they left.
  const [settled, setSettled] = useState(false)
  const live = useQuery({
    queryKey: ["deploy-run", runId],
    queryFn: () => getDeployRun(runId!),
    enabled: !!runId,
    refetchInterval: settled ? false : 2000,
    refetchIntervalInBackground: true,
  })
  useEffect(() => {
    if (live.data && live.data.status !== "running") {
      setSettled(true)
      qc.invalidateQueries({ queryKey: ["deploy-targets"] })
      qc.invalidateQueries({ queryKey: ["deploy-releases", target.id] })
      qc.invalidateQueries({ queryKey: ["deploy-runs", target.id] })
    }
  }, [live.data?.status])   // eslint-disable-line react-hooks/exhaustive-deps

  const start = (id: string) => { setSettled(false); setRunId(id) }
  const go = useMutation({
    mutationFn: () => deployNow(target.id),
    onSuccess: (r) => start(r.run_id),
  })
  const back = useMutation({
    mutationFn: () => rollback(target.id),
    onSuccess: (r) => start(r.run_id),
  })
  const remove = useMutation({
    mutationFn: () => deleteDeployTarget(target.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["deploy-targets"] }),
  })

  const busy = live.data?.status === "running" || go.isPending || back.isPending
  const shown = live.data ?? runs.data?.runs[0]

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-h3 text-foreground">{target.name}</h3>
          <p className="mt-0.5 truncate font-mono text-[12.5px] text-muted-foreground">
            {target.repo}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1
                          text-[12px] text-muted-foreground">
            <span><GitBranch size={12} className="mr-1 inline align-[-2px]" />{target.branch}</span>
            <span className="font-mono">{target.path}</span>
            <span>{target.server_name}</span>
            {target.environment === "staging" && (
              <span className="rounded bg-amber-500/15 px-1.5 py-0.5 font-medium
                               text-amber-700 dark:text-amber-400">staging</span>
            )}
            {target.auto_deploy && (
              <span className="text-primary">
                <Webhook size={12} className="mr-1 inline align-[-2px]" />deploys on push
              </span>
            )}
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2">
          <Button size="sm" disabled={busy} onClick={() => go.mutate()}>
            {busy ? <Loader2 size={13} className="animate-spin" /> : <Rocket size={13} />}
            Deploy now
          </Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => back.mutate()}>
            <Undo2 size={13} />Roll back
          </Button>
          <Button size="sm" variant="ghost" onClick={onEdit}>Edit</Button>
          <Button size="sm" variant="ghost"
            onClick={() => confirmDelete ? remove.mutate() : setConfirmDelete(true)}>
            <Trash2 size={13} className={confirmDelete ? "text-red-500" : ""} />
            {confirmDelete ? "Sure?" : ""}
          </Button>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12.5px]">
        <span className="text-muted-foreground">
          Live now:{" "}
          <span className="font-mono text-foreground">
            {releases.data?.current ?? target.current_release ?? "nothing yet"}
          </span>
        </span>
        {target.last_status && (
          <span className={statusTone(target.last_status)}>last deploy {target.last_status}</span>
        )}
        {releases.data && (
          <span className="text-muted-foreground">
            <History size={12} className="mr-1 inline align-[-2px]" />
            {releases.data.releases.length} release
            {releases.data.releases.length === 1 ? "" : "s"} kept
          </span>
        )}
        {releases.isError && (
          <span className="text-muted-foreground">
            (couldn’t read the server — nothing deployed there yet?)
          </span>
        )}
      </div>

      {(detail(go.error) || detail(back.error)) && (
        <p className="mt-2 text-[12.5px] text-red-600 dark:text-red-400">
          {detail(go.error) || detail(back.error)}
        </p>
      )}

      {target.auto_deploy && (
        <div className="mt-3">
          {secret
            ? <CopyRow label="Webhook secret" value={secret} />
            : <button className="text-[12px] text-primary hover:underline"
                onClick={async () => setSecret((await revealWebhookSecret(target.id)).webhook_secret)}>
                Show webhook secret
              </button>}
        </div>
      )}

      {shown && <RunLog run={shown} />}

      {!!runs.data?.runs.length && (
        <details className="mt-3">
          <summary className="cursor-pointer text-[12.5px] text-muted-foreground">
            Deploy history
          </summary>
          <ul className="mt-2 space-y-1">
            {runs.data.runs.map((r) => (
              <li key={r.id} className="flex items-center gap-3 text-[12.5px]">
                <span className={cn("w-20 shrink-0 font-medium", statusTone(r.status))}>
                  {r.status}
                </span>
                <span className="font-mono text-muted-foreground">{r.release}</span>
                <span className="text-muted-foreground">
                  {r.kind === "rollback" ? "rollback" : r.trigger === "push" ? "on push" : "manual"}
                </span>
                <span className="ml-auto text-muted-foreground">
                  {r.started_at ? new Date(r.started_at).toLocaleString() : ""}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

export default function Deployments() {
  const qc = useQueryClient()
  const [form, setForm] = useState<{ open: boolean; target?: DeployTarget }>({ open: false })

  const targets = useQuery({ queryKey: ["deploy-targets"], queryFn: listDeployTargets })
  const servers = useQuery({ queryKey: ["servers"], queryFn: listServers })
  // Deploys run commands over SSH, so anything else cannot host one.
  const deployable = useMemo(
    () => (servers.data ?? []).filter((s) => s.connection_type === "ssh"),
    [servers.data])

  const close = () => { setForm({ open: false }); qc.invalidateQueries({ queryKey: ["deploy-targets"] }) }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-h1 text-foreground">Deployments</h1>
          <p className="mt-1 text-[13px] text-muted-foreground">
            Ship a repository to a server. Each deploy builds in its own folder and only
            goes live when it has finished, so you can always go straight back.
          </p>
        </div>
        {!form.open && !!deployable.length && (
          <Button onClick={() => setForm({ open: true })}><Plus size={14} />New target</Button>
        )}
      </div>

      {form.open && (
        <TargetForm target={form.target} servers={deployable}
          onDone={close} onCancel={() => setForm({ open: false })} />
      )}

      {targets.isLoading && (
        <div className="flex justify-center py-10">
          <Loader2 className="animate-spin text-muted-foreground" />
        </div>
      )}

      {!targets.isLoading && !targets.data?.count && !form.open && (
        <EmptyState
          icon={Rocket}
          title="No deploy targets yet"
          description={deployable.length
            ? "Point one at a repository and a folder on a server, and pushing to your branch can deploy it."
            : "Add a server you connect to over SSH first — deploys run commands on the server."}
          action={deployable.length
            ? <Button onClick={() => setForm({ open: true })}><Plus size={14} />New target</Button>
            : undefined}
        />
      )}

      <div className="space-y-3">
        {targets.data?.targets.map((t) => (
          <TargetPanel key={t.id} target={t} onEdit={() => setForm({ open: true, target: t })} />
        ))}
      </div>
    </div>
  )
}

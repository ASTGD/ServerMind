import { useState } from "react"
import { useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  CircleCheck, CircleAlert, Loader2, Play, Plus, Repeat, RotateCw, Square, Trash2, X,
} from "lucide-react"
import {
  actOnSiteDaemon, addSiteDaemon, getSiteDaemons, type SiteDaemon, type SiteDetail,
} from "@/api/sites"
import { Button, EmptyState, Input, Label } from "@/components/ui"

/**
 * The processes kept running for this site.
 *
 * Different from Scheduled jobs on purpose: those run at a time and finish, these run
 * continuously and are started again if they stop. A Laravel queue worker is the common
 * case — without it the work an app queues up simply never happens, and nothing says so.
 *
 * Only this site's own processes can be touched here. The server's Services screen manages
 * everything else on the machine, which is where a wrong name would stop nginx.
 */
export default function SiteDaemons() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  const qc = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; message: string; log?: string } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["site-daemons", site.id],
    queryFn: () => getSiteDaemons(site.id),
  })
  const reload = () => qc.invalidateQueries({ queryKey: ["site-daemons", site.id] })
  const said = (e: unknown, fallback: string) => setNote({
    ok: false,
    message: (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      || fallback,
  })

  const add = useMutation({
    mutationFn: (body: { name: string; command: string }) => addSiteDaemon(site.id, body),
    onSuccess: (r) => { setAdding(false); setNote(r); reload() },
    onError: (e) => said(e, "That could not be set up."),
  })

  const act = useMutation({
    mutationFn: ({ unit, action }: { unit: string; action: "start" | "stop" | "restart" | "remove" }) =>
      actOnSiteDaemon(site.id, unit, action),
    onSuccess: () => { setNote(null); reload() },
    onError: (e) => said(e, "That did not work."),
  })

  if (isLoading) {
    return <div className="flex justify-center py-16 text-muted-foreground">
      <Loader2 size={20} className="animate-spin" /></div>
  }

  const daemons = data?.daemons ?? []
  const suggested = data?.suggested ?? null
  const busy = add.isPending || act.isPending

  return (
    <div className="space-y-3">
      {note && (
        <div className={`rounded-lg border-l-2 px-3 py-2 text-small text-foreground ${
          note.ok ? "border-emerald-500 bg-emerald-500/5" : "border-destructive bg-destructive/5"}`}>
          {note.message}
          {/* Its own log is the only thing that says why it did not stay up. */}
          {note.log && (
            <pre className="mt-2 overflow-x-auto rounded bg-muted/60 p-2 font-mono text-caption">
              {note.log}
            </pre>
          )}
        </div>
      )}

      {suggested && (
        <div className="rounded-xl border border-primary/30 bg-primary/5 p-3">
          <p className="text-sm font-medium text-foreground">{suggested.title}</p>
          <p className="mt-1 text-small text-muted-foreground">{suggested.why}</p>
          <p className="mt-1.5 break-all font-mono text-caption text-muted-foreground">
            {suggested.command}
          </p>
          <Button size="sm" className="mt-2" disabled={busy}
            onClick={() => add.mutate({ name: suggested.name, command: suggested.command })}>
            {add.isPending ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
            Keep this running
          </Button>
        </div>
      )}

      {daemons.length > 0 ? (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          {daemons.map((dm) => (
            <DaemonRow key={dm.unit} daemon={dm} busy={busy}
              onAct={(action) => {
                if (action === "remove"
                    && !confirm(`Stop and remove “${dm.name}”?\n\n${dm.command}`)) return
                act.mutate({ unit: dm.unit, action })
              }} />
          ))}
        </div>
      ) : !suggested && (
        <EmptyState
          icon={Repeat}
          title="Nothing is being kept running for this site"
          description="Some sites need a process that runs all the time — a queue worker, a websocket server, an app that is not a set of PHP files. Anything added here is started again if it stops, and after a reboot."
        />
      )}

      {adding ? (
        <NewDaemon busy={busy} workingDir={data?.working_dir ?? ""}
          onCancel={() => setAdding(false)}
          onAdd={(name, command) => add.mutate({ name, command })} />
      ) : (
        <Button size="sm" variant="outline" onClick={() => { setAdding(true); setNote(null) }}>
          <Plus size={13} /> Keep something running
        </Button>
      )}
    </div>
  )
}

function DaemonRow({ daemon, busy, onAct }: {
  daemon: SiteDaemon
  busy: boolean
  onAct: (a: "start" | "stop" | "restart" | "remove") => void
}) {
  return (
    <div className="flex flex-wrap items-start gap-3 border-t border-border px-4 py-3 first:border-t-0">
      {daemon.running
        ? <CircleCheck size={14} className="mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
        : <CircleAlert size={14} className="mt-0.5 shrink-0 text-destructive" />}
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-sm text-foreground">
          {daemon.name}
          <span className={`text-caption ${daemon.running
            ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`}>
            {daemon.running ? "running" : daemon.state}
          </span>
          {!daemon.at_boot && (
            <span className="text-caption text-amber-700 dark:text-amber-300">
              will not start after a reboot
            </span>
          )}
        </p>
        <p className="mt-0.5 break-all font-mono text-caption text-muted-foreground">
          {daemon.command}
        </p>
      </div>
      <div className="flex shrink-0 gap-1">
        {daemon.running ? (
          <>
            <Button size="sm" variant="ghost" disabled={busy} title="Restart"
              onClick={() => onAct("restart")}><RotateCw size={13} /></Button>
            <Button size="sm" variant="ghost" disabled={busy} title="Stop"
              onClick={() => onAct("stop")}><Square size={13} /></Button>
          </>
        ) : (
          <Button size="sm" variant="ghost" disabled={busy} title="Start"
            onClick={() => onAct("start")}><Play size={13} /></Button>
        )}
        <Button size="sm" variant="ghost" disabled={busy} title="Remove"
          onClick={() => onAct("remove")}><Trash2 size={13} /></Button>
      </div>
    </div>
  )
}

function NewDaemon({ busy, workingDir, onAdd, onCancel }: {
  busy: boolean
  workingDir: string
  onAdd: (name: string, command: string) => void
  onCancel: () => void
}) {
  const [name, setName] = useState("")
  const [command, setCommand] = useState("")

  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-foreground">Something to keep running</p>
        <Button size="sm" variant="ghost" onClick={onCancel}><X size={13} /></Button>
      </div>
      <div className="mt-2 grid gap-2 sm:grid-cols-[180px_1fr]">
        <div>
          <Label htmlFor="dm-name">Call it</Label>
          <Input id="dm-name" value={name} placeholder="queue-worker"
            onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <Label htmlFor="dm-cmd">Run this</Label>
          <Input id="dm-cmd" value={command} className="font-mono"
            placeholder="php artisan queue:work"
            onChange={(e) => setCommand(e.target.value)} />
        </div>
      </div>
      <p className="mt-1.5 text-caption text-muted-foreground">
        It runs in <span className="font-mono">{workingDir || "this site's folder"}</span>,
        as the account that owns this site's files, and is started again if it stops.
      </p>
      <Button size="sm" className="mt-2" disabled={busy || !name.trim() || !command.trim()}
        onClick={() => onAdd(name.trim(), command.trim())}>
        {busy ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
        Keep it running
      </Button>
    </div>
  )
}

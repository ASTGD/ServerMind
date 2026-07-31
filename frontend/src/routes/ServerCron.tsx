import { useState } from "react"
import { useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Clock, Loader2, Plus, Trash2, Zap } from "lucide-react"
import {
  addCronJob, getCron, removeCronJob,
  type CronJob, type CronPreset, type CronUser,
} from "@/api/cron"
import { Button, EmptyState } from "@/components/ui"
import type { Server } from "@/types"

/**
 * The server's own scheduled jobs.
 *
 * Not the same as ServerAlly's scheduled tasks, and the page says so: those run from here
 * and we keep their history, while these run on the server whether or not this product is
 * up. Laravel and WordPress both need the second kind.
 *
 * Every change sends back the fingerprint of the list being shown. If someone else edited
 * the crontab in between, the server refuses rather than overwriting — because what would
 * be overwritten is usually a backup job nobody misses until they need it.
 */
export default function ServerCron() {
  const { server } = useOutletContext<{ server: Server }>()
  const qc = useQueryClient()
  const [adding, setAdding] = useState<{ user: string; preset?: CronPreset } | null>(null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["cron", server.id],
    queryFn: () => getCron(server.id),
  })

  const refresh = () => qc.invalidateQueries({ queryKey: ["cron", server.id] })

  const remove = useMutation({
    mutationFn: (v: { user: string; job: CronJob; expect: string }) =>
      removeCronJob(server.id, { user: v.user, raw_line: v.job.raw, expect: v.expect }),
    onSuccess: () => { setNote({ ok: true, text: "That job is no longer scheduled." }); refresh() },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setNote({ ok: false, text: e.response?.data?.detail ?? "The job could not be removed." }),
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <Loader2 size={20} className="animate-spin" />
      </div>
    )
  }

  const users = data?.users ?? []
  const total = users.reduce((n, u) => n + u.jobs.length, 0)

  return (
    <div className="space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-h2 text-foreground">Scheduled jobs</h2>
          <p className="mt-0.5 text-small text-muted-foreground">
            Work this server runs on a timer, by itself — including anything set up before
            you started using ServerAlly.
          </p>
        </div>
        {users.length > 0 && (
          <Button size="sm" onClick={() => setAdding({ user: users[0].user })}>
            <Plus size={14} /> New job
          </Button>
        )}
      </div>

      {note && (
        <p
          className={`rounded-lg border-l-2 px-3 py-2 text-small ${
            note.ok
              ? "border-emerald-500 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
              : "border-destructive bg-destructive/5 text-destructive"
          }`}
        >
          {note.text}
        </p>
      )}

      {!data?.reachable && (
        <EmptyState
          icon={AlertTriangle}
          title="We could not look at this server"
          description="It did not answer. Check it is online, then try again."
        />
      )}

      {data?.reachable && total === 0 && (
        <div className="rounded-xl border border-border bg-card p-5">
          <p className="text-sm font-medium text-foreground">Nothing scheduled yet</p>
          <p className="mt-0.5 text-small text-muted-foreground">
            Two jobs are worth adding if you run one of these:
          </p>
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            {(data.presets ?? []).map((preset) => (
              <button
                key={preset.id}
                onClick={() => setAdding({ user: users[0]?.user ?? "root", preset })}
                className="rounded-lg border border-border p-3 text-left hover:border-primary/50 hover:bg-accent"
              >
                <p className="flex items-center gap-1.5 text-sm font-medium text-foreground">
                  <Zap size={13} className="text-primary" /> {preset.label}
                </p>
                <p className="mt-0.5 text-caption text-muted-foreground">{preset.blurb}</p>
              </button>
            ))}
          </div>
        </div>
      )}

      {users.map((entry) => (
        <UserCard
          key={entry.user}
          entry={entry}
          onAdd={() => setAdding({ user: entry.user })}
          onRemove={(job) =>
            remove.mutate({ user: entry.user, job, expect: entry.fingerprint })}
        />
      ))}

      {adding && (
        <AddDialog
          serverId={server.id}
          user={adding.user}
          users={users.map((u) => u.user)}
          preset={adding.preset}
          expect={users.find((u) => u.user === adding.user)?.fingerprint}
          presets={data?.presets ?? []}
          onClose={() => setAdding(null)}
          onDone={(description) => {
            setAdding(null)
            setNote({ ok: true, text: `Scheduled — ${description.toLowerCase()}.` })
            refresh()
          }}
        />
      )}
    </div>
  )
}

function UserCard({ entry, onAdd, onRemove }: {
  entry: CronUser
  onAdd: () => void
  onRemove: (job: CronJob) => void
}) {
  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <p className="text-sm font-medium text-foreground">Runs as {entry.user}</p>
          <p className="text-caption text-muted-foreground">
            {entry.jobs.length === 0
              ? "Nothing scheduled"
              : `${entry.jobs.length} job${entry.jobs.length === 1 ? "" : "s"}`}
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={onAdd}>
          <Plus size={14} /> Add
        </Button>
      </div>

      {entry.jobs.length === 0 ? (
        <p className="px-4 py-5 text-small text-muted-foreground">
          This account has no scheduled jobs.
        </p>
      ) : (
        <ul className="divide-y divide-border">
          {entry.jobs.map((job, i) => (
            <li key={`${job.raw}-${i}`} className="flex items-start gap-3 px-4 py-3">
              <Clock size={14} className="mt-1 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="text-sm text-foreground">
                  {job.description || job.schedule || "Schedule not recognised"}
                </p>
                <p className="mt-0.5 break-all font-mono text-caption text-muted-foreground">
                  {job.command}
                </p>
                {job.note && (
                  <p className="mt-0.5 text-caption text-muted-foreground/80">{job.note}</p>
                )}
                {/* Shown rather than hidden: a job we cannot read is still a job that
                    runs, and a screen that omits it would be lying. */}
                {!job.parsed && (
                  <p className="mt-1 text-caption text-amber-600 dark:text-amber-400">
                    We could not read this line, so it is shown exactly as it is written.
                  </p>
                )}
              </div>
              <button
                onClick={() => onRemove(job)}
                className="shrink-0 rounded-md p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                title="Remove this job"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const COMMON = [
  { value: "*/5 * * * *", label: "Every 5 minutes" },
  { value: "*/15 * * * *", label: "Every 15 minutes" },
  { value: "0 * * * *", label: "Every hour" },
  { value: "0 2 * * *", label: "Every day at 2:00 am" },
  { value: "0 4 * * 0", label: "Every Sunday at 4:00 am" },
  { value: "0 0 1 * *", label: "The first day of every month" },
  { value: "* * * * *", label: "Every minute" },
]

function AddDialog({ serverId, user, users, preset, presets, expect, onClose, onDone }: {
  serverId: string
  user: string
  users: string[]
  preset?: CronPreset
  presets: CronPreset[]
  expect?: string
  onClose: () => void
  onDone: (description: string) => void
}) {
  const [runAs, setRunAs] = useState(user)
  const [schedule, setSchedule] = useState(preset?.schedule ?? "0 2 * * *")
  const [custom, setCustom] = useState(false)
  const [path, setPath] = useState("")
  const [command, setCommand] = useState(preset ? "" : "")
  const [note, setNote] = useState(preset?.label ?? "")
  const [chosen, setChosen] = useState<CronPreset | undefined>(preset)
  const [error, setError] = useState<string | null>(null)

  const finalCommand = chosen ? chosen.command.replace("{path}", path.trim()) : command

  const add = useMutation({
    mutationFn: () => addCronJob(serverId, {
      user: runAs, schedule, command: finalCommand, note, expect,
    }),
    onSuccess: (r) => onDone(r.description),
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "The job could not be scheduled."),
  })

  function pick(p: CronPreset | undefined) {
    setChosen(p)
    setError(null)
    if (p) { setSchedule(p.schedule); setNote(p.label) } else { setNote("") }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-16">
      <div className="w-full max-w-lg rounded-xl border border-border bg-card p-5 shadow-xl">
        <h3 className="text-h3 text-foreground">New scheduled job</h3>
        <p className="mt-0.5 text-small text-muted-foreground">
          This runs on the server itself, on a timer.
        </p>

        <form
          onSubmit={(e) => { e.preventDefault(); setError(null); add.mutate() }}
          className="mt-4 space-y-3"
        >
          <div className="flex flex-wrap gap-2">
            {presets.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => pick(chosen?.id === p.id ? undefined : p)}
                className={`rounded-full border px-3 py-1 text-caption ${
                  chosen?.id === p.id
                    ? "border-primary bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:bg-accent"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          {chosen && (
            <div className="rounded-lg border border-border bg-muted/40 p-3">
              <p className="text-caption text-muted-foreground">{chosen.blurb}</p>
              <label className="mt-2 block text-caption text-muted-foreground">
                {chosen.needs_path}
              </label>
              <input
                value={path}
                onChange={(e) => setPath(e.target.value)}
                placeholder="/var/www/shop.example.com"
                required
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground"
              />
            </div>
          )}

          {users.length > 1 && (
            <div>
              <label className="text-caption text-muted-foreground">Run as</label>
              <select
                value={runAs}
                onChange={(e) => setRunAs(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground"
              >
                {users.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
          )}

          <div>
            <label className="text-caption text-muted-foreground">When</label>
            {custom ? (
              <input
                value={schedule}
                onChange={(e) => setSchedule(e.target.value)}
                required
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground"
              />
            ) : (
              <select
                value={schedule}
                onChange={(e) => setSchedule(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground"
              >
                {COMMON.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                {!COMMON.some((o) => o.value === schedule) && (
                  <option value={schedule}>{schedule}</option>
                )}
              </select>
            )}
            <button
              type="button"
              onClick={() => setCustom(!custom)}
              className="mt-1 text-caption text-muted-foreground underline-offset-2 hover:underline"
            >
              {custom ? "Choose from the list instead" : "Write a cron schedule myself"}
            </button>
          </div>

          {!chosen && (
            <div>
              <label className="text-caption text-muted-foreground">Command to run</label>
              <input
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                placeholder="/usr/local/bin/backup.sh"
                required
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground"
              />
            </div>
          )}

          <div>
            <label className="text-caption text-muted-foreground">
              What is this for? (optional)
            </label>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="nightly database backup"
              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground"
            />
          </div>

          {error && (
            <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-destructive">
              {error}
            </p>
          )}

          <div className="flex items-center gap-2 pt-1">
            <Button type="submit" disabled={add.isPending || !finalCommand.trim()}>
              {add.isPending ? "Scheduling…" : "Schedule it"}
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  )
}

import { useState } from "react"
import { Link, useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Clock, Loader2, Plus, Sparkles, Trash2, X } from "lucide-react"
import {
  addSiteCron, getSiteCron, removeSiteCron, type SiteCronJob, type SiteDetail,
} from "@/api/sites"
import { Button, EmptyState, Input, Label } from "@/components/ui"

/**
 * The scheduled jobs that belong to this site.
 *
 * The crontab is the server's, so this is a filtered view of it — and it says so, because
 * hiding that would make someone think deleting a job here could not affect anything else.
 *
 * Adding is scoped the same way. Which account runs a job is decided on the server, from
 * whoever owns the site's files, rather than offered as a choice: a Laravel scheduler run
 * as root leaves root-owned files in storage/ and the site breaks days later.
 */
export default function SiteCron() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  const qc = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [error, setError] = useState("")

  const { data, isLoading } = useQuery({
    queryKey: ["site-cron", site.id],
    queryFn: () => getSiteCron(site.id),
  })
  const reload = () => qc.invalidateQueries({ queryKey: ["site-cron", site.id] })
  // Axios gives us an Error; the useful sentence is the API's `detail` underneath it.
  const said = (e: unknown, fallback: string) =>
    setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
             || fallback)

  const add = useMutation({
    mutationFn: (body: { schedule: string; command: string }) =>
      addSiteCron(site.id, { ...body, expect: data?.jobs[0]?.fingerprint ?? null }),
    onSuccess: () => { setAdding(false); setError(""); reload() },
    onError: (e) => said(e, "That job could not be scheduled."),
  })

  const remove = useMutation({
    mutationFn: (job: SiteCronJob) =>
      removeSiteCron(site.id, {
        user: job.user, raw_line: job.raw, expect: job.fingerprint ?? null,
      }),
    onSuccess: () => { setError(""); reload() },
    onError: (e) => said(e, "That job could not be removed."),
  })

  if (isLoading) {
    return <div className="flex justify-center py-12 text-muted-foreground">
      <Loader2 size={18} className="animate-spin" /></div>
  }

  const jobs = data?.jobs ?? []
  const suggested = data?.suggested ?? null
  const busy = add.isPending || remove.isPending

  return (
    <div className="space-y-3">
      {error && (
        <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-foreground">
          {error}
        </p>
      )}

      {/* What this application needs and has not got. Withheld once something is doing
          the job, so it is an offer once rather than a permanent nag. */}
      {suggested && (
        <div className="rounded-xl border border-primary/30 bg-primary/5 p-3">
          <p className="flex items-center gap-2 text-sm font-medium text-foreground">
            <Sparkles size={14} className="text-primary" /> {suggested.title}
          </p>
          <p className="mt-1 text-small text-muted-foreground">{suggested.why}</p>
          <p className="mt-1.5 break-all font-mono text-caption text-muted-foreground">
            {suggested.schedule} · {suggested.command}
          </p>
          <Button size="sm" className="mt-2" disabled={busy}
            onClick={() => add.mutate({
              schedule: suggested.schedule, command: suggested.command,
            })}>
            {add.isPending ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
            Add this job
          </Button>
        </div>
      )}

      {jobs.length > 0 ? (
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
              <Button size="sm" variant="ghost" disabled={busy} title="Remove this job"
                onClick={() => {
                  if (confirm(`Stop running this job?\n\n${job.command}`)) remove.mutate(job)
                }}>
                <Trash2 size={13} />
              </Button>
            </div>
          ))}
        </div>
      ) : !suggested && (
        <EmptyState
          icon={Clock}
          title="Nothing scheduled for this site"
          description="A scheduled job runs on its own on a timer — sending a nightly report, clearing old files, whatever this site needs doing without somebody visiting it."
        />
      )}

      {adding ? (
        <CustomJob
          busy={busy}
          onCancel={() => { setAdding(false); setError("") }}
          onAdd={(schedule, command) => add.mutate({ schedule, command })}
        />
      ) : (
        <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
          <Plus size={13} /> Add a job
        </Button>
      )}

      <p className="px-1 text-caption text-muted-foreground">
        These are the server's scheduled jobs that mention this site.{" "}
        <Link to={`/servers/${site.server.id}/cron`}
          className="text-muted-foreground underline hover:text-foreground">
          Every job on this server →
        </Link>
      </p>
    </div>
  )
}

/** Anything the suggestion does not cover. Validated on the server, in one place. */
function CustomJob({ busy, onAdd, onCancel }: {
  busy: boolean
  onAdd: (schedule: string, command: string) => void
  onCancel: () => void
}) {
  const [schedule, setSchedule] = useState("0 3 * * *")
  const [command, setCommand] = useState("")

  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-foreground">A job of your own</p>
        <Button size="sm" variant="ghost" onClick={onCancel}><X size={13} /></Button>
      </div>
      <div className="mt-2 grid gap-2 sm:grid-cols-[180px_1fr]">
        <div>
          <Label htmlFor="cron-schedule">When</Label>
          <Input id="cron-schedule" value={schedule} className="font-mono"
            onChange={(e) => setSchedule(e.target.value)} placeholder="0 3 * * *" />
        </div>
        <div>
          <Label htmlFor="cron-command">Run this</Label>
          <Input id="cron-command" value={command} className="font-mono"
            onChange={(e) => setCommand(e.target.value)}
            placeholder="cd /var/www/example.com && php do-something.php" />
        </div>
      </div>
      <p className="mt-1.5 text-caption text-muted-foreground">
        Five fields: minute, hour, day of month, month, day of week. It runs as the account
        that owns this site's files.
      </p>
      <Button size="sm" className="mt-2" disabled={busy || !command.trim()}
        onClick={() => onAdd(schedule.trim(), command.trim())}>
        {busy ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
        Schedule it
      </Button>
    </div>
  )
}

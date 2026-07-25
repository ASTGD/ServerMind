import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import {
  Plane, Plus, Trash2, Play, Loader2, X, CheckCircle2, PauseCircle, AlertTriangle, Clock,
} from "lucide-react"
import {
  listAutopilotTasks, createAutopilotTask, deleteAutopilotTask, runAutopilotTask,
  updateAutopilotTask, type AutopilotTask, type AutopilotBody, type AutopilotPolicy,
} from "@/api/autopilot"
import { parseSchedule } from "@/api/scheduler"
import { Button } from "@/components/ui"

const input =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
const label = "mb-1 block text-xs font-medium text-muted-foreground"

/** The policy is the whole feature — describe each one in the owner's words. */
const POLICIES: { value: AutopilotPolicy; title: string; detail: string }[] = [
  {
    value: "report_only",
    title: "Look and tell me",
    detail: "Ally checks and reports. It will not change anything.",
  },
  {
    value: "safe_fixes",
    title: "Fix ordinary problems",
    detail: "Ally repairs everyday things (like restarting a stopped service) and stops to ask about risky ones.",
  },
  {
    value: "full",
    title: "Fix anything allowed",
    detail: "Ally proceeds on anything the safety rules permit. Dangerous commands are still always blocked.",
  },
]

const EXAMPLES = [
  "Check the site is loading and fix it if it is not",
  "Look for anything suspicious and tell me what you find",
  "Check disk space and clean up old logs if it is getting full",
  "Make sure nginx, MySQL and PHP are running",
]

function StatusChip({ status }: { status: string | null }) {
  if (!status) return <span className="text-[11px] text-muted-foreground">not run yet</span>
  if (status === "completed")
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400">
        <CheckCircle2 size={11} /> all good
      </span>
    )
  if (status === "needs_you")
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-400">
        <PauseCircle size={11} /> needed your OK
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-red-600 dark:text-red-400">
      <AlertTriangle size={11} /> could not finish
    </span>
  )
}

function AddTaskForm({ serverId, onClose }: { serverId?: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState<AutopilotBody>({
    name: "", goal: "", server_id: serverId ?? null,
    policy: "report_only", cron_expression: "0 3 * * *",
    human_schedule: "every night at 3am", channel: "email", channel_target: "",
    notify_on_change_only: true,
  })
  const [scheduleText, setScheduleText] = useState("every night at 3am")
  const [error, setError] = useState<string | null>(null)

  // Natural language → cron, same helper the scheduler and backups use.
  const parse = useMutation({
    mutationFn: (text: string) => parseSchedule(text),
    onSuccess: (r) =>
      setForm((f) => ({ ...f, cron_expression: r.cron_expression, human_schedule: r.human_description })),
  })

  const save = useMutation({
    mutationFn: () =>
      createAutopilotTask({ ...form, channel_target: form.channel_target?.trim() || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["autopilot-tasks"] })
      onClose()
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(typeof d === "string" ? d : "Could not create this task.")
    },
  })

  return (
    <div className="rounded-xl border border-border bg-muted/30 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="text-sm font-semibold">New autopilot task</h4>
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-accent">
          <X size={15} />
        </button>
      </div>

      <div className="space-y-3">
        <div>
          <label className={label}>Name</label>
          <input className={input} placeholder="Nightly health check" value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })} />
        </div>

        <div>
          <label className={label}>What should Ally do?</label>
          <textarea
            className={`${input} min-h-[64px] resize-y`}
            placeholder="Check the site is loading and fix it if it is not"
            value={form.goal}
            onChange={(e) => setForm({ ...form, goal: e.target.value })}
          />
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {EXAMPLES.map((ex) => (
              <button key={ex} onClick={() => setForm({ ...form, goal: ex })}
                className="rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground">
                {ex}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className={label}>How far may Ally go on its own?</label>
          <div className="space-y-1.5">
            {POLICIES.map((p) => (
              <label key={p.value}
                className={`flex cursor-pointer items-start gap-2.5 rounded-lg border p-2.5 transition-colors ${
                  form.policy === p.value ? "border-primary bg-primary/5" : "border-border hover:bg-muted/50"
                }`}>
                <input type="radio" name="policy" className="mt-0.5" checked={form.policy === p.value}
                  onChange={() => setForm({ ...form, policy: p.value })} />
                <span>
                  <span className="block text-[13px] font-medium">{p.title}</span>
                  <span className="block text-[11.5px] text-muted-foreground">{p.detail}</span>
                </span>
              </label>
            ))}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className={label}>When</label>
            <input className={input} placeholder="every night at 3am" value={scheduleText}
              onChange={(e) => setScheduleText(e.target.value)}
              onBlur={() => scheduleText.trim() && parse.mutate(scheduleText.trim())} />
            <p className="mt-1 text-[11px] text-muted-foreground">
              {parse.isPending ? "Working it out…" : `Runs: ${form.human_schedule || form.cron_expression}`}
            </p>
          </div>
          <div>
            <label className={label}>Email me the report</label>
            <input className={input} type="email" placeholder="you@example.com"
              value={form.channel_target ?? ""}
              onChange={(e) => setForm({ ...form, channel_target: e.target.value })} />
            <label className="mt-1.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <input type="checkbox" checked={form.notify_on_change_only}
                onChange={(e) => setForm({ ...form, notify_on_change_only: e.target.checked })} />
              Only when something happened
            </label>
          </div>
        </div>
      </div>

      {error && (
        <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      <div className="mt-3 flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
        <Button size="sm" disabled={!form.name || !form.goal || save.isPending}
          onClick={() => { setError(null); save.mutate() }}>
          {save.isPending ? <><Loader2 size={14} className="animate-spin" /> Creating…</> : "Create task"}
        </Button>
      </div>
    </div>
  )
}

function TaskRow({ task }: { task: AutopilotTask }) {
  const qc = useQueryClient()
  const refresh = () => qc.invalidateQueries({ queryKey: ["autopilot-tasks"] })
  const run = useMutation({ mutationFn: () => runAutopilotTask(task.id), onSuccess: refresh })
  const toggle = useMutation({
    mutationFn: () => updateAutopilotTask(task.id, { is_active: !task.is_active }),
    onSuccess: refresh,
  })
  const remove = useMutation({ mutationFn: () => deleteAutopilotTask(task.id), onSuccess: refresh })

  return (
    <li className="rounded-lg border border-border bg-background px-3 py-2.5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-sm font-medium">{task.name}</span>
            {!task.is_active && (
              <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">paused</span>
            )}
            <StatusChip status={task.last_status} />
          </div>
          <p className="mt-0.5 line-clamp-2 text-[12px] text-muted-foreground">{task.goal}</p>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1"><Clock size={10} />{task.human_schedule || task.cron_expression}</span>
            <span>·</span>
            <span>{task.policy_label}</span>
            {task.last_run && (
              <>
                <span>·</span>
                <span>ran {formatDistanceToNow(new Date(task.last_run), { addSuffix: true })}</span>
              </>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button size="sm" variant="ghost" title="Run now" disabled={run.isPending}
            onClick={() => run.mutate()}>
            {run.isPending ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
          </Button>
          <Button size="sm" variant="ghost" title={task.is_active ? "Pause" : "Resume"}
            disabled={toggle.isPending} onClick={() => toggle.mutate()}>
            <PauseCircle size={14} />
          </Button>
          <Button size="sm" variant="ghost" disabled={remove.isPending}
            onClick={() => { if (window.confirm(`Delete "${task.name}"?`)) remove.mutate() }}
            className="text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-400 dark:hover:bg-red-950/30">
            <Trash2 size={14} />
          </Button>
        </div>
      </div>
    </li>
  )
}

/** Ally on autopilot — standing instructions that run on a schedule, within set limits. */
export default function AutopilotPanel({ serverId }: { serverId?: string }) {
  const [adding, setAdding] = useState(false)
  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ["autopilot-tasks"],
    queryFn: listAutopilotTasks,
  })
  const shown = serverId ? tasks.filter((t) => t.server_id === serverId) : tasks

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold">
          <Plane size={15} className="text-primary" />
          Autopilot
        </h3>
        {!adding && (
          <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
            <Plus size={14} /> New task
          </Button>
        )}
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Ally checks and fixes on a schedule, only as far as you allow. Dangerous commands stay blocked either way.
      </p>

      {adding && <div className="mb-3"><AddTaskForm serverId={serverId} onClose={() => setAdding(false)} /></div>}

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading…</p>
      ) : shown.length === 0 && !adding ? (
        <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
          Nothing on autopilot yet. Ally only works when you ask.
        </div>
      ) : (
        <ul className="space-y-2">{shown.map((t) => <TaskRow key={t.id} task={t} />)}</ul>
      )}
    </div>
  )
}

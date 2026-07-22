import { useState, useCallback, useEffect, useRef } from "react"
import { useParams } from "react-router-dom"
import { Button } from "@/components/ui"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Clock,
  Plus,
  Play,
  Pause,
  Trash2,
  RotateCcw,
  Loader2,
  CheckCircle2,
  XCircle,
  Terminal,
  BookOpen,
  FileCode,
  ChevronDown,
  Sparkles,
  AlertTriangle,
  X,
} from "lucide-react"
import {
  listSchedules,
  createSchedule,
  deleteSchedule,
  toggleSchedule,
  runNow,
  parseSchedule,
  type ScheduledTaskCreateBody,
} from "@/api/scheduler"
import { listPlaybooks } from "@/api/playbooks"
import { listScripts } from "@/api/scripts"
import type { ScheduledTask } from "@/types"
import { formatDistanceToNow, format } from "date-fns"

// ── Helpers ────────────────────────────────────────────────────────────────

type TaskType = "command" | "playbook" | "user_script"

const TYPE_META: Record<
  TaskType,
  { label: string; icon: React.ReactNode; color: string }
> = {
  command: {
    label: "Command",
    icon: <Terminal className="h-3.5 w-3.5" />,
    color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20",
  },
  playbook: {
    label: "Playbook",
    icon: <BookOpen className="h-3.5 w-3.5" />,
    color: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  },
  user_script: {
    label: "My Script",
    icon: <FileCode className="h-3.5 w-3.5" />,
    color: "bg-violet-500/10 text-violet-400 border-violet-500/20",
  },
}

const STATUS_META: Record<
  string,
  { icon: React.ReactNode; color: string }
> = {
  success: {
    icon: <CheckCircle2 className="h-3.5 w-3.5" />,
    color: "text-emerald-400",
  },
  failed: {
    icon: <XCircle className="h-3.5 w-3.5" />,
    color: "text-red-400",
  },
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—"
  return formatDistanceToNow(new Date(iso), { addSuffix: true })
}

function fmtNextRun(iso: string | null): string {
  if (!iso) return "—"
  return format(new Date(iso), "MMM d, HH:mm")
}

// ── Task card ──────────────────────────────────────────────────────────────

function TaskCard({
  task,
  onToggle,
  onDelete,
  onRunNow,
  isRunning,
}: {
  task: ScheduledTask
  onToggle: (id: string) => void
  onDelete: (id: string) => void
  onRunNow: (id: string) => void
  isRunning: boolean
}) {
  const meta = TYPE_META[task.task_type] ?? TYPE_META.command
  const statusMeta = task.last_status ? STATUS_META[task.last_status] : null

  return (
    <div
      className={`rounded-xl border bg-card p-5 flex flex-col gap-4 transition-all ${
        task.is_active ? "border-border" : "border-border/40 opacity-60"
      }`}
    >
      {/* Top row */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border ${meta.color}`}
            >
              {meta.icon}
              {meta.label}
            </span>
            {!task.is_active && (
              <span className="text-[10px] text-muted-foreground border border-border rounded px-1.5 py-0.5">
                Paused
              </span>
            )}
          </div>
          <h3 className="font-medium text-foreground text-sm leading-snug truncate">
            {task.title}
          </h3>
          <p className="text-xs font-mono text-muted-foreground mt-0.5">
            {task.human_schedule ?? task.cron_expression}
            {task.human_schedule && (
              <span className="ml-2 text-muted-foreground/50">
                ({task.cron_expression})
              </span>
            )}
          </p>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-1 shrink-0">
          <button
            onClick={() => onRunNow(task.id)}
            disabled={isRunning}
            title="Run now"
            className="p-1.5 rounded text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors disabled:opacity-40"
          >
            {isRunning ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
          </button>
          <button
            onClick={() => onToggle(task.id)}
            title={task.is_active ? "Pause" : "Resume"}
            className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
          >
            {task.is_active ? (
              <Pause className="h-3.5 w-3.5" />
            ) : (
              <RotateCcw className="h-3.5 w-3.5" />
            )}
          </button>
          <button
            onClick={() => onDelete(task.id)}
            title="Delete"
            className="p-1.5 rounded text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3 text-xs">
        <div>
          <p className="text-muted-foreground/70 mb-0.5">Last run</p>
          <div className="flex items-center gap-1">
            {statusMeta && (
              <span className={statusMeta.color}>{statusMeta.icon}</span>
            )}
            <span className="text-muted-foreground">{fmtDate(task.last_run)}</span>
          </div>
        </div>
        <div>
          <p className="text-muted-foreground/70 mb-0.5">Next run</p>
          <p className="text-foreground font-medium">{fmtNextRun(task.next_run)}</p>
        </div>
        <div>
          <p className="text-muted-foreground/70 mb-0.5">Created</p>
          <p className="text-muted-foreground">{fmtDate(task.created_at)}</p>
        </div>
      </div>

      {/* Payload preview */}
      {task.payload && task.task_type === "command" && (
        <div className="rounded-lg bg-black/40 border border-border px-3 py-2 font-mono text-xs text-green-400 truncate">
          {(task.payload as Record<string, string>).command ?? "—"}
        </div>
      )}
    </div>
  )
}

// ── New task modal ─────────────────────────────────────────────────────────

interface NewTaskModalProps {
  onClose: () => void
  onCreate: (body: ScheduledTaskCreateBody) => Promise<void>
  isCreating: boolean
}

function NewTaskModal({ onClose, onCreate, isCreating }: NewTaskModalProps) {
  const [title, setTitle] = useState("")
  const [taskType, setTaskType] = useState<TaskType>("command")
  const [command, setCommand] = useState("")
  const [playbookId, setPlaybookId] = useState("")
  const [scriptId, setScriptId] = useState("")
  const [scheduleInput, setScheduleInput] = useState("")
  const [cronPreview, setCronPreview] = useState<string | null>(null)
  const [cronDesc, setCronDesc] = useState<string | null>(null)
  const [isParsing, setIsParsing] = useState(false)
  const parseTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { data: playbooks = [] } = useQuery({
    queryKey: ["playbooks"],
    queryFn: () => listPlaybooks(),
  })
  const { data: scripts = [] } = useQuery({
    queryKey: ["scripts"],
    queryFn: listScripts,
  })

  // Debounce NL schedule parsing
  useEffect(() => {
    if (!scheduleInput.trim()) {
      setCronPreview(null)
      setCronDesc(null)
      return
    }
    if (parseTimer.current) clearTimeout(parseTimer.current)
    parseTimer.current = setTimeout(async () => {
      setIsParsing(true)
      try {
        const result = await parseSchedule(scheduleInput)
        setCronPreview(result.cron_expression)
        setCronDesc(result.human_description)
      } catch {
        setCronPreview(null)
        setCronDesc(null)
      } finally {
        setIsParsing(false)
      }
    }, 700)
    return () => {
      if (parseTimer.current) clearTimeout(parseTimer.current)
    }
  }, [scheduleInput])

  const handleSubmit = async () => {
    if (!title.trim() || !scheduleInput.trim()) return

    const payload: Record<string, string> = {}
    if (taskType === "command") payload.command = command
    else if (taskType === "playbook") payload.playbook_id = playbookId
    else if (taskType === "user_script") payload.user_script_id = scriptId

    await onCreate({
      title: title.trim(),
      task_type: taskType,
      payload,
      human_schedule: scheduleInput.trim(),
      cron_expression: cronPreview ?? undefined,
    })
  }

  const canSubmit =
    title.trim() &&
    scheduleInput.trim() &&
    (taskType === "command" ? command.trim() : taskType === "playbook" ? playbookId : scriptId)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            <h2 className="font-semibold text-foreground">New Scheduled Task</h2>
            <p className="text-xs text-muted-foreground mt-0.5">
              Runs automatically on your server
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="overflow-y-auto flex-1 p-6 space-y-5">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-1.5">
              Task name
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g. Daily MySQL Backup"
              className="w-full rounded-lg border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground/50 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>

          {/* Task type */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-2">
              Task type
            </label>
            <div className="grid grid-cols-3 gap-2">
              {(Object.keys(TYPE_META) as TaskType[]).map((t) => {
                const m = TYPE_META[t]
                return (
                  <button
                    key={t}
                    onClick={() => setTaskType(t)}
                    className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-sm transition-all ${
                      taskType === t
                        ? "border-primary/60 bg-primary/5 text-foreground"
                        : "border-border text-muted-foreground hover:border-border/80 hover:text-foreground"
                    }`}
                  >
                    <span className={taskType === t ? "text-primary" : ""}>{m.icon}</span>
                    {m.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Payload */}
          {taskType === "command" && (
            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">
                Command
              </label>
              <input
                type="text"
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                placeholder="e.g. mysqldump -u root mydb > /backup/db.sql"
                className="w-full rounded-lg border border-border bg-background text-sm font-mono text-foreground placeholder:text-muted-foreground/50 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
            </div>
          )}

          {taskType === "playbook" && (
            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">
                Playbook
              </label>
              <div className="relative">
                <select
                  value={playbookId}
                  onChange={(e) => setPlaybookId(e.target.value)}
                  className="w-full appearance-none rounded-lg border border-border bg-background text-sm text-foreground px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/40 pr-8"
                >
                  <option value="">Select a playbook…</option>
                  {playbooks.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              </div>
            </div>
          )}

          {taskType === "user_script" && (
            <div>
              <label className="block text-sm font-medium text-foreground mb-1.5">
                My Script
              </label>
              <div className="relative">
                <select
                  value={scriptId}
                  onChange={(e) => setScriptId(e.target.value)}
                  className="w-full appearance-none rounded-lg border border-border bg-background text-sm text-foreground px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/40 pr-8"
                >
                  <option value="">Select a script…</option>
                  {scripts.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.title}
                    </option>
                  ))}
                </select>
                <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
              </div>
            </div>
          )}

          {/* Schedule input */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-1.5">
              Schedule
            </label>
            <div className="relative">
              <input
                type="text"
                value={scheduleInput}
                onChange={(e) => setScheduleInput(e.target.value)}
                placeholder="e.g. every night at 2am  or  0 2 * * *"
                className="w-full rounded-lg border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground/50 px-3 py-2 pr-8 focus:outline-none focus:ring-2 focus:ring-primary/40"
              />
              {isParsing && (
                <Loader2 className="absolute right-2.5 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground animate-spin" />
              )}
            </div>

            {/* Cron preview */}
            {cronPreview && (
              <div className="mt-2 flex items-start gap-2 rounded-lg border border-primary/20 bg-primary/5 px-3 py-2">
                <Sparkles className="h-3.5 w-3.5 text-primary mt-0.5 shrink-0" />
                <div>
                  <p className="text-xs font-mono text-primary">{cronPreview}</p>
                  {cronDesc && (
                    <p className="text-xs text-muted-foreground mt-0.5">{cronDesc}</p>
                  )}
                </div>
              </div>
            )}

            {/* Examples */}
            <div className="mt-2 flex flex-wrap gap-1.5">
              {[
                "every hour",
                "every night at 2am",
                "every Sunday at midnight",
                "every 15 minutes",
                "every weekday at 9am",
              ].map((ex) => (
                <button
                  key={ex}
                  onClick={() => setScheduleInput(ex)}
                  className="text-[11px] px-2 py-0.5 rounded-full border border-border text-muted-foreground hover:border-primary/30 hover:text-foreground transition-colors"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm text-muted-foreground hover:text-foreground border border-border hover:bg-muted/50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit || isCreating}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {isCreating ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            Create Task
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────

export default function Scheduler() {
  const { id: serverId } = useParams<{ id: string }>()
  const queryClient = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [runningId, setRunningId] = useState<string | null>(null)

  const { data: tasks = [], isLoading } = useQuery({
    queryKey: ["schedules", serverId],
    queryFn: () => listSchedules(serverId!),
    enabled: !!serverId,
    refetchInterval: 15_000, // refresh every 15s to pick up last_run updates
  })

  const createMutation = useMutation({
    mutationFn: (body: ScheduledTaskCreateBody) => createSchedule(serverId!, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules", serverId] })
      setShowModal(false)
    },
  })

  const toggleMutation = useMutation({
    mutationFn: toggleSchedule,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["schedules", serverId] }),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteSchedule,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["schedules", serverId] }),
  })

  const handleRunNow = useCallback(
    async (id: string) => {
      setRunningId(id)
      try {
        await runNow(id)
        setTimeout(() => {
          queryClient.invalidateQueries({ queryKey: ["schedules", serverId] })
        }, 2000)
      } finally {
        setRunningId(null)
      }
    },
    [serverId, queryClient]
  )

  const active = tasks.filter((t) => t.is_active)
  const paused = tasks.filter((t) => !t.is_active)

  return (
    <>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-h1 text-foreground flex items-center gap-2">
              <Clock className="h-6 w-6 text-primary" />
              Scheduler
            </h1>
            <p className="text-sm text-muted-foreground mt-1">
              Recurring tasks on this server — runs automatically on your cron schedule
            </p>
          </div>
          <Button onClick={() => setShowModal(true)}>
            <Plus className="h-4 w-4" />
            New Task
          </Button>
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-24 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin mr-2" />
            Loading scheduled tasks…
          </div>
        )}

        {/* Empty */}
        {!isLoading && tasks.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <Clock className="h-10 w-10 text-muted-foreground/30 mb-3" />
            <p className="font-medium text-muted-foreground">No scheduled tasks yet</p>
            <p className="text-sm text-muted-foreground/60 mt-1">
              Create a task and describe when to run it in plain English
            </p>
            <button
              onClick={() => setShowModal(true)}
              className="mt-4 flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              <Plus className="h-4 w-4" />
              New Task
            </button>
          </div>
        )}

        {/* Active tasks */}
        {active.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <h2 className="text-sm font-medium text-foreground">Active</h2>
              <span className="text-xs text-muted-foreground bg-muted rounded-full px-2 py-0.5">
                {active.length}
              </span>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {active.map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  onToggle={(id) => toggleMutation.mutate(id)}
                  onDelete={(id) => deleteMutation.mutate(id)}
                  onRunNow={handleRunNow}
                  isRunning={runningId === task.id}
                />
              ))}
            </div>
          </div>
        )}

        {/* Paused tasks */}
        {paused.length > 0 && (
          <div>
            <div className="flex items-center gap-2 mb-3">
              <h2 className="text-sm font-medium text-foreground">Paused</h2>
              <span className="text-xs text-muted-foreground bg-muted rounded-full px-2 py-0.5">
                {paused.length}
              </span>
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {paused.map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  onToggle={(id) => toggleMutation.mutate(id)}
                  onDelete={(id) => deleteMutation.mutate(id)}
                  onRunNow={handleRunNow}
                  isRunning={runningId === task.id}
                />
              ))}
            </div>
          </div>
        )}

        {/* Error feedback */}
        {createMutation.isError && (
          <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {(createMutation.error as Error).message}
          </div>
        )}
      </div>

      {showModal && (
        <NewTaskModal
          onClose={() => setShowModal(false)}
          onCreate={async (body) => {
            await createMutation.mutateAsync(body)
          }}
          isCreating={createMutation.isPending}
        />
      )}
    </>
  )
}

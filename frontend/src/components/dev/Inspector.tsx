import { useEffect, useState, type ReactNode } from "react"
import { useQuery, useMutation } from "@tanstack/react-query"
import type { AxiosError } from "axios"
import {
  Play,
  Loader2,
  ChevronDown,
  ChevronRight,
  Copy,
  Check,
  ShieldCheck,
  AlertTriangle,
  Zap,
  RotateCcw,
  BookmarkPlus,
} from "lucide-react"
import { listServers } from "@/api/servers"
import { dryRun, captureEvalCase, type DryRunTrace } from "@/api/dev"

function errMsg(e: unknown): string {
  const detail = (e as AxiosError<{ detail?: unknown }>)?.response?.data?.detail
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) return detail.map((d) => (d as { msg?: string })?.msg).filter(Boolean).join("; ")
  return (e as Error)?.message || "Something went wrong"
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false)
  return (
    <button
      onClick={(e) => {
        e.stopPropagation()
        navigator.clipboard.writeText(text).then(() => {
          setDone(true)
          setTimeout(() => setDone(false), 1200)
        })
      }}
      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      title="Copy"
    >
      {done ? <Check size={13} /> : <Copy size={13} />}
      {done ? "Copied" : "Copy"}
    </button>
  )
}

function Panel({
  title,
  subtitle,
  body,
  defaultOpen = false,
  tone = "default",
}: {
  title: string
  subtitle?: string
  body: string
  defaultOpen?: boolean
  tone?: "default" | "muted"
}) {
  const [open, setOpen] = useState(defaultOpen)
  const empty = !body
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-4 py-3 text-left transition-colors hover:bg-accent/40"
      >
        {open ? <ChevronDown size={16} className="shrink-0 text-muted-foreground" /> : <ChevronRight size={16} className="shrink-0 text-muted-foreground" />}
        <span className="text-sm font-medium text-foreground">{title}</span>
        {subtitle && <span className="text-xs text-muted-foreground">{subtitle}</span>}
        <span className="ml-auto text-xs text-muted-foreground">{empty ? "empty" : `${body.length.toLocaleString()} chars`}</span>
        {!empty && <CopyButton text={body} />}
      </button>
      {open && (
        <div className="border-t border-border">
          {empty ? (
            <p className="px-4 py-3 text-xs text-muted-foreground">(nothing)</p>
          ) : (
            <pre
              className={`max-h-96 overflow-auto px-4 py-3 text-xs leading-relaxed ${
                tone === "muted" ? "bg-muted/30" : ""
              } whitespace-pre-wrap break-words font-mono text-foreground/90`}
            >
              {body}
            </pre>
          )}
        </div>
      )}
    </section>
  )
}

function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: "accent" }) {
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={`text-sm font-semibold ${tone === "accent" ? "text-primary" : "text-foreground"}`}>{value}</div>
    </div>
  )
}

function Chip({ on, label }: { on: boolean; label: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${
        on ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400" : "bg-muted text-muted-foreground"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${on ? "bg-emerald-500" : "bg-muted-foreground/40"}`} />
      {label}
    </span>
  )
}

/** Capture the current dry-run as a skill-routing eval case (message → the skill that
 * matched). The flywheel: pin correct routing, or capture a mis-route then fix the trigger. */
function CaptureButton({ trace }: { trace: DryRunTrace }) {
  const capture = useMutation({
    mutationFn: () =>
      captureEvalCase({
        category: "skill-routing",
        input: trace.input.message,
        expected: trace.context.skill || "None",
        os: trace.input.server.os_type || "linux",
        note: "captured from the Prompt Inspector",
      }),
  })
  return (
    <button
      onClick={() => capture.mutate()}
      disabled={capture.isPending || capture.isSuccess}
      className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-60"
      title="Save this as a skill-routing eval case"
    >
      {capture.isSuccess ? <Check size={13} className="text-emerald-500" /> : <BookmarkPlus size={13} />}
      {capture.isSuccess ? "Captured → Evals tab" : capture.isPending ? "Capturing…" : "Capture as eval case"}
    </button>
  )
}

function Results({ trace }: { trace: DryRunTrace }) {
  const { meta, context, prompt, output } = trace
  const parsed = JSON.stringify(output.parsed, null, 2)
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        <Stat label="Model" value={meta.models[0]?.replace("claude-", "") || "—"} />
        <Stat label="Input tok" value={meta.input_tokens.toLocaleString()} />
        <Stat label="Output tok" value={meta.output_tokens.toLocaleString()} />
        <Stat label="Cache read" value={meta.cache_read_tokens.toLocaleString()} />
        <Stat label="LLM calls" value={meta.calls} />
        <Stat label="Cost" value={`$${meta.cost_usd.toFixed(4)}`} tone="accent" />
      </div>

      {(meta.escalated || meta.retried_trimmed || context.use_skill_requested) && (
        <div className="flex flex-wrap gap-2">
          {meta.escalated && (
            <span className="inline-flex items-center gap-1 rounded-full bg-violet-500/10 px-2.5 py-1 text-xs font-medium text-violet-600 dark:text-violet-400">
              <Zap size={12} /> stronger model
            </span>
          )}
          {meta.retried_trimmed && (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-600 dark:text-amber-400">
              <RotateCcw size={12} /> trimmed-context retry
            </span>
          )}
          {context.use_skill_requested && (
            <span className="inline-flex items-center gap-1 rounded-full bg-blue-500/10 px-2.5 py-1 text-xs font-medium text-blue-600 dark:text-blue-400">
              requested skill: {context.use_skill_requested}
            </span>
          )}
        </div>
      )}

      <section className="rounded-xl border border-border bg-card p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-foreground">Context assembled</span>
          <span className="text-xs text-muted-foreground">
            skill: <b className="text-foreground">{context.skill || "generalist"}</b> · mode:{" "}
            <b className="text-foreground">{trace.input.ally_mode || "normal"}</b>
          </span>
          <span className="ml-auto">
            <CaptureButton trace={trace} />
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          <Chip on={context.has_live_snapshot} label="live snapshot" />
          <Chip on={context.has_scout} label="scout" />
          <Chip on={context.has_server_profile} label="server profile" />
          <Chip on={context.has_memories} label="memories" />
          <Chip on={context.skill_menu_offered} label="skill menu" />
          <Chip on={!!context.other_servers} label="other servers" />
        </div>
      </section>

      <Panel title="System prompt" subtitle="stable prefix — persona, rules, server identity, skill" body={prompt.system} />
      <Panel title="Volatile tail" subtitle="per-message — snapshot, scout, profile, memories, history" body={prompt.volatile} defaultOpen tone="muted" />
      <Panel title="Raw model output" body={output.raw} tone="muted" />
      <Panel title="Parsed plan" subtitle="what the chat pipeline would act on" body={parsed} defaultOpen />
    </div>
  )
}

export default function Inspector() {
  const [serverId, setServerId] = useState("")
  const [message, setMessage] = useState("")

  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers })
  const run = useMutation({ mutationFn: () => dryRun(serverId, message) })

  useEffect(() => {
    if (!serverId && servers.length) setServerId(servers[0].id)
  }, [servers, serverId])

  const canRun = Boolean(serverId && message.trim()) && !run.isPending

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Dry-run a message the way Ally would — see the exact prompt, the raw model output, and the cost.
        Nothing runs on the server.
      </p>

      <section className="rounded-xl border border-border bg-card p-5">
        <div className="space-y-4">
          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">Server</label>
            <select
              value={serverId}
              onChange={(e) => setServerId(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground"
            >
              {servers.length === 0 && <option value="">No servers</option>}
              {servers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} — {s.os_type || "unknown"} ({s.connection_type})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1.5 block text-sm font-medium text-foreground">Message</label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && canRun) run.mutate()
              }}
              rows={3}
              placeholder="e.g. why is my disk full? — or — install fail2ban"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground/70"
            />
          </div>

          <div className="flex items-center justify-between">
            <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <ShieldCheck size={14} className="text-emerald-500" />
              Read-only — plans only, never executes
            </span>
            <button
              onClick={() => run.mutate()}
              disabled={!canRun}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {run.isPending ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              {run.isPending ? "Planning…" : "Dry run"}
            </button>
          </div>
          <p className="text-[11px] text-muted-foreground">⌘/Ctrl + Enter to run</p>
        </div>
      </section>

      {run.isError && (
        <div className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-600 dark:text-red-400">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>{errMsg(run.error)}</span>
        </div>
      )}

      {run.data && <Results trace={run.data} />}
    </div>
  )
}

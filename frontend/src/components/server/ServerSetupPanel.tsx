import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Check, CircleDashed, Loader2, TriangleAlert, Wand2, X, MinusCircle, Sparkles,
} from "lucide-react"
import {
  getSetupStatus, startSetup, stopSetup, type SetupStep,
} from "@/api/setup"
import type { Server } from "@/types"
import { Button } from "@/components/ui"
import { useAssistantStore } from "@/store/assistantStore"
import { cn } from "@/lib/utils"

const detail = (e: unknown) =>
  (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail

function elapsed(from: string | null): string {
  if (!from) return ""
  const secs = Math.max(0, Math.round((Date.now() - new Date(from).getTime()) / 1000))
  return secs < 60 ? `${secs}s` : `${Math.floor(secs / 60)}m ${secs % 60}s`
}

function StepIcon({ state }: { state: SetupStep["state"] }) {
  if (state === "done")
    return <Check size={14} className="shrink-0 text-emerald-600 dark:text-emerald-400" />
  if (state === "running")
    return <Loader2 size={14} className="shrink-0 animate-spin text-primary" />
  if (state === "failed")
    return <X size={14} className="shrink-0 text-red-600 dark:text-red-400" />
  if (state === "skipped")
    return <MinusCircle size={14} className="shrink-0 text-muted-foreground" />
  return <CircleDashed size={14} className="shrink-0 text-muted-foreground/50" />
}

/**
 * One button that turns a blank server into a working one.
 *
 * The waiting experience is the feature as much as the installing is. A customer staring
 * at a spinner has exactly one question — how much longer — so this shows named steps in
 * plain words, a count, a percentage and a timer on the current step. And it says the
 * thing that removes the anxiety: the work continues if they leave.
 */
export default function ServerSetupPanel({ server }: { server: Server }) {
  const qc = useQueryClient()
  const openServer = useAssistantStore((s) => s.openServer)
  const [purpose, setPurpose] = useState("websites")
  const [force, setForce] = useState(false)

  const q = useQuery({
    queryKey: ["server-setup", server.id],
    queryFn: () => getSetupStatus(server.id),
    // Poll only while something is happening, and keep polling on a hidden tab — someone
    // who starts this and switches away should come back to the finished list.
    refetchInterval: (query) =>
      query.state.data?.latest?.status === "running" ? 3000 : false,
    refetchIntervalInBackground: true,
  })

  const begin = useMutation({
    mutationFn: () => startSetup(server.id, { purpose, force }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["server-setup", server.id] }),
  })
  const halt = useMutation({
    mutationFn: () => stopSetup(server.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["server-setup", server.id] }),
  })

  if (q.isLoading) {
    return <div className="flex justify-center py-8">
      <Loader2 className="animate-spin text-muted-foreground" /></div>
  }
  const data = q.data
  if (!data) return null
  const run = data.latest
  const busy = run?.status === "running"
  const chosen = data.options.find((o) => o.key === purpose)
  const startError = detail(begin.error)

  // ── while it runs, or after it has finished ────────────────────────────────
  if (run && (busy || run.status !== "done" || data.already_set_up)) {
    return (
      <section className="rounded-xl border border-border bg-card p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-h3 text-foreground">
              {busy ? "Setting up this server" : run.status === "done"
                ? "This server is set up" : "Setup stopped"}
            </h2>
            {busy && (
              <p className="mt-1 text-[12.5px] text-muted-foreground">
                <strong className="text-foreground">
                  {run.progress.done} of {run.progress.total}
                </strong>{" "}
                · {run.progress.percent}% ·{" "}
                {/* The sentence that removes the anxiety. Our work genuinely survives a
                    closed tab — we have simply never said so. */}
                <span className="text-foreground">
                  it is safe to leave this page, this continues in the background.
                </span>
              </p>
            )}
            {run.message && !busy && (
              <p className="mt-1 text-[12.5px] text-muted-foreground">{run.message}</p>
            )}
          </div>
          {busy && (
            <Button size="sm" variant="outline" disabled={halt.isPending}
              onClick={() => halt.mutate()}>Stop after this step</Button>
          )}
        </div>

        {busy && (
          <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${run.progress.percent}%` }} />
          </div>
        )}

        <ul className="mt-3 space-y-1.5">
          {run.steps.map((step, i) => (
            <li key={`${step.slug}-${i}`} className="flex items-center gap-2">
              <StepIcon state={step.state} />
              <span className={cn("text-[13px]",
                step.state === "pending" ? "text-muted-foreground/70"
                  : step.state === "running" ? "font-medium text-foreground"
                  : "text-foreground")}>
                {step.label}
              </span>
              {step.state === "running" && run.started_at && (
                <span className="text-[11.5px] tabular-nums text-muted-foreground">
                  {elapsed(run.started_at)}
                </span>
              )}
              {step.state === "skipped" && (
                <span className="text-[11.5px] text-muted-foreground">
                  skipped{step.note ? ` — ${step.note}` : ""}
                </span>
              )}
              {step.state === "failed" && step.note && (
                <span className="text-[11.5px] text-red-600 dark:text-red-400">
                  {step.note}
                </span>
              )}
            </li>
          ))}
        </ul>

        {run.status === "failed" && (
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" variant="gradient"
              onClick={() => openServer(server,
                `The automatic setup stopped at “${run.failed_step}”. Please look at why `
                + "and finish setting this server up.")}>
              <Sparkles size={13} />Ask Ally to finish it
            </Button>
            <Button size="sm" variant="outline" onClick={() => begin.mutate()}>
              Try again
            </Button>
          </div>
        )}
        {!busy && run.status === "done" && (
          <p className="mt-3 text-[12.5px] text-emerald-600 dark:text-emerald-400">
            Next: add a website to it from the Sites page.
          </p>
        )}
      </section>
    )
  }

  // ── nothing has run yet ────────────────────────────────────────────────────
  return (
    <section className="rounded-xl border border-border bg-card p-4">
      <h2 className="flex items-center gap-2 text-h3 text-foreground">
        <Wand2 size={16} className="text-primary" /> Set up this server
      </h2>
      <p className="mt-1 text-[12.5px] text-muted-foreground">
        A blank server needs updates, security and software before it can host anything.
        Choose what it is for and we will do all of it — no commands to type.
      </p>

      {data.blocked && !force && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border-l-2 border-amber-500
                        bg-amber-500/10 px-3 py-2">
          <TriangleAlert size={14} className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
          <div className="flex-1">
            <p className="text-[12.5px] text-amber-900 dark:text-amber-200">{data.blocked}</p>
            <button className="mt-1 text-[12px] text-amber-800 underline dark:text-amber-300"
              onClick={() => setForce(true)}>
              Set it up anyway
            </button>
          </div>
        </div>
      )}

      <div className="mt-3 grid gap-2 sm:grid-cols-2">
        {data.options.map((o) => (
          <button key={o.key} onClick={() => setPurpose(o.key)}
            className={cn("rounded-lg border p-3 text-left transition",
              purpose === o.key
                ? "border-primary bg-primary/5" : "border-border hover:bg-accent")}>
            <p className="text-[13px] font-medium text-foreground">{o.title}</p>
            <p className="mt-0.5 text-[12px] text-muted-foreground">{o.description}</p>
            <p className="mt-1 text-[11.5px] text-muted-foreground">
              {o.steps.length} steps · about {o.minutes} minutes
            </p>
          </button>
        ))}
      </div>

      {chosen && (
        <details className="mt-3">
          <summary className="cursor-pointer text-[12px] text-muted-foreground">
            What will be done
          </summary>
          <ul className="mt-1.5 space-y-1">
            {chosen.steps.map((st, i) => (
              <li key={i} className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
                <CircleDashed size={12} className="shrink-0 opacity-50" />{st.label}
                {st.optional && <span className="text-[11px]">(optional)</span>}
              </li>
            ))}
          </ul>
        </details>
      )}

      {startError && (
        <p className="mt-2 text-[12.5px] text-red-600 dark:text-red-400">{startError}</p>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button disabled={begin.isPending || (!!data.blocked && !force)}
          onClick={() => begin.mutate()}>
          {begin.isPending && <Loader2 size={14} className="animate-spin" />}
          Set up this server
        </Button>
        {/* The second door. Same engine — this one just lets the customer say it in
            their own words, and lets Ally handle a server that is not standard. */}
        <Button variant="ghost" onClick={() => openServer(server,
          "Please get this server ready to host websites — updates, security, firewall, "
          + "web server, PHP and a database. Tell me what you find before changing anything.")}>
          <Sparkles size={13} />Or ask Ally to do it
        </Button>
      </div>
    </section>
  )
}

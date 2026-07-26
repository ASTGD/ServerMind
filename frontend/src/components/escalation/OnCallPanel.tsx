import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  BellRing, Loader2, Plus, Trash2, Check, Send, Clock, Star, Power,
} from "lucide-react"
import {
  listPolicies, createPolicy, updatePolicy, deletePolicy, previewPolicy,
  CHANNEL_HINT, CHANNEL_LABEL,
  type Channel, type EscalationPolicy, type Severity, type StepInput,
} from "@/api/escalation"
import { Button } from "@/components/ui"

const input =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
const label = "mb-1 block text-xs font-medium text-muted-foreground"

const CHANNELS: Channel[] = ["email", "sms", "telegram", "slack", "webhook"]

const SEVERITY_COPY: { value: Severity; title: string; detail: string }[] = [
  { value: "critical", title: "Only emergencies", detail: "Your site is down, or a server looks compromised" },
  { value: "high", title: "Serious problems", detail: "Emergencies, plus an expiring certificate" },
  { value: "warning", title: "Anything worth knowing", detail: "Also disk, memory and CPU warnings" },
]

/** A blank ladder that already reads like a real on-call setup. */
const STARTER_STEPS: StepInput[] = [
  { after_minutes: 0, channel: "email", target: "", label: "Me" },
  { after_minutes: 5, channel: "sms", target: "", label: "My phone" },
]

function StepRow({ step, index, onChange, onRemove }: {
  step: StepInput; index: number
  onChange: (s: StepInput) => void; onRemove: () => void
}) {
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
          <Clock size={12} />
          {index === 0 ? "Right away" : `Step ${index + 1}`}
        </span>
        <button
          onClick={onRemove}
          className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-red-500/10 hover:text-red-600"
          title="Remove this step"
        >
          <Trash2 size={13} />
        </button>
      </div>
      <div className="grid gap-2 sm:grid-cols-4">
        <div>
          <label className={label}>After</label>
          <div className="flex items-center gap-1.5">
            <input
              type="number" min={0} max={1440} className={input}
              value={step.after_minutes}
              onChange={(e) => onChange({ ...step, after_minutes: Math.max(0, Number(e.target.value) || 0) })}
            />
            <span className="shrink-0 text-xs text-muted-foreground">min</span>
          </div>
        </div>
        <div>
          <label className={label}>Reach me by</label>
          <select
            className={input} value={step.channel}
            onChange={(e) => onChange({ ...step, channel: e.target.value as Channel })}
          >
            {CHANNELS.map((c) => <option key={c} value={c}>{CHANNEL_LABEL[c]}</option>)}
          </select>
        </div>
        <div>
          <label className={label}>Where</label>
          <input
            className={input} placeholder={CHANNEL_HINT[step.channel]}
            value={step.target}
            onChange={(e) => onChange({ ...step, target: e.target.value })}
          />
        </div>
        <div>
          <label className={label}>Who is this <span className="text-muted-foreground/70">(optional)</span></label>
          <input
            className={input} placeholder="Rafi"
            value={step.label ?? ""}
            onChange={(e) => onChange({ ...step, label: e.target.value })}
          />
        </div>
      </div>
    </div>
  )
}

function PolicyEditor({ initial, onCancel, onSaved }: {
  initial?: EscalationPolicy
  onCancel: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState(initial?.name ?? "On-call")
  const [minSeverity, setMinSeverity] = useState<Severity>(initial?.min_severity ?? "high")
  const [repeatMinutes, setRepeatMinutes] = useState(initial?.repeat_minutes ?? 15)
  const [maxRepeats, setMaxRepeats] = useState(initial?.max_repeats ?? 3)
  const [isDefault, setIsDefault] = useState(initial?.is_default ?? true)
  const [steps, setSteps] = useState<StepInput[]>(
    initial?.steps.map((s) => ({ ...s })) ?? STARTER_STEPS.map((s) => ({ ...s })),
  )
  const [error, setError] = useState<string | null>(null)

  const body = {
    name: name.trim() || "On-call",
    min_severity: minSeverity,
    repeat_minutes: repeatMinutes,
    max_repeats: maxRepeats,
    is_default: isDefault,
    steps: steps.filter((s) => s.target.trim()).map((s) => ({ ...s, target: s.target.trim() })),
  }

  const save = useMutation({
    mutationFn: () => (initial ? updatePolicy(initial.id, body) : createPolicy(body)),
    onSuccess: onSaved,
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(typeof d === "string" ? d : "Could not save this policy.")
    },
  })

  // The same arithmetic the server does, so the promise on the button matches reality.
  const maxMessages = body.steps.length ? body.steps.length + maxRepeats : 0

  return (
    <div className="rounded-lg border border-border p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={label}>Name</label>
          <input className={input} value={name} onChange={(e) => setName(e.target.value)}
            placeholder="Production on-call" />
        </div>
        <div>
          <label className={label}>Page me about</label>
          <select className={input} value={minSeverity}
            onChange={(e) => setMinSeverity(e.target.value as Severity)}>
            {SEVERITY_COPY.map((s) => <option key={s.value} value={s.value}>{s.title}</option>)}
          </select>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {SEVERITY_COPY.find((s) => s.value === minSeverity)?.detail}
          </p>
        </div>
      </div>

      <p className="mb-2 mt-4 text-xs font-medium text-muted-foreground">
        Who to reach, and when
      </p>
      <div className="space-y-2">
        {steps.map((step, i) => (
          <StepRow
            key={i} step={step} index={i}
            onChange={(s) => setSteps(steps.map((old, j) => (j === i ? s : old)))}
            onRemove={() => setSteps(steps.filter((_, j) => j !== i))}
          />
        ))}
      </div>
      {steps.length < 10 && (
        <button
          onClick={() => setSteps([...steps, {
            after_minutes: (steps.at(-1)?.after_minutes ?? 0) + 10,
            channel: "sms", target: "", label: "",
          }])}
          className="mt-2 flex items-center gap-1.5 rounded-lg border border-dashed border-border px-3 py-2 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
        >
          <Plus size={13} /> Add another person or channel
        </button>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div>
          <label className={label}>If nobody answers, nudge every</label>
          <div className="flex items-center gap-1.5">
            <input type="number" min={1} max={1440} className={input} value={repeatMinutes}
              onChange={(e) => setRepeatMinutes(Math.max(1, Number(e.target.value) || 1))} />
            <span className="shrink-0 text-xs text-muted-foreground">min</span>
          </div>
        </div>
        <div>
          <label className={label}>…at most this many times</label>
          <input type="number" min={0} max={10} className={input} value={maxRepeats}
            onChange={(e) => setMaxRepeats(Math.min(10, Math.max(0, Number(e.target.value) || 0)))} />
        </div>
      </div>

      <label className="mt-3 flex cursor-pointer items-start gap-2.5 rounded-lg border border-border p-3">
        <input type="checkbox" className="mt-0.5" checked={isDefault}
          onChange={(e) => setIsDefault(e.target.checked)} />
        <span>
          <span className="block text-[13px] font-medium">Use this for all my servers</span>
          <span className="block text-[11.5px] text-muted-foreground">
            Any server without its own policy will use this one.
          </span>
        </span>
      </label>

      {/* The honest ceiling, stated before saving — an escalation you can't picture is one
          you won't trust at 3am. */}
      <p className="mt-3 rounded-lg bg-muted/60 px-3 py-2 text-[11.5px] text-muted-foreground">
        {maxMessages === 0
          ? "Add at least one contact, otherwise nothing will be sent."
          : `One problem sends at most ${maxMessages} message${maxMessages === 1 ? "" : "s"}. Acknowledging stops them.`}
      </p>

      {error && (
        <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      <div className="mt-3 flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button size="sm" disabled={save.isPending || !body.steps.length}
          onClick={() => { setError(null); save.mutate() }}>
          {save.isPending ? <><Loader2 size={14} className="animate-spin" /> Saving…</> : "Save policy"}
        </Button>
      </div>
    </div>
  )
}

/**
 * On-call escalation settings. Turns "an email you missed" into "you woke up".
 */
export default function OnCallPanel() {
  const qc = useQueryClient()
  const { data: policies = [] } = useQuery({
    queryKey: ["escalation-policies"], queryFn: listPolicies,
  })
  const [editing, setEditing] = useState<string | "new" | null>(null)
  const [tested, setTested] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ["escalation-policies"] })

  const remove = useMutation({ mutationFn: deletePolicy, onSuccess: invalidate })
  const toggle = useMutation({
    mutationFn: (p: EscalationPolicy) => updatePolicy(p.id, { is_active: !p.is_active }),
    onSuccess: invalidate,
  })
  const test = useMutation({
    mutationFn: previewPolicy,
    onSuccess: (res) => { setTested(res.to); setTimeout(() => setTested(null), 4000) },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      setError(typeof d === "string" ? d : "Could not send the test page.")
    },
  })

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <BellRing size={15} className="text-primary" />
        <h3 className="text-sm font-semibold">On-call escalation</h3>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        When something serious happens, keep reaching you — and then someone else — until
        one of you says “I’ve got it”.
      </p>

      {policies.length === 0 && editing !== "new" && (
        <p className="mb-3 rounded-lg border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
          No on-call policy yet. Alerts are sent once, by email.
        </p>
      )}

      <div className="mb-3 space-y-2">
        {policies.map((p) => (
          editing === p.id ? (
            <PolicyEditor
              key={p.id} initial={p}
              onCancel={() => setEditing(null)}
              onSaved={() => { setEditing(null); invalidate() }}
            />
          ) : (
            <div key={p.id} className="rounded-lg border border-border p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="flex items-center gap-1.5 text-[13px] font-medium">
                    {p.name}
                    {p.is_default && (
                      <span className="flex items-center gap-1 rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                        <Star size={9} /> All servers
                      </span>
                    )}
                    {!p.is_active && (
                      <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        Off
                      </span>
                    )}
                  </p>
                  <ul className="mt-1.5 space-y-0.5">
                    {p.summary.map((line, i) => (
                      <li key={i} className="text-[11.5px] text-muted-foreground">{line}</li>
                    ))}
                  </ul>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <button title="Send a test page" disabled={test.isPending}
                    onClick={() => { setError(null); test.mutate(p.id) }}
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
                    {tested ? <Check size={14} className="text-emerald-600" /> : <Send size={14} />}
                  </button>
                  <button title={p.is_active ? "Turn off" : "Turn on"}
                    onClick={() => toggle.mutate(p)}
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
                    <Power size={14} />
                  </button>
                  <Button size="sm" variant="ghost" onClick={() => setEditing(p.id)}>Edit</Button>
                  <button title="Delete" onClick={() => remove.mutate(p.id)}
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-red-500/10 hover:text-red-600">
                    <Trash2 size={14} />
                  </button>
                </div>
              </div>
            </div>
          )
        ))}
      </div>

      {tested && (
        <p className="mb-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-700 dark:text-emerald-400">
          Test page sent to {tested}.
        </p>
      )}
      {error && (
        <p className="mb-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      {editing === "new" ? (
        <PolicyEditor
          onCancel={() => setEditing(null)}
          onSaved={() => { setEditing(null); invalidate() }}
        />
      ) : editing === null ? (
        <Button size="sm" variant="outline" onClick={() => setEditing("new")}>
          <Plus size={14} /> {policies.length ? "Add another policy" : "Set up on-call"}
        </Button>
      ) : null}
    </div>
  )
}

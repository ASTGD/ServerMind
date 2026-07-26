import { useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import Editor from "@monaco-editor/react"
import {
  BookMarked, Plus, Loader2, Trash2, Power, Info, Wand2, Search, Lock,
} from "lucide-react"
import {
  listRunbooks, createRunbook, updateRunbook, deleteRunbook, previewMatch,
  builtInProcedures, type OsFamily, type Runbook, type RunbookMode,
} from "@/api/runbooks"
import { Button, EmptyState } from "@/components/ui"
import { cn } from "@/lib/utils"

const input =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary"
const label = "mb-1 block text-xs font-medium text-muted-foreground"

const STARTER = `## When to use this
Describe the situation this procedure is for.

## Steps
1. Look first — a read-only check that tells you what is actually wrong.
2. The change that fixes it.
3. Verify: prove the problem is gone, don't assume.

## Watch out for
- Anything that has bitten you before on this setup.
`

function detail(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return typeof d === "string" ? d : fallback
}

/** "Would this actually fire?" — the difference between writing a runbook and trusting it. */
function MatchTester() {
  const [message, setMessage] = useState("")
  const test = useMutation({ mutationFn: (m: string) => previewMatch(m) })

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <Search size={15} className="text-primary" />
        <h3 className="text-sm font-semibold">Try a message</h3>
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Type what someone would say and see which procedure Ally would follow. Free — this
        only checks the trigger phrases.
      </p>
      <div className="flex gap-2">
        <input
          className={input} placeholder="the checkout page is broken"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && message.trim()) test.mutate(message.trim()) }}
        />
        <Button size="sm" disabled={!message.trim() || test.isPending}
          onClick={() => test.mutate(message.trim())}>
          {test.isPending ? <Loader2 size={13} className="animate-spin" /> : "Check"}
        </Button>
      </div>
      {test.data && (
        <div className={cn(
          "mt-3 rounded-lg border px-3 py-2 text-xs",
          test.data.matched?.is_custom
            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
            : "border-border bg-muted/50 text-muted-foreground",
        )}>
          {test.data.explanation}
          {test.data.matched?.is_mission && (
            <span className="ml-1 opacity-80">It would run as a step-by-step mission.</span>
          )}
        </div>
      )}
    </div>
  )
}

function BuiltIns() {
  const { data } = useQuery({ queryKey: ["built-in-procedures"], queryFn: builtInProcedures })
  const [open, setOpen] = useState(false)
  if (!data) return null
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 text-left">
        <Info size={15} className="text-primary" />
        <h3 className="flex-1 text-sm font-semibold">
          What ServerAlly already knows ({data.procedures.length})
        </h3>
        <span className="text-xs text-muted-foreground">{open ? "Hide" : "Show"}</span>
      </button>
      {open && (
        <>
          <p className="mb-2 mt-2 text-xs text-muted-foreground">
            Ally follows these unless one of your own runbooks matches better. Yours wins on an
            equal match — so write one only where your way differs.
          </p>
          <ul className="grid gap-1 sm:grid-cols-2">
            {data.procedures.map((p) => (
              <li key={p.slug} className="text-[11.5px] text-muted-foreground">
                <span className="font-medium text-foreground">{p.title}</span>
                {p.is_mission && <span className="ml-1 opacity-70">· step-by-step</span>}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

function RunbookEditor({ initial, bodyLimit, onCancel, onSaved }: {
  initial?: Runbook
  bodyLimit: number
  onCancel: () => void
  onSaved: () => void
}) {
  const [title, setTitle] = useState(initial?.title ?? "")
  const [description, setDescription] = useState(initial?.description ?? "")
  const [triggerText, setTriggerText] = useState((initial?.triggers ?? []).join(", "))
  const [mode, setMode] = useState<RunbookMode>(initial?.mode ?? "guide")
  const [osFamily, setOsFamily] = useState<OsFamily>(initial?.os_family ?? "any")
  const [body, setBody] = useState(initial?.body ?? STARTER)
  const [budget, setBudget] = useState(initial?.budget ?? 20)
  const [error, setError] = useState<string | null>(null)

  const triggers = useMemo(
    () => triggerText.split(",").map((t) => t.trim()).filter(Boolean),
    [triggerText],
  )

  const payload = {
    title: title.trim(),
    description: description.trim() || null,
    triggers,
    body,
    mode,
    os_family: osFamily,
    budget: mode === "mission" ? budget : null,
  }

  const save = useMutation({
    mutationFn: () => (initial ? updateRunbook(initial.id, payload) : createRunbook(payload)),
    onSuccess: onSaved,
    onError: (e) => setError(detail(e, "Could not save this runbook.")),
  })

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <h3 className="mb-3 text-sm font-semibold">
        {initial ? `Edit “${initial.title}”` : "New runbook"}
      </h3>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={label}>Name</label>
          <input className={input} placeholder="WooCommerce checkout triage"
            value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div>
          <label className={label}>What is it for? <span className="text-muted-foreground/70">(optional)</span></label>
          <input className={input} placeholder="Our order of checks when a store can't take payments"
            value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <div className="sm:col-span-2">
          <label className={label}>
            Use it when someone says… <span className="text-muted-foreground/70">(comma separated)</span>
          </label>
          <input className={input} placeholder="checkout is broken, payment failing, orders not going through"
            value={triggerText} onChange={(e) => setTriggerText(e.target.value)} />
          <p className="mt-1 text-[11px] text-muted-foreground">
            Use the words someone would actually type. Single common words like “site” are too
            broad — they would match almost every message.
          </p>
        </div>
        <div>
          <label className={label}>How should Ally use it?</label>
          <select className={input} value={mode}
            onChange={(e) => setMode(e.target.value as RunbookMode)}>
            <option value="guide">Follow it while answering</option>
            <option value="mission">Work through it step by step</option>
          </select>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {mode === "guide"
              ? "Ally uses it to shape its answer and its plan."
              : "Ally offers a mission and works through the steps, asking before anything risky."}
          </p>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className={label}>Only on</label>
            <select className={input} value={osFamily}
              onChange={(e) => setOsFamily(e.target.value as OsFamily)}>
              <option value="any">Any server</option>
              <option value="linux">Linux</option>
              <option value="windows">Windows</option>
            </select>
          </div>
          {mode === "mission" && (
            <div>
              <label className={label}>Steps allowed</label>
              <input type="number" min={5} max={40} className={input} value={budget}
                onChange={(e) => setBudget(Math.min(40, Math.max(5, Number(e.target.value) || 20)))} />
            </div>
          )}
        </div>
      </div>

      <div className="mt-3">
        <div className="mb-1 flex items-center justify-between">
          <label className={label}>The procedure</label>
          <span className={cn("text-[11px]",
            body.length > bodyLimit ? "text-red-600 dark:text-red-400" : "text-muted-foreground")}>
            {body.length.toLocaleString()} / {bodyLimit.toLocaleString()}
          </span>
        </div>
        <div className="overflow-hidden rounded-lg border border-border">
          <Editor
            height="360px" defaultLanguage="markdown" value={body}
            theme="vs-dark"
            onChange={(v) => setBody(v ?? "")}
            options={{
              minimap: { enabled: false }, fontSize: 13, wordWrap: "on",
              lineNumbers: "off", scrollBeyondLastLine: false, padding: { top: 10 },
            }}
          />
        </div>
        <p className="mt-1 text-[11px] text-muted-foreground">
          Write it as you would explain it to a new colleague: what to look at first, what to
          change, and how to prove it worked. Ally still asks before anything destructive — a
          runbook cannot switch that off.
        </p>
      </div>

      {error && (
        <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      )}

      <div className="mt-3 flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button size="sm" disabled={save.isPending || !title.trim() || !triggers.length}
          onClick={() => { setError(null); save.mutate() }}>
          {save.isPending ? <><Loader2 size={13} className="animate-spin" /> Saving…</> : "Save runbook"}
        </Button>
      </div>
    </div>
  )
}

/**
 * Runbooks — the account's own expert procedures, followed by Ally in place of its
 * built-in ones.
 */
export default function Runbooks() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ["runbooks"], queryFn: listRunbooks })
  const [editing, setEditing] = useState<string | "new" | null>(null)

  const invalidate = () => qc.invalidateQueries({ queryKey: ["runbooks"] })
  const toggle = useMutation({
    mutationFn: (r: Runbook) => updateRunbook(r.id, { is_active: !r.is_active }),
    onSuccess: invalidate,
  })
  const remove = useMutation({ mutationFn: deleteRunbook, onSuccess: invalidate })

  const runbooks = data?.runbooks ?? []
  const canEdit = data?.can_edit ?? false

  return (
    <div>
      <header className="mb-4">
        <h1 className="flex items-center gap-2 text-h1 text-foreground">
          <BookMarked className="h-5 w-5 text-primary" /> Runbooks
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Teach Ally how <em>you</em> do things. When one of your runbooks matches, Ally follows
          it instead of its own approach.
        </p>
      </header>

      {!canEdit && !isLoading && (
        <p className="mb-4 flex items-start gap-2 rounded-xl border border-border bg-muted/40 px-4 py-3 text-xs text-muted-foreground">
          <Lock size={14} className="mt-0.5 shrink-0" />
          <span>
            You can read these procedures, but only the account owner or an admin can change
            them — a runbook tells Ally how to work on the servers, so it needs the highest
            permission.
          </span>
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.6fr_1fr] lg:items-start">
        <div className="min-w-0 space-y-3">
          {editing === "new" && data && (
            <RunbookEditor
              bodyLimit={data.body_limit}
              onCancel={() => setEditing(null)}
              onSaved={() => { setEditing(null); invalidate() }}
            />
          )}

          {isLoading ? (
            <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>
          ) : runbooks.length === 0 && editing !== "new" ? (
            <EmptyState
              icon={BookMarked}
              title="No runbooks yet"
              description="Ally uses its own expert procedures. Add a runbook where your way differs — an order of checks, a client's quirk, a step someone always forgets."
              action={canEdit ? (
                <Button size="sm" onClick={() => setEditing("new")}>
                  <Plus size={14} /> Write your first runbook
                </Button>
              ) : undefined}
            />
          ) : (
            runbooks.map((r) => (
              editing === r.id && data ? (
                <RunbookEditor
                  key={r.id} initial={r} bodyLimit={data.body_limit}
                  onCancel={() => setEditing(null)}
                  onSaved={() => { setEditing(null); invalidate() }}
                />
              ) : (
                <div key={r.id} className="rounded-xl border border-border bg-card p-4">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="flex flex-wrap items-center gap-1.5 text-sm font-semibold">
                        {r.title}
                        {r.mode === "mission" && (
                          <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                            Step by step
                          </span>
                        )}
                        {r.os_family !== "any" && (
                          <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                            {r.os_family}
                          </span>
                        )}
                        {!r.is_active && (
                          <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                            Off
                          </span>
                        )}
                      </p>
                      {r.description && (
                        <p className="mt-0.5 text-xs text-muted-foreground">{r.description}</p>
                      )}
                      <p className="mt-1.5 text-[11.5px] text-muted-foreground">
                        Used when someone says: {r.triggers.map((t) => `“${t}”`).join(", ")}
                      </p>
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        {r.times_used > 0
                          ? `Followed ${r.times_used} time${r.times_used === 1 ? "" : "s"}`
                          : "Not used yet"}
                      </p>
                      {/* Our own procedures carry hard-won specifics; replacing one should be
                          a choice, not a surprise found during an incident. */}
                      {r.shadows && (
                        <p className="mt-1.5 flex items-start gap-1.5 rounded-lg bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-800 dark:text-amber-300">
                          <Wand2 size={11} className="mt-0.5 shrink-0" />
                          This replaces ServerAlly’s built-in “{r.shadows}” procedure for these
                          phrases.
                        </p>
                      )}
                    </div>
                    {canEdit && (
                      <div className="flex shrink-0 items-center gap-1">
                        <button title={r.is_active ? "Turn off" : "Turn on"}
                          onClick={() => toggle.mutate(r)}
                          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
                          <Power size={14} />
                        </button>
                        <Button size="sm" variant="ghost" onClick={() => setEditing(r.id)}>Edit</Button>
                        <button title="Delete" onClick={() => remove.mutate(r.id)}
                          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-red-500/10 hover:text-red-600">
                          <Trash2 size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              )
            ))
          )}

          {canEdit && runbooks.length > 0 && editing === null && (
            <Button size="sm" variant="outline" onClick={() => setEditing("new")}>
              <Plus size={14} /> New runbook
            </Button>
          )}
          {data && runbooks.length >= data.limit && (
            <p className="text-[11px] text-muted-foreground">
              You have the maximum of {data.limit} runbooks. Every one is offered to Ally on
              each message, so the library is capped — delete one you no longer use.
            </p>
          )}
        </div>

        <aside className="min-w-0 space-y-3">
          <MatchTester />
          <BuiltIns />
        </aside>
      </div>
    </div>
  )
}

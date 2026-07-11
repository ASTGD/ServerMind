import { useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import type { AxiosError } from "axios"
import {
  Play,
  Loader2,
  CheckCircle2,
  XCircle,
  Trash2,
  Plus,
  AlertTriangle,
} from "lucide-react"
import {
  runEvals,
  captureEvalCase,
  deleteEvalCase,
  EVAL_CATEGORIES,
  type EvalRunResult,
} from "@/api/dev"

function errMsg(e: unknown): string {
  const detail = (e as AxiosError<{ detail?: unknown }>)?.response?.data?.detail
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) return detail.map((d) => (d as { msg?: string })?.msg).filter(Boolean).join("; ")
  return (e as Error)?.message || "Something went wrong"
}

function CategoryBars({ result }: { result: EvalRunResult }) {
  return (
    <div className="space-y-1.5">
      {result.by_category.map((c) => {
        const pct = c.total ? Math.round((100 * c.passed) / c.total) : 0
        const ok = c.passed === c.total
        return (
          <div key={c.category} className="flex items-center gap-3 text-sm">
            <span className="w-36 shrink-0 font-mono text-xs text-muted-foreground">{c.category}</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
              <div
                className={`h-full rounded-full ${ok ? "bg-emerald-500" : "bg-red-500"}`}
                style={{ width: `${pct}%` }}
              />
            </div>
            <span className={`w-14 shrink-0 text-right text-xs tabular-nums ${ok ? "text-muted-foreground" : "text-red-500 font-medium"}`}>
              {c.passed}/{c.total}
            </span>
          </div>
        )
      })}
    </div>
  )
}

export default function EvalRunner() {
  const qc = useQueryClient()
  const evals = useQuery({ queryKey: ["dev-evals"], queryFn: runEvals })
  const [form, setForm] = useState({ category: "skill-routing", input: "", expected: "", os: "ubuntu" })

  const invalidate = () => qc.invalidateQueries({ queryKey: ["dev-evals"] })
  const add = useMutation({
    mutationFn: () => captureEvalCase(form),
    onSuccess: () => {
      setForm({ category: "skill-routing", input: "", expected: "", os: "ubuntu" })
      invalidate()
    },
  })
  const del = useMutation({ mutationFn: (id: string) => deleteEvalCase(id), onSuccess: invalidate })

  const result = evals.data
  const canAdd = form.input.trim() && form.expected.trim() && !add.isPending

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Run the whole deterministic suite (corpus + your captured cases) — offline, no AI cost.
        </p>
        <button
          onClick={() => evals.refetch()}
          disabled={evals.isFetching}
          className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-50"
        >
          {evals.isFetching ? <Loader2 size={15} className="animate-spin" /> : <Play size={15} />}
          {evals.isFetching ? "Running…" : "Re-run"}
        </button>
      </div>

      {evals.isError && (
        <div className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-600 dark:text-red-400">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>{errMsg(evals.error)}</span>
        </div>
      )}

      {result && (
        <>
          {/* Summary */}
          <section className="rounded-xl border border-border bg-card p-5">
            <div className="mb-4 flex items-center gap-3">
              {result.summary.ok ? (
                <CheckCircle2 size={20} className="text-emerald-500" />
              ) : (
                <XCircle size={20} className="text-red-500" />
              )}
              <span className="text-lg font-semibold text-foreground">
                {result.summary.passed} / {result.summary.total} passing
              </span>
              {!result.summary.ok && (
                <span className="rounded-full bg-red-500/10 px-2.5 py-0.5 text-xs font-medium text-red-600 dark:text-red-400">
                  {result.failures.length} failing
                </span>
              )}
            </div>
            <CategoryBars result={result} />
          </section>

          {/* Failures */}
          {result.failures.length > 0 && (
            <section className="rounded-xl border border-red-500/30 bg-card">
              <div className="border-b border-border px-4 py-2.5 text-sm font-medium text-red-600 dark:text-red-400">
                Failures
              </div>
              <div className="divide-y divide-border">
                {result.failures.map((f, i) => (
                  <div key={i} className="px-4 py-3 text-sm">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground">{f.category}</span>
                      {f.source === "captured" && (
                        <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400">captured</span>
                      )}
                    </div>
                    <div className="mt-1 font-mono text-xs text-foreground/90">{f.input}</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      got <b className="text-red-500">{f.got}</b>, expected <b className="text-foreground">{f.expected}</b>
                      {f.error ? ` — ${f.error}` : ""}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Captured cases */}
          <section className="rounded-xl border border-border bg-card">
            <div className="border-b border-border px-4 py-2.5 text-sm font-medium text-foreground">
              Captured cases <span className="text-muted-foreground">({result.captured.length})</span>
            </div>
            {result.captured.length === 0 ? (
              <p className="px-4 py-3 text-xs text-muted-foreground">
                None yet. Capture one from the Inspector, or add one below — it runs alongside the corpus.
              </p>
            ) : (
              <div className="divide-y divide-border">
                {result.captured.map((c) => (
                  <div key={c.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                    {c.passed ? (
                      <CheckCircle2 size={15} className="shrink-0 text-emerald-500" />
                    ) : (
                      <XCircle size={15} className="shrink-0 text-red-500" />
                    )}
                    <span className="w-32 shrink-0 font-mono text-xs text-muted-foreground">{c.category}</span>
                    <span className="min-w-0 flex-1 truncate font-mono text-xs text-foreground/90" title={c.input}>{c.input}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">→ {c.expected}</span>
                    <button
                      onClick={() => del.mutate(c.id)}
                      className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-red-500"
                      title="Delete"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Add a case */}
            <div className="border-t border-border p-4">
              <div className="flex flex-wrap items-end gap-2">
                <label className="flex flex-col gap-1">
                  <span className="text-[11px] text-muted-foreground">category</span>
                  <select
                    value={form.category}
                    onChange={(e) => setForm({ ...form, category: e.target.value })}
                    className="rounded-lg border border-border bg-background px-2 py-1.5 text-xs text-foreground"
                  >
                    {EVAL_CATEGORIES.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </label>
                <label className="flex min-w-[180px] flex-1 flex-col gap-1">
                  <span className="text-[11px] text-muted-foreground">input (message or command)</span>
                  <input
                    value={form.input}
                    onChange={(e) => setForm({ ...form, input: e.target.value })}
                    placeholder="my wordpress site is down"
                    className="rounded-lg border border-border bg-background px-2 py-1.5 text-xs text-foreground"
                  />
                </label>
                <label className="flex w-40 flex-col gap-1">
                  <span className="text-[11px] text-muted-foreground">expected</span>
                  <input
                    value={form.expected}
                    onChange={(e) => setForm({ ...form, expected: e.target.value })}
                    placeholder="wordpress-rescue"
                    className="rounded-lg border border-border bg-background px-2 py-1.5 text-xs text-foreground"
                  />
                </label>
                <label className="flex w-24 flex-col gap-1">
                  <span className="text-[11px] text-muted-foreground">os</span>
                  <input
                    value={form.os}
                    onChange={(e) => setForm({ ...form, os: e.target.value })}
                    className="rounded-lg border border-border bg-background px-2 py-1.5 text-xs text-foreground"
                  />
                </label>
                <button
                  onClick={() => add.mutate()}
                  disabled={!canAdd}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {add.isPending ? <Loader2 size={13} className="animate-spin" /> : <Plus size={13} />}
                  Add case
                </button>
              </div>
              {add.isError && <p className="mt-2 text-xs text-red-500">{errMsg(add.error)}</p>}
              <p className="mt-2 text-[11px] text-muted-foreground">
                Expected: a skill slug (or <code>None</code>) for routing; <code>blocked</code>/<code>confirm</code>/<code>ok</code> for safety;
                {" "}<code>read-only</code>/<code>mutating</code> for the read-only guard.
              </p>
            </div>
          </section>
        </>
      )}
    </div>
  )
}

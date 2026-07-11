import { useQuery } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import { Loader2, RefreshCw, AlertTriangle } from "lucide-react"
import { getActivity, type ActivityData } from "@/api/dev"

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border bg-card px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-xl font-semibold text-foreground">{value}</div>
    </div>
  )
}

function money(n: number): string {
  return n >= 1 ? `$${n.toFixed(2)}` : `$${n.toFixed(4)}`
}

function Table({ data }: { data: ActivityData }) {
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card">
      <div className="border-b border-border px-4 py-2.5 text-sm font-medium text-foreground">
        Recent AI calls <span className="text-muted-foreground">({data.recent.length})</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-border text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">when</th>
              <th className="px-3 py-2 font-medium">feature</th>
              <th className="px-3 py-2 font-medium">model</th>
              <th className="px-3 py-2 font-medium">skill</th>
              <th className="px-3 py-2 text-right font-medium">in / out</th>
              <th className="px-3 py-2 text-right font-medium">cache</th>
              <th className="px-3 py-2 text-right font-medium">cost</th>
              <th className="px-3 py-2 font-medium">server</th>
              <th className="px-3 py-2 font-medium">status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {data.recent.length === 0 && (
              <tr>
                <td colSpan={9} className="px-3 py-4 text-center text-muted-foreground">
                  No AI calls recorded yet.
                </td>
              </tr>
            )}
            {data.recent.map((c, i) => (
              <tr key={i} className="hover:bg-accent/30">
                <td className="whitespace-nowrap px-3 py-2 text-muted-foreground">
                  {c.created_at ? formatDistanceToNow(new Date(c.created_at), { addSuffix: true }) : "—"}
                </td>
                <td className="px-3 py-2 font-medium text-foreground">{c.feature}</td>
                <td className="whitespace-nowrap px-3 py-2 font-mono text-muted-foreground">{c.model.replace("claude-", "")}</td>
                <td className="px-3 py-2 text-muted-foreground">{c.skill || "—"}</td>
                <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums text-muted-foreground">
                  {c.input_tokens.toLocaleString()} / {c.output_tokens.toLocaleString()}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">{c.cache_read_tokens.toLocaleString()}</td>
                <td className="px-3 py-2 text-right tabular-nums text-foreground">{money(c.cost_usd)}</td>
                <td className="max-w-[10rem] truncate px-3 py-2 text-muted-foreground" title={c.server || ""}>{c.server || "—"}</td>
                <td className="px-3 py-2">
                  {c.status === "ok" ? (
                    <span className="text-emerald-600 dark:text-emerald-400">ok</span>
                  ) : (
                    <span className="text-red-500">{c.status}</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

export default function Activity() {
  const { data, isLoading, isError, error, refetch, isFetching } = useQuery({
    queryKey: ["dev-activity"],
    queryFn: getActivity,
  })

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Every AI call Ally made — counts, model, and cost. The ledger stores no prompt or
          response content (no secrets by design).
        </p>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="inline-flex items-center gap-2 rounded-lg border border-border px-3 py-1.5 text-sm font-medium text-foreground transition-colors hover:bg-accent disabled:opacity-50"
        >
          {isFetching ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
          Refresh
        </button>
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 size={16} className="animate-spin" /> Loading…
        </div>
      )}

      {isError && (
        <div className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-600 dark:text-red-400">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>{(error as Error)?.message || "Failed to load activity"}</span>
        </div>
      )}

      {data && (
        <>
          <div className="grid grid-cols-3 gap-3">
            <Kpi label="Cost this month" value={money(data.summary.cost_usd)} />
            <Kpi label="Actions" value={data.summary.actions.toLocaleString()} />
            <Kpi label="Model calls" value={data.summary.calls.toLocaleString()} />
          </div>

          {data.by_feature.length > 0 && (
            <section className="rounded-xl border border-border bg-card p-4">
              <div className="mb-2 text-sm font-medium text-foreground">Cost by feature (this month)</div>
              <div className="flex flex-wrap gap-2">
                {data.by_feature.map((f) => (
                  <span key={f.feature} className="inline-flex items-center gap-2 rounded-full bg-muted px-3 py-1 text-xs">
                    <span className="font-medium text-foreground">{f.feature}</span>
                    <span className="text-muted-foreground">{money(f.cost_usd)} · {f.calls} calls</span>
                  </span>
                ))}
              </div>
            </section>
          )}

          <Table data={data} />
        </>
      )}
    </div>
  )
}

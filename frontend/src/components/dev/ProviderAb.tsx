import { useEffect, useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Loader2, AlertTriangle, Info, Scale } from "lucide-react"
import { getProviderAb, type ProviderAb, type OaTier } from "@/api/dev"

function money(n: number): string {
  return n >= 1 ? `$${n.toFixed(2)}` : `$${n.toFixed(4)}`
}

const TIER_ORDER: OaTier[] = ["top", "mid", "small"]

/** big verdict number, colored by who wins */
function Verdict({ data }: { data: ProviderAb }) {
  const t = data.totals
  const d = t.delta_pct
  const openaiCheaper = d != null && d < 0
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <div className="rounded-xl border border-border bg-card px-4 py-3">
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Claude (real, cached)</div>
        <div className="mt-0.5 text-2xl font-semibold text-foreground">{money(t.claude_usd)}</div>
        <div className="text-[11px] text-muted-foreground">this month · {t.cache_hit_pct.toFixed(0)}% cache hit</div>
      </div>
      <div className="rounded-xl border border-border bg-card px-4 py-3">
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">OpenAI-equivalent</div>
        <div className="mt-0.5 text-2xl font-semibold text-foreground">{money(t.openai_usd)}</div>
        <div className="text-[11px] text-muted-foreground">same tokens · OpenAI caching</div>
      </div>
      <div className={`rounded-xl border px-4 py-3 ${openaiCheaper ? "border-amber-500/30 bg-amber-500/5" : "border-emerald-500/30 bg-emerald-500/5"}`}>
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Difference</div>
        <div className={`mt-0.5 text-2xl font-semibold ${openaiCheaper ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400"}`}>
          {d == null ? "—" : `${d > 0 ? "+" : ""}${d.toFixed(0)}%`}
        </div>
        <div className="text-[11px] text-muted-foreground">
          {d == null ? "no usage yet" : openaiCheaper ? "OpenAI cheaper on fuel" : "Claude cheaper on fuel"}
        </div>
      </div>
    </div>
  )
}

export default function ProviderAb() {
  // Editable OpenAI prices ($/M) — seeded from the backend defaults, overridable so
  // management can plug in OpenAI's real quote and see the true number on real usage.
  const [prices, setPrices] = useState<Record<OaTier, { in: number; out: number }>>({
    top: { in: 5, out: 15 },
    mid: { in: 2.5, out: 10 },
    small: { in: 0.15, out: 0.6 },
  })
  const [labels, setLabels] = useState<Record<OaTier, string>>({ top: "", mid: "", small: "" })

  const run = useMutation({
    mutationFn: (p?: Record<OaTier, { in: number; out: number }>) => getProviderAb(p),
    onSuccess: (d) => {
      // adopt the backend's tier labels + seed prices on first load
      setLabels({ top: d.tiers.top.label, mid: d.tiers.mid.label, small: d.tiers.small.label })
    },
  })

  // Run once on mount with the backend defaults.
  useEffect(() => {
    run.mutate(undefined)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const data = run.data
  const setPrice = (tier: OaTier, field: "in" | "out", v: string) =>
    setPrices((p) => ({ ...p, [tier]: { ...p[tier], [field]: Number(v) || 0 } }))

  return (
    <div className="space-y-6">
      <div className="flex items-start gap-2 text-sm text-muted-foreground">
        <Scale size={16} className="mt-0.5 shrink-0 text-primary" />
        <p>
          Would moving to OpenAI actually be cheaper? This re-prices <strong>this month's real token
          usage</strong> (from the ledger) on Claude vs an OpenAI-equivalent model — no live calls, no
          OpenAI key. Edit the OpenAI prices to match a real quote.
        </p>
      </div>

      {run.isPending && !data && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 size={16} className="animate-spin" /> Computing…
        </div>
      )}

      {run.isError && (
        <div className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-4 text-sm text-red-600 dark:text-red-400">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <span>{(run.error as Error)?.message || "Failed to compute the A/B"}</span>
        </div>
      )}

      {data && (
        <>
          <Verdict data={data} />

          {/* Editable OpenAI price assumptions */}
          <section className="rounded-xl border border-border bg-card p-4">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-sm font-medium text-foreground">OpenAI prices ($ per 1M tokens)</div>
              <button
                onClick={() => run.mutate(prices)}
                disabled={run.isPending}
                className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                {run.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
                Recompute
              </button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-muted-foreground">
                  <tr>
                    <th className="py-1 pr-3 font-medium">tier</th>
                    <th className="py-1 pr-3 font-medium">maps from</th>
                    <th className="py-1 pr-3 text-right font-medium">input $/M</th>
                    <th className="py-1 text-right font-medium">output $/M</th>
                  </tr>
                </thead>
                <tbody>
                  {TIER_ORDER.map((tier) => (
                    <tr key={tier}>
                      <td className="py-1.5 pr-3 font-mono text-foreground">{tier}</td>
                      <td className="py-1.5 pr-3 text-muted-foreground">{labels[tier] || "—"}</td>
                      <td className="py-1.5 pr-3 text-right">
                        <input
                          type="number" step="0.01" min="0" value={prices[tier].in}
                          onChange={(e) => setPrice(tier, "in", e.target.value)}
                          className="w-20 rounded border border-border bg-background px-2 py-1 text-right tabular-nums outline-none focus:border-primary"
                        />
                      </td>
                      <td className="py-1.5 text-right">
                        <input
                          type="number" step="0.01" min="0" value={prices[tier].out}
                          onChange={(e) => setPrice(tier, "out", e.target.value)}
                          className="w-20 rounded border border-border bg-background px-2 py-1 text-right tabular-nums outline-none focus:border-primary"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {/* Per-feature breakdown */}
          <section className="overflow-hidden rounded-xl border border-border bg-card">
            <div className="border-b border-border px-4 py-2.5 text-sm font-medium text-foreground">
              By feature (this month)
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="border-b border-border text-muted-foreground">
                  <tr>
                    <th className="px-3 py-2 font-medium">feature</th>
                    <th className="px-3 py-2 text-right font-medium">calls</th>
                    <th className="px-3 py-2 text-right font-medium">Claude $</th>
                    <th className="px-3 py-2 text-right font-medium">OpenAI $</th>
                    <th className="px-3 py-2 text-right font-medium">Δ</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.by_feature.length === 0 && (
                    <tr><td colSpan={5} className="px-3 py-4 text-center text-muted-foreground">No usage this month.</td></tr>
                  )}
                  {data.by_feature.map((f) => {
                    const d = f.claude_usd > 0 ? (f.openai_usd - f.claude_usd) / f.claude_usd * 100 : null
                    return (
                      <tr key={f.feature} className="hover:bg-accent/30">
                        <td className="px-3 py-2 font-medium text-foreground">{f.feature}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">{f.calls}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-foreground">{money(f.claude_usd)}</td>
                        <td className="px-3 py-2 text-right tabular-nums text-foreground">{money(f.openai_usd)}</td>
                        <td className={`px-3 py-2 text-right tabular-nums ${d != null && d < 0 ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                          {d == null ? "—" : `${d > 0 ? "+" : ""}${d.toFixed(0)}%`}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
                {data.by_feature.length > 0 && (
                  <tfoot className="border-t border-border">
                    <tr className="font-semibold text-foreground">
                      <td className="px-3 py-2">Total</td>
                      <td />
                      <td className="px-3 py-2 text-right tabular-nums">{money(data.totals.claude_usd)}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{money(data.totals.openai_usd)}</td>
                      <td className={`px-3 py-2 text-right tabular-nums ${data.totals.delta_pct != null && data.totals.delta_pct < 0 ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400"}`}>
                        {data.totals.delta_pct == null ? "—" : `${data.totals.delta_pct > 0 ? "+" : ""}${data.totals.delta_pct.toFixed(0)}%`}
                      </td>
                    </tr>
                  </tfoot>
                )}
              </table>
            </div>
          </section>

          {/* Honest caveats */}
          <section className="rounded-xl border border-border bg-muted/30 p-4">
            <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <Info size={13} /> How to read this
            </div>
            <ul className="space-y-1.5 text-xs leading-relaxed text-muted-foreground">
              {data.caveats.map((c, i) => (
                <li key={i} className="flex gap-2">
                  <span className="text-muted-foreground/50">•</span>
                  <span>{c}</span>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  )
}

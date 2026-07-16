import { useQuery } from "@tanstack/react-query"
import { Link2 } from "lucide-react"
import { getEntitlementLog } from "@/api/dev"

const when = (s: string | null) =>
  s ? new Date(s).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "—"

/** The WHMCS↔ServerAlly seam, made visible.
 *
 *  This is where "the customer paid but is still on Free" gets answered: if the event
 *  isn't here, WHMCS never reached us. Renewal is silence by design (SAAS-LAUNCH-PLAN
 *  §3.3) — a paying customer's renewal writes NOTHING, so a quiet log is normal. What
 *  you're looking for is a missing event, or a reconcile that keeps correcting drift.
 */
export default function AdminEntitlements() {
  const { data: events = [], isLoading } = useQuery({
    queryKey: ["admin-entitlements"],
    queryFn: getEntitlementLog,
    refetchInterval: 60_000,
  })

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted-foreground">
              <th className="px-4 py-2 font-medium">When</th>
              <th className="px-4 py-2 font-medium">Email</th>
              <th className="px-4 py-2 font-medium">→ Plan</th>
              <th className="px-4 py-2 font-medium">Source</th>
              <th className="px-4 py-2 font-medium">WHMCS ref</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading ? (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-muted-foreground">Loading…</td></tr>
            ) : events.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-sm text-muted-foreground">
                  No billing events yet — WHMCS has never called this deployment.
                </td>
              </tr>
            ) : (
              events.map((e, i) => (
                <tr key={i} className="hover:bg-muted/50">
                  <td className="px-4 py-2 text-muted-foreground">{when(e.created_at)}</td>
                  <td className="px-4 py-2 text-foreground">{e.email || "—"}</td>
                  <td className="px-4 py-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        e.plan === "pro" ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {e.plan}
                    </span>
                    {e.created && (
                      <span className="ml-2 text-xs text-emerald-600 dark:text-emerald-400">new account</span>
                    )}
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">
                    {e.action === "entitlement.reconcile" ? (
                      <span className="text-amber-600 dark:text-amber-400" title="Corrected by the nightly reconcile — an event had been missed">
                        reconcile{e.forced ? " (forced)" : ""}
                      </span>
                    ) : (
                      "billing event"
                    )}
                  </td>
                  <td className="px-4 py-2 text-muted-foreground">{e.reference || "—"}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
        <Link2 size={12} className="mt-0.5 shrink-0" />
        <span>
          A successful <strong>renewal writes nothing here</strong> — the customer was Pro
          and stays Pro, so silence is normal. A <strong>reconcile</strong> row means the
          nightly job found drift and corrected it: an event had been missed, which is
          worth understanding rather than ignoring.
        </span>
      </p>
    </div>
  )
}

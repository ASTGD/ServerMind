import { useOutletContext } from "react-router-dom"
import { Activity, CircleAlert, CircleCheck, ShieldCheck } from "lucide-react"
import type { SiteDetail } from "@/api/sites"
import { EmptyState } from "@/components/ui"

/**
 * Whether a visitor can actually reach this site.
 *
 * Checked from outside — from where a visitor is — because a check run on the server
 * itself passes while DNS is broken or a firewall blocks 443, which are exactly the
 * outages that matter.
 */
export default function SiteUptime() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  const u = site.uptime

  if (!u) {
    return (
      <EmptyState
        icon={Activity}
        title="This site is not being watched yet"
        description="Add an uptime monitor for it and ServerAlly will check it from outside every minute, and tell you the moment it stops answering."
      />
    )
  }

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-border bg-card p-4">
        <p className="flex items-center gap-2 text-sm font-medium text-foreground">
          {u.status === "up"
            ? <><CircleCheck size={15} className="text-emerald-600 dark:text-emerald-400" /> Up</>
            : <><CircleAlert size={15} className="text-red-600 dark:text-red-400" /> Down</>}
        </p>
        {u.error && <p className="mt-1 text-small text-destructive">{u.error}</p>}
        <dl className="mt-3 grid gap-2 text-small sm:grid-cols-3">
          {typeof u.response_ms === "number" && (
            <div><dt className="text-caption text-muted-foreground">Answered in</dt>
              <dd className="tabular-nums text-foreground">{u.response_ms} ms</dd></div>
          )}
          {u.last_checked && (
            <div><dt className="text-caption text-muted-foreground">Last checked</dt>
              <dd className="text-foreground">{new Date(u.last_checked).toLocaleString()}</dd></div>
          )}
          {typeof u.cert_days_left === "number" && (
            <div><dt className="text-caption text-muted-foreground">Certificate</dt>
              <dd className="flex items-center gap-1 text-foreground">
                <ShieldCheck size={12} /> {u.cert_days_left} days left
              </dd></div>
          )}
        </dl>
      </div>
    </div>
  )
}

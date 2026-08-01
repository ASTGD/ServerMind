import {
  AlertTriangle, ArrowUpCircle, CheckCircle2, Database, Loader2, Power, Trash2, XCircle,
} from "lucide-react"
import type { SiteApp } from "@/api/sites"
import { Button } from "@/components/ui"

/**
 * A Laravel deployment's condition, and the few commands that fix it.
 *
 * Deliberately not shaped like the WordPress screen. WordPress is content you administer;
 * Laravel is a codebase you deploy, so the questions are "is it in production mode", "are
 * migrations waiting", "is anything running the queue and the scheduler" — states, not
 * inventories. So this is a list of checks with a verdict, not a table of things.
 *
 * Two of them are worth the whole screen, because neither is visible from outside and both
 * are common: debug mode left on in production, and no scheduler entry in cron.
 */

interface Check {
  ok: boolean
  /** Amber rather than red: worth doing, but nothing is broken right now. */
  advisory?: boolean
  label: string
  detail: string
}

function checksFor(d: SiteApp): Check[] {
  const checks: Check[] = []

  // The most damaging Laravel misconfiguration there is. Laravel's debug page prints the
  // stack trace AND the environment — database password included — to anybody who can make
  // the site throw an error.
  if (d.debug_in_production) {
    checks.push({
      ok: false,
      label: "Debug mode is on, in production",
      detail: "When something goes wrong, visitors are shown the error page — which "
        + "includes this site's database password. Turn it off.",
    })
  } else if (d.debug) {
    checks.push({
      ok: true, advisory: true,
      label: `Debug mode is on (${d.environment})`,
      detail: "Fine while you are building. Make sure it is off before this goes live.",
    })
  } else {
    checks.push({ ok: true, label: "Debug mode is off", detail: "Visitors never see error details." })
  }

  // Nothing anywhere reports this failing, because from the application's point of view
  // nothing was ever asked to happen.
  checks.push(d.scheduler
    ? { ok: true, label: "The scheduler is running", detail: "Cron is calling Laravel every minute." }
    : {
      ok: false,
      label: "Nothing is running the scheduler",
      detail: "Laravel runs every scheduled job through one cron entry, and there is none. "
        + "Anything this site schedules — emails, reports, clean-ups — never happens, and "
        + "nothing reports an error.",
    })

  checks.push(d.queue_worker
    ? { ok: true, label: "A queue worker is running", detail: "Background jobs are being processed." }
    : {
      ok: true, advisory: true,
      label: "No queue worker is running",
      detail: "Only a problem if this site uses queued jobs — if it does, they are piling up.",
    })

  checks.push(d.storage_link
    ? { ok: true, label: "The uploads link is in place", detail: "Uploaded files can be served." }
    : {
      ok: true, advisory: true,
      label: "The uploads link is missing",
      detail: "If this site accepts uploads, they will not be visible to visitors.",
    })

  const cached = [d.cache_config, d.cache_routes].filter(Boolean).length
  checks.push(cached === 2
    ? {
      ok: true, label: "Configuration and routes are cached",
      detail: "The fast setting for a live site. Cache them again after each deploy.",
    }
    : {
      ok: true, advisory: d.environment === "production",
      label: "Configuration and routes are not fully cached",
      detail: d.environment === "production"
        ? "A production site runs noticeably faster with these cached."
        : "Normal while you are developing.",
    })

  return checks
}

export default function LaravelPanel({ data, onAct, busy }: {
  data: SiteApp
  onAct: (action: string) => void
  busy: string | null
}) {
  const checks = checksFor(data)
  const problems = checks.filter((c) => !c.ok).length
  const pending = data.pending_migrations ?? 0
  const disabled = busy !== null

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-card">
        <div className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
          <div className="min-w-0">
            <p className="text-sm font-medium text-foreground">
              Laravel {data.version} · PHP {data.php_version}
            </p>
            <p className="mt-0.5 text-small text-muted-foreground">
              Running as <span className="font-mono">{data.environment}</span>.
              {data.runs_as && (
                <> Commands run as <span className="font-mono">{data.runs_as}</span>.</>
              )}
            </p>
          </div>
          <span className={`rounded-full px-2 py-0.5 text-caption ${
            problems > 0
              ? "bg-destructive/10 text-destructive"
              : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"}`}>
            {problems > 0
              ? `${problems} thing${problems === 1 ? "" : "s"} to fix`
              : "Nothing needs attention"}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-t border-border px-4 py-2.5">
          {data.maintenance && (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-caption text-amber-700 dark:text-amber-400">
              In maintenance mode — visitors see a holding page
            </span>
          )}
          <span className="flex-1" />
          <Button size="sm" variant="outline" disabled={disabled}
                  onClick={() => onAct(data.maintenance ? "up" : "down")}>
            <Power size={13} />
            {data.maintenance ? "Bring the site back" : "Put into maintenance mode"}
          </Button>
          <Button size="sm" variant="outline" disabled={disabled}
                  onClick={() => onAct("optimize")}>
            {busy === "optimize"
              ? <Loader2 size={13} className="animate-spin" /> : <ArrowUpCircle size={13} />}
            Cache for production
          </Button>
          <Button size="sm" variant="ghost" disabled={disabled}
                  onClick={() => onAct("clear")}>
            <Trash2 size={13} /> Clear caches
          </Button>
        </div>
      </div>

      {/* Offered only when something is actually waiting — a button that would do nothing
          teaches people to press it without reading, which is the last habit anyone should
          have around a command that changes a database. */}
      {pending > 0 && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4">
          <p className="text-sm font-medium text-foreground">
            {pending} database change{pending === 1 ? "" : "s"} waiting to be applied
          </p>
          <p className="mt-1 text-small text-muted-foreground">
            New code often needs the database changed to match it. This applies those
            changes — and it can rename or remove columns, so take a backup first if this
            site holds anything you cannot lose.
          </p>
          <Button size="sm" className="mt-3" disabled={disabled}
                  onClick={() => onAct("migrate")}>
            {busy === "migrate"
              ? <Loader2 size={13} className="animate-spin" /> : <Database size={13} />}
            Apply {pending} change{pending === 1 ? "" : "s"}
          </Button>
        </div>
      )}

      {/* A check we could not run is not a check that passed. */}
      {!data.migrations_known && (
        <p className="rounded-lg border-l-2 border-border bg-muted/40 px-3 py-2 text-small text-muted-foreground">
          We could not read the migration list — usually because the site cannot reach its
          database. Nothing is claimed about it either way.
        </p>
      )}

      <div className="rounded-xl border border-border bg-card">
        {checks.map((c) => (
          <div key={c.label}
               className="flex items-start gap-3 border-t border-border px-4 py-3 first:border-t-0">
            {!c.ok
              ? <XCircle size={15} className="mt-0.5 shrink-0 text-destructive" />
              : c.advisory
                ? <AlertTriangle size={15} className="mt-0.5 shrink-0 text-amber-500" />
                : <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" />}
            <div className="min-w-0">
              <p className="text-sm text-foreground">{c.label}</p>
              <p className="mt-0.5 text-small text-muted-foreground">{c.detail}</p>
            </div>
            {!data.storage_link && c.label.includes("uploads link") && (
              <Button size="sm" variant="outline" className="ml-auto shrink-0"
                      disabled={disabled} onClick={() => onAct("storage_link")}>
                Create it
              </Button>
            )}
            {!data.queue_worker && c.label.includes("queue worker") && (
              <Button size="sm" variant="ghost" className="ml-auto shrink-0"
                      disabled={disabled} onClick={() => onAct("queue_restart")}>
                Restart workers
              </Button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

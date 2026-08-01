import { useState } from "react"
import { useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AlertTriangle, ArrowUpCircle, CheckCircle2, Loader2, Power, Trash2, Users,
} from "lucide-react"
import { getSiteApp, runSiteAppAction, type SiteApp, type SiteDetail } from "@/api/sites"
import { Button, EmptyState } from "@/components/ui"

/**
 * The screen for the application running on this site.
 *
 * Driven by the backend's registry: it answers which application is here and everything its
 * screen shows, so adding Nextcloud later is an entry there plus a branch here, not a new
 * route, a new menu item and a new API.
 *
 * Read fresh on every visit. Plugin versions and administrator accounts change without us —
 * a customer updates from the WordPress admin, or somebody who should not be there creates
 * an account — and a cached answer to "is anything out of date" is worth nothing.
 */
export default function SiteAppPage() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  const qc = useQueryClient()
  const [busy, setBusy] = useState<string | null>(null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["site-app", site.id],
    queryFn: () => getSiteApp(site.id),
  })

  const run = useMutation({
    mutationFn: ({ action, target }: { action: string; target?: string }) =>
      runSiteAppAction(site.id, action, target ?? ""),
    onMutate: ({ action, target }) => {
      setNote(null)
      setBusy(target || action)
    },
    onSuccess: () => {
      setBusy(null)
      setNote({ ok: true, text: "Done." })
      qc.invalidateQueries({ queryKey: ["site-app", site.id] })
    },
    // wp-cli's own message names the actual problem far better than anything written here.
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      setBusy(null)
      setNote({ ok: false, text: e.response?.data?.detail ?? "That did not work." })
    },
  })

  if (isLoading) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <Loader2 size={20} className="animate-spin" />
      </div>
    )
  }

  if (!data?.app) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Nothing to manage here"
        description="This site does not run an application we have tools for."
      />
    )
  }

  if (!data.ok) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title={`${data.label} could not be read`}
        description={data.reason ?? "We could not look at this site."}
      />
    )
  }

  const act = (action: string, target?: string) => run.mutate({ action, target })

  return (
    <div className="space-y-4">
      <Summary data={data} onAct={act} busy={busy} />

      {note && (
        <p
          className={`rounded-lg border-l-2 px-3 py-2 text-small ${
            note.ok
              ? "border-emerald-500 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
              : "border-destructive bg-destructive/5 text-destructive"
          }`}
        >
          {note.text}
        </p>
      )}

      <Extensions
        title="Plugins"
        blurb="Out-of-date plugins are the most common way a WordPress site is broken into."
        rows={data.plugins ?? []}
        onUpdate={(name) => act("update_plugin", name)}
        onToggle={(name, active) =>
          act(active ? "deactivate_plugin" : "activate_plugin", name)}
        busy={busy}
      />

      <Extensions
        title="Themes"
        rows={data.themes ?? []}
        onUpdate={(name) => act("update_theme", name)}
        busy={busy}
      />

      <Admins admins={data.admins ?? []} />
    </div>
  )
}

function Summary({ data, onAct, busy }: {
  data: SiteApp
  onAct: (action: string, target?: string) => void
  busy: string | null
}) {
  const waiting = data.updates_waiting ?? 0
  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="flex flex-wrap items-start justify-between gap-3 px-4 py-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-foreground">
            {data.title || data.label} · {data.label} {data.core_version}
          </p>
          <p className="mt-0.5 text-small text-muted-foreground">
            {data.core_update
              ? `Version ${data.core_update} is available.`
              : data.core_update_known
                ? "WordPress itself is up to date."
                // A check we could not complete is not the same as good news.
                : "We could not check for a WordPress update just now."}
            {data.runs_as && (
              <> Commands run as <span className="font-mono">{data.runs_as}</span>.</>
            )}
          </p>
        </div>
        {data.core_update && (
          <Button size="sm" disabled={busy !== null}
                  onClick={() => onAct("update_core")}>
            {busy === "update_core"
              ? <Loader2 size={14} className="animate-spin" />
              : <ArrowUpCircle size={14} />}
            Update to {data.core_update}
          </Button>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-border px-4 py-2.5">
        <span className={`rounded-full px-2 py-0.5 text-caption ${
          waiting > 0
            ? "bg-amber-500/10 text-amber-700 dark:text-amber-400"
            : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"}`}>
          {waiting > 0 ? `${waiting} update${waiting === 1 ? "" : "s"} waiting` : "Everything up to date"}
        </span>

        {data.maintenance && (
          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-caption text-amber-700 dark:text-amber-400">
            Maintenance mode is on — visitors see a holding page
          </span>
        )}
        {data.debug && (
          <span className="rounded-full bg-destructive/10 px-2 py-0.5 text-caption text-destructive">
            Debug mode is on — errors may be shown to visitors
          </span>
        )}

        <span className="flex-1" />

        <Button size="sm" variant="outline" disabled={busy !== null}
                onClick={() => onAct(data.maintenance ? "maintenance_off" : "maintenance_on")}>
          <Power size={13} />
          {data.maintenance ? "Turn off maintenance mode" : "Turn on maintenance mode"}
        </Button>
        <Button size="sm" variant="ghost" disabled={busy !== null}
                onClick={() => onAct("flush_cache")}>
          <Trash2 size={13} /> Clear cache
        </Button>
      </div>
    </div>
  )
}

interface Row {
  name: string
  title?: string
  status: string
  version: string
  update_available: boolean
  update_version: string
}

function Extensions({ title, blurb, rows, onUpdate, onToggle, busy }: {
  title: string
  blurb?: string
  rows: Row[]
  onUpdate: (name: string) => void
  onToggle?: (name: string, active: boolean) => void
  busy: string | null
}) {
  if (!rows.length) return null
  const stale = rows.filter((r) => r.update_available).length

  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <p className="text-sm font-medium text-foreground">
          {title} <span className="text-muted-foreground">({rows.length})</span>
          {stale > 0 && (
            <span className="ml-2 rounded-full bg-amber-500/10 px-2 py-0.5 text-caption text-amber-700 dark:text-amber-400">
              {stale} out of date
            </span>
          )}
        </p>
        {blurb && <p className="mt-0.5 text-caption text-muted-foreground">{blurb}</p>}
      </div>

      <table className="w-full text-small">
        <tbody>
          {/* Out-of-date first: it is the only reason most people open this screen. */}
          {[...rows].sort((a, b) => Number(b.update_available) - Number(a.update_available))
            .map((r) => {
              const active = r.status === "active"
              return (
                <tr key={r.name} className="border-t border-border first:border-t-0">
                  <td className="px-4 py-2.5">
                    <span className="text-foreground">{r.title || r.name}</span>
                    <span className="ml-2 text-caption text-muted-foreground">
                      {active ? "active" : r.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-muted-foreground">
                    {r.update_available
                      ? <span className="text-amber-700 dark:text-amber-400">
                          {r.version} → {r.update_version}
                        </span>
                      : r.version}
                  </td>
                  <td className="w-px whitespace-nowrap px-4 py-2.5 text-right">
                    {r.update_available && (
                      <Button size="sm" variant="outline" disabled={busy !== null}
                              onClick={() => onUpdate(r.name)}>
                        {busy === r.name
                          ? <Loader2 size={13} className="animate-spin" />
                          : <ArrowUpCircle size={13} />}
                        Update
                      </Button>
                    )}
                    {onToggle && !r.update_available && (
                      <button
                        onClick={() => onToggle(r.name, active)}
                        disabled={busy !== null}
                        className="text-caption text-muted-foreground hover:text-foreground disabled:opacity-50"
                      >
                        {active ? "Deactivate" : "Activate"}
                      </button>
                    )}
                  </td>
                </tr>
              )
            })}
        </tbody>
      </table>
    </div>
  )
}

function Admins({ admins }: { admins: { id: string; login: string; email: string }[] }) {
  if (!admins.length) return null
  // An administrator can do anything to the site, so this list IS the site's access control
  // — and on a site nobody audits, it is where a break-in shows up first as accounts that
  // should not be there. Worth stating plainly rather than leaving as a bare list.
  const many = admins.length > 5

  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Users size={14} className="text-muted-foreground" />
        <p className="text-sm font-medium text-foreground">
          Administrators <span className="text-muted-foreground">({admins.length})</span>
        </p>
        {many ? (
          <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-caption text-amber-700 dark:text-amber-400">
            More than most sites need — check you know every one
          </span>
        ) : (
          <CheckCircle2 size={14} className="text-emerald-600 dark:text-emerald-400" />
        )}
      </div>
      <div className="max-h-72 overflow-y-auto">
        {admins.map((a) => (
          <div key={a.id || a.login}
               className="flex items-baseline justify-between gap-4 border-t border-border px-4 py-2 first:border-t-0">
            <span className="font-mono text-small text-foreground">{a.login}</span>
            <span className="truncate text-small text-muted-foreground">{a.email}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

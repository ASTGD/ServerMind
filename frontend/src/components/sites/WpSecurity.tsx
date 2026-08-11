import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Bug, Clock, Loader2, ShieldBan } from "lucide-react"

import { getWpSecurity, setWpDebug, setWpTimer, setWpXmlrpc } from "@/api/sites"
import { Button } from "@/components/ui"

/**
 * The two WordPress security switches.
 *
 * Both are things a WordPress owner is told to do and never does, because both mean editing
 * a file they are frightened of. The screen's job is to say what each one costs — turning
 * debugging on is temporary and turning XML-RPC off breaks named, real tools — so nobody
 * flips one and finds out later.
 */
export default function WpSecurity({ siteId }: { siteId: string }) {
  const qc = useQueryClient()
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const q = useQuery({ queryKey: ["wp-security", siteId], queryFn: () => getWpSecurity(siteId) })

  const run = (what: string, fn: () => Promise<{ message: string }>) => {
    setBusy(what); setNote(null)
    fn()
      .then(async (r) => {
        await qc.invalidateQueries({ queryKey: ["wp-security", siteId] })
        setNote({ ok: true, text: r.message })
      })
      .catch((e: { response?: { data?: { detail?: string } } }) =>
        setNote({ ok: false, text: e.response?.data?.detail ?? "That could not be changed." }))
      .finally(() => setBusy(null))
  }

  const d = q.data
  if (q.isLoading) {
    return (
      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2 text-small text-muted-foreground">
          <Loader2 size={14} className="animate-spin" /> Reading this site's settings…
        </div>
      </div>
    )
  }
  if (!d?.ok) return null

  return (
    <div className="space-y-4">
      {/* Stated before either switch, because it is true right now and nobody can see it
          from the site itself until a visitor happens to trigger an error. */}
      {d.leaking_errors && (
        <div className="rounded-xl border-l-2 border-destructive bg-destructive/10 px-4 py-3">
          <p className="flex items-center gap-1.5 text-small font-semibold text-destructive">
            <AlertTriangle size={14} /> This site is showing its errors to visitors
          </p>
          <p className="mt-1 text-caption text-foreground">
            Debug mode is on and error display was never turned off, so a PHP error prints
            file paths and plugin internals straight into the page for whoever is looking.
            Turning debugging off below fixes it, and turning it on from here never causes
            it.
          </p>
        </div>
      )}

      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2">
          <Bug size={15} className="text-muted-foreground" />
          <h3 className="text-h3 text-foreground">Debug logging</h3>
        </div>
        <p className="mt-1 text-small text-muted-foreground">
          Records PHP errors and warnings so a broken plugin can be found. Errors are written
          to a file <span className="font-medium text-foreground">beside</span> the site, not
          inside it — nobody can download the log, and visitors never see an error page.
        </p>

        {d.can_debug === false ? (
          <p className="mt-3 rounded-lg border-l-2 border-amber-500 bg-amber-500/5 px-3 py-2
                        text-small text-foreground">{d.cannot_debug_reason}</p>
        ) : (
          <>
            {d.log_path && (
              <p className="mt-2 text-caption text-muted-foreground">
                Log: <span className="font-mono">{d.log_path}</span>
              </p>
            )}
            <div className="mt-3 flex items-center gap-3">
              <Button size="sm" variant={d.debug ? "outline" : "primary"}
                      disabled={!!busy}
                      onClick={() => run("debug", () => setWpDebug(siteId, !d.debug))}>
                {busy === "debug" && <Loader2 size={14} className="animate-spin" />}
                {d.debug ? "Turn debugging off" : "Turn debugging on"}
              </Button>
              <span className="text-caption text-muted-foreground">
                {d.debug ? "Currently ON" : "Currently off"}
              </span>
            </div>
            {d.debug && (
              <p className="mt-2 text-caption text-muted-foreground">
                Leave it on only while you need it — a debug log on a busy site grows quickly.
              </p>
            )}
          </>
        )}
      </div>

      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2">
          <ShieldBan size={15} className="text-muted-foreground" />
          <h3 className="text-h3 text-foreground">XML-RPC</h3>
        </div>
        <p className="mt-1 text-small text-muted-foreground">
          An old WordPress interface that attackers use to try thousands of passwords in one
          request, and to flood sites with pingbacks. Blocking it here refuses the request at
          the web server, before WordPress starts — so the attack never costs you anything.
        </p>
        <p className="mt-2 text-caption text-muted-foreground">
          Block it unless you use{" "}
          <span className="text-foreground">{(d.xmlrpc_breaks ?? []).join(", ")}</span> —
          those need it.
        </p>
        <div className="mt-3 flex items-center gap-3">
          <Button size="sm" variant={d.xmlrpc_blocked ? "outline" : "primary"}
                  disabled={!!busy}
                  onClick={() => run("xmlrpc", () => setWpXmlrpc(siteId, !d.xmlrpc_blocked))}>
            {busy === "xmlrpc" && <Loader2 size={14} className="animate-spin" />}
            {d.xmlrpc_blocked ? "Allow XML-RPC again" : "Block XML-RPC"}
          </Button>
          <span className="text-caption text-muted-foreground">
            {d.xmlrpc_blocked ? "Currently blocked" : "Currently open"}
          </span>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-2">
          <Clock size={15} className="text-muted-foreground" />
          <h3 className="text-h3 text-foreground">Scheduled work</h3>
        </div>
        <p className="mt-1 text-small text-muted-foreground">
          By default WordPress does its scheduled work — publishing posts, sending mail,
          running backups — while somebody is loading a page. On a quiet site that means it
          happens late or not at all, and on a busy one every visitor waits for it.
        </p>
        <p className="mt-2 text-caption text-muted-foreground">
          {d.timer_disabled
            ? "A scheduled job is doing this instead, so pages are not slowed by it."
            : "Add the scheduled job on this site's Scheduled jobs screen first — then this "
              + "can be switched off. It is refused until then, because switching it off "
              + "with nothing else running would stop the work completely and say nothing."}
        </p>
        <div className="mt-3 flex items-center gap-3">
          <Button size="sm" variant={d.timer_disabled ? "outline" : "primary"}
                  disabled={!!busy}
                  onClick={() => run("timer", () => setWpTimer(siteId, !d.timer_disabled))}>
            {busy === "timer" && <Loader2 size={14} className="animate-spin" />}
            {d.timer_disabled
              ? "Let WordPress run it during visits again"
              : "Stop running it during visits"}
          </Button>
          <span className="text-caption text-muted-foreground">
            {d.timer_disabled ? "Handled by a scheduled job" : "Runs during visits"}
          </span>
        </div>
      </div>

      {note && (
        <p className={`rounded-lg border-l-2 px-3 py-2 text-small ${
          note.ok
            ? "border-emerald-500 bg-emerald-500/5 text-foreground"
            : "border-destructive bg-destructive/5 text-destructive"}`}>
          {note.text}
        </p>
      )}
    </div>
  )
}

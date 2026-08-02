import { useState } from "react"
import { Link, useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, CheckCircle2, Code2, Loader2 } from "lucide-react"
import { getSitePhp, switchSitePhp, type SiteDetail } from "@/api/sites"
import { Button, EmptyState } from "@/components/ui"

/**
 * Which PHP version serves this site.
 *
 * The server's PHP screen lists every site on the machine; this one is about the site in
 * front of you, and it cannot reach a neighbour — the configuration file to rewrite is
 * worked out on the server, from this site, and is never sent from here.
 *
 * The risk is real and worth stating on the page: an application written for an older PHP
 * throws a fatal error on a newer one and the site goes white the moment the config
 * reloads. So the change keeps a copy, checks the site still serves real content, and puts
 * the old file back if it does not.
 */
export default function SitePhp() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  const qc = useQueryClient()
  const [note, setNote] = useState("")
  const [error, setError] = useState("")

  const { data, isLoading } = useQuery({
    queryKey: ["site-php", site.id],
    queryFn: () => getSitePhp(site.id),
  })

  const swap = useMutation({
    mutationFn: (version: string) => switchSitePhp(site.id, version),
    onSuccess: (r) => {
      setNote(r.message); setError("")
      qc.invalidateQueries({ queryKey: ["site-php", site.id] })
      qc.invalidateQueries({ queryKey: ["site-app", site.id] })
    },
    onError: (e) => {
      setNote("")
      setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
               || "The version could not be changed.")
    },
  })

  if (isLoading) {
    return <div className="flex justify-center py-16 text-muted-foreground">
      <Loader2 size={20} className="animate-spin" /></div>
  }

  if (!data?.ok) {
    return (
      <div className="space-y-3">
        <EmptyState
          icon={Code2}
          title="We cannot tell which configuration serves this site"
          description={data?.reason ?? "This site's PHP version could not be read."}
        />
        <p className="px-1 text-caption text-muted-foreground">
          <Link to={`/servers/${site.server.id}/php`}
            className="underline hover:text-foreground">
            Every site's PHP version on this server →
          </Link>
        </p>
      </div>
    )
  }

  const current = data.version
  const others = data.versions.filter((v) => v !== current)
  const busy = swap.isPending

  return (
    <div className="space-y-3">
      {error && (
        <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-foreground">
          {error}
        </p>
      )}
      {note && (
        <p className="flex items-start gap-2 rounded-lg border-l-2 border-emerald-500 bg-emerald-500/5 px-3 py-2 text-small text-foreground">
          <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
          {note}
        </p>
      )}

      <div className="rounded-xl border border-border bg-card p-4">
        <p className="text-sm text-muted-foreground">This site runs on</p>
        <p className="mt-0.5 text-h2 font-medium text-foreground">
          PHP {current ?? "unknown"}
        </p>
        <p className="mt-1 font-mono text-caption text-muted-foreground">{data.config}</p>
      </div>

      {others.length === 0 ? (
        <p className="rounded-xl border border-border bg-card px-4 py-3 text-small text-muted-foreground">
          This is the only PHP version installed on this server. Add another from the
          server's{" "}
          <Link to={`/servers/${site.server.id}/php`} className="underline">PHP screen</Link>,
          then come back and choose it here.
        </p>
      ) : (
        <div className="rounded-xl border border-border bg-card">
          <p className="border-b border-border px-4 py-3 text-sm font-medium text-foreground">
            Change it to
          </p>
          {others.map((v) => (
            <div key={v}
              className="flex items-center justify-between gap-3 border-t border-border px-4 py-2.5 first:border-t-0">
              <div>
                <span className="font-mono text-sm text-foreground">PHP {v}</span>
                {data.running && !data.running.includes(v) && (
                  <span className="ml-2 text-caption text-amber-700 dark:text-amber-300">
                    installed but not running
                  </span>
                )}
              </div>
              <Button size="sm" variant="outline" disabled={busy}
                onClick={() => {
                  if (confirm(
                    `Switch ${site.domain} to PHP ${v}?\n\n`
                    + `If the site stops working, the old version is put straight back.`,
                  )) swap.mutate(v)
                }}>
                {busy ? <Loader2 size={13} className="animate-spin" /> : null}
                Use PHP {v}
              </Button>
            </div>
          ))}
        </div>
      )}

      {/* Said plainly, before it is done rather than after. */}
      <p className="flex items-start gap-2 px-1 text-caption text-muted-foreground">
        <AlertTriangle size={12} className="mt-0.5 shrink-0" />
        An application written for an older PHP can stop working on a newer one. The old
        configuration is kept, the site is checked afterwards, and if it stops serving
        properly the change is undone straight away.
      </p>
    </div>
  )
}

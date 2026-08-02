import { useState } from "react"
import { useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Loader2, Trash2 } from "lucide-react"
import {
  addSiteRedirect, listSiteRedirects, removeSiteRedirect,
  type SiteDetail, type SiteRedirectRule,
} from "@/api/sites"
import { Button, EmptyState, Input, Label } from "@/components/ui"
import { cn } from "@/lib/utils"

/**
 * Send one address on this site to another.
 *
 * A copy of Ploi's Redirects screen: two fields and a type, the form always on the page,
 * the list underneath only once there is something in it. The type's values are nginx's own
 * rewrite flags, which is what they become on the way down.
 *
 * The dot on each row is not decoration. A redirect is recorded here and written into the
 * web server's configuration, and those are two different moments — a row that never
 * reached the server is shown as not live rather than as working.
 */
export default function SiteRedirects() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  const qc = useQueryClient()

  const [from, setFrom] = useState("")
  const [to, setTo] = useState("")
  const [kind, setKind] = useState("redirect")
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState<SiteRedirectRule | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["site-redirects", site.id],
    queryFn: () => listSiteRedirects(site.id),
  })

  const fail = (e: { response?: { data?: { detail?: string } } }) =>
    setError(e.response?.data?.detail ?? "That did not work.")
  const refresh = () => qc.invalidateQueries({ queryKey: ["site-redirects", site.id] })

  const add = useMutation({
    mutationFn: () => addSiteRedirect(site.id, {
      redirect_from: from, redirect_to: to, redirect_type: kind,
    }),
    onSuccess: () => { setFrom(""); setTo(""); setError(null); refresh() },
    // The server's message names the actual problem — a path that is not a path, a
    // duplicate, a configuration the web server refused — so it is shown, not replaced.
    onError: (e: { response?: { data?: { detail?: string } } }) => { fail(e); refresh() },
  })

  const drop = useMutation({
    mutationFn: (r: SiteRedirectRule) => removeSiteRedirect(site.id, r.id),
    onSuccess: () => { setConfirming(null); setError(null); refresh() },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      setConfirming(null); fail(e); refresh()
    },
  })

  const redirects = data?.redirects ?? []

  if (data && !data.ok) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="Redirects are not available for this site"
        description={data.reason ?? "This site is not managed over SSH."}
      />
    )
  }

  return (
    <div className="space-y-4">
      <form onSubmit={(e) => { e.preventDefault(); setError(null); add.mutate() }}>
        <section className="grid overflow-hidden rounded-xl border border-border bg-card sm:grid-cols-[minmax(0,300px)_minmax(0,1fr)]">
          <div className="p-5 sm:pr-6">
            <h3 className="text-sm font-medium text-foreground">New redirect</h3>
            <p className="mt-1 text-caption text-muted-foreground">
              You can create redirects here to have specific paths redirected to a new path.
            </p>
            <p className="mt-3 text-caption text-muted-foreground">
              To redirect this whole domain to another domain, use these variables:
            </p>
            {/* Anchored with ^ on purpose. The unanchored form is what Ploi prints, and
                against real nginx it also redirects /.well-known/… — which is the path
                Let's Encrypt uses to prove you own the domain, so certificate renewal
                quietly starts failing weeks later. Checked by requesting both. */}
            <p className="mt-1.5 text-caption text-muted-foreground">
              From: <code className="rounded bg-muted px-1 py-0.5 font-mono text-foreground">
                {String.raw`^/(?!\.well-known/)(.*)`}
              </code>
            </p>
            <p className="mt-1 text-caption text-muted-foreground">
              To: <code className="rounded bg-muted px-1 py-0.5 font-mono text-foreground">
                https://example.com/$1
              </code>
            </p>
            <p className="mt-2 text-caption text-muted-foreground">
              The <code className="font-mono">^</code> matters — without it the rule also
              catches the address certificates are renewed through.
            </p>
          </div>

          <div className="space-y-3 p-5 sm:pl-0">
            <div>
              <Label htmlFor="redirect-from">Redirect from</Label>
              <Input id="redirect-from" value={from} required className="font-mono"
                     onChange={(e) => setFrom(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="redirect-to">Redirect to</Label>
              <Input id="redirect-to" value={to} required className="font-mono"
                     onChange={(e) => setTo(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="redirect-type">Type</Label>
              <select
                id="redirect-type"
                value={kind}
                onChange={(e) => setKind(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground"
              >
                <option value="redirect">Temporary (302)</option>
                <option value="permanent">Permanent (301)</option>
              </select>
            </div>

            {error && (
              <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-destructive">
                {error}
              </p>
            )}
          </div>

          <footer className="col-span-full flex justify-end border-t border-border bg-muted/30 px-5 py-3">
            <Button type="submit" size="sm"
                    disabled={add.isPending || !from.trim() || !to.trim()}>
              {add.isPending
                ? <><Loader2 size={13} className="animate-spin" /> Adding…</>
                : "Add redirect"}
            </Button>
          </footer>
        </section>
      </form>

      {isLoading && (
        <div className="h-16 animate-pulse rounded-xl border border-border bg-card" />
      )}

      {/* Only once there is something to list — an empty table under the form would be a
          box saying nothing, which is why Ploi does not draw one either. */}
      {redirects.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-border bg-card">
          {redirects.map((r) => (
            <div key={r.id}
                 className="flex items-center gap-3 border-t border-border px-4 py-3 first:border-t-0">
              <span
                title={r.is_applied
                  ? "Live on the server"
                  : "Saved here, but not in the web server's configuration"}
                className={cn("size-2 shrink-0 rounded-full",
                  r.is_applied ? "bg-emerald-500" : "bg-muted-foreground/40")}
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-foreground">
                  Redirect <span className="font-mono">{r.from}</span> to{" "}
                  <span className="font-mono">{r.to}</span>
                </p>
                <p className="text-caption text-muted-foreground">
                  {r.type_label}
                  {!r.is_applied && " · not live on the server"}
                </p>
              </div>
              <Button variant="danger" size="sm" aria-label="Delete redirect"
                      disabled={drop.isPending}
                      onClick={() => setConfirming(r)}>
                <Trash2 size={13} />
              </Button>
            </div>
          ))}
        </div>
      )}

      {confirming && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
             onClick={() => setConfirming(null)}>
          <div className="w-full max-w-sm rounded-xl border border-border bg-card p-5"
               onClick={(e) => e.stopPropagation()}>
            <p className="text-sm font-medium text-foreground">Are you sure?</p>
            <p className="mt-1 text-small text-muted-foreground">
              Are you sure you want to delete this redirect?
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <Button variant="outline" size="sm" onClick={() => setConfirming(null)}>
                Cancel
              </Button>
              <Button variant="danger" size="sm" disabled={drop.isPending}
                      onClick={() => drop.mutate(confirming)}>
                {drop.isPending ? "Deleting…" : "Delete"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

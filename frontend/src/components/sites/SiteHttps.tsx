import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Copy, Loader2, ShieldCheck, ShieldAlert, Lock } from "lucide-react"
import { getSslReadiness, turnOnSsl } from "@/api/sites"
import { Button } from "@/components/ui"

/**
 * HTTPS for one site.
 *
 * The whole difficulty here is that the one requirement is outside our control: a
 * certificate can only be issued if the domain ALREADY points at this server, because the
 * authority proves ownership by reaching it through that name. A domain bought an hour ago
 * does not, and that is normal — so this checks first and shows the record to create,
 * rather than letting someone press a button that spends one of the five attempts Let's
 * Encrypt allows per domain per week.
 */
export default function SiteHttps({ siteId, domain, hasSsl }: {
  siteId: string
  domain: string
  hasSsl: boolean
}) {
  const qc = useQueryClient()
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [copied, setCopied] = useState(false)
  // ZeroSSL is behind a fold: its only reason to exist is that Let's Encrypt has refused,
  // so putting it beside the free button would make a rare fallback look like a decision
  // everybody has to make.
  const [eab, setEab] = useState({ kid: "", key: "" })

  const { data: dns, isLoading } = useQuery({
    queryKey: ["ssl-readiness", siteId],
    queryFn: () => getSslReadiness(siteId),
    enabled: !hasSsl,
    staleTime: 30_000,
  })

  const turnOn = useMutation({
    mutationFn: (opts: Parameters<typeof turnOnSsl>[1]) => turnOnSsl(siteId, opts),
    onSuccess: (r) => {
      // Name what it covers. "A certificate is coming" is not the same promise as "these
      // three addresses will be secure", and only the second one can be checked later.
      const left = r.excluded.map((e) => e.name).join(", ")
      setNote({
        ok: true,
        text: `Getting a certificate for ${r.covers.join(", ")} now. It takes about a minute.`
          + (left ? ` ${left} was left out — it does not point here yet.` : ""),
      })
      qc.invalidateQueries({ queryKey: ["site", siteId] })
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setNote({ ok: false, text: e.response?.data?.detail ?? "HTTPS could not be turned on." }),
  })

  if (hasSsl) {
    return (
      <div className="flex items-start gap-3 rounded-xl border border-border bg-card p-4">
        <ShieldCheck size={16} className="mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
        <div>
          <p className="text-sm font-medium text-foreground">HTTPS is on</p>
          <p className="mt-0.5 text-small text-muted-foreground">
            Visitors on http are sent to https automatically. The certificate renews itself,
            and ServerAlly warns you well before it expires.
          </p>
        </div>
      </div>
    )
  }

  return (
    <section className="rounded-xl border border-border bg-card">
      <header className="flex items-start gap-3 border-b border-border px-4 py-3">
        <Lock size={15} className="mt-0.5 shrink-0 text-muted-foreground" />
        <div>
          <h3 className="text-sm font-medium text-foreground">HTTPS is not on yet</h3>
          <p className="text-caption text-muted-foreground">
            Until it is, browsers show visitors a “Not secure” warning.
          </p>
        </div>
      </header>

      <div className="space-y-3 p-4">
        {note && (
          <p className={`rounded-lg border-l-2 px-3 py-2 text-small ${
            note.ok
              ? "border-emerald-500 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
              : "border-amber-500 bg-amber-500/5 text-amber-800 dark:text-amber-300"
          }`}>
            {note.text}
          </p>
        )}

        {isLoading ? (
          <p className="flex items-center gap-2 text-small text-muted-foreground">
            <Loader2 size={13} className="animate-spin" /> Checking where {domain} points…
          </p>
        ) : dns?.ready ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={() => { setNote(null); turnOn.mutate({}) }} disabled={turnOn.isPending}>
                {turnOn.isPending ? "Starting…" : "Turn on HTTPS"}
              </Button>
              <p className="text-caption text-muted-foreground">
                {domain} points here, so this will work. Free, and it renews itself.
              </p>
            </div>

            {/* One certificate covers every name the site answers to. Said before the
                button, because a certificate that misses `www` gives half the visitors a
                security warning on a site whose owner has been told HTTPS is on — and they
                would only find that out from a visitor. */}
            {(dns.covers?.length ?? 0) > 1 && (
              <p className="text-caption text-muted-foreground">
                One certificate will cover{" "}
                {dns.covers.map((n, i) => (
                  <span key={n}>
                    {i > 0 && ", "}
                    <span className="font-mono text-foreground">{n}</span>
                  </span>
                ))}.
              </p>
            )}

            <details className="text-caption">
              <summary className="cursor-pointer text-muted-foreground">
                Use ZeroSSL instead
              </summary>
              <div className="mt-2 space-y-2 rounded-lg border border-border p-3">
                <p className="text-caption text-muted-foreground">
                  Only worth it if Let’s Encrypt has refused because this domain asked for
                  too many certificates this week — ZeroSSL has its own separate allowance.
                  Both are free. You need a key id and an HMAC key from the Developer page of
                  your ZeroSSL account.
                </p>
                <div className="grid gap-2 sm:grid-cols-2">
                  <input value={eab.kid} placeholder="Key id"
                         onChange={(e) => setEab({ ...eab, kid: e.target.value })}
                         className="rounded-lg border border-border bg-background px-2.5 py-1.5
                                    font-mono text-caption text-foreground" />
                  <input value={eab.key} placeholder="HMAC key"
                         onChange={(e) => setEab({ ...eab, key: e.target.value })}
                         className="rounded-lg border border-border bg-background px-2.5 py-1.5
                                    font-mono text-caption text-foreground" />
                </div>
                <Button size="sm" variant="outline"
                        disabled={turnOn.isPending || !eab.kid.trim() || !eab.key.trim()}
                        onClick={() => {
                          setNote(null)
                          turnOn.mutate({ authority: "zerossl", eab_kid: eab.kid,
                                          eab_key: eab.key })
                        }}>
                  Get a certificate from ZeroSSL
                </Button>
              </div>
            </details>

            {(dns.excluded?.length ?? 0) > 0 && (
              // Never dropped quietly: an owner who believes an alias is covered when it was
              // left out is back where they started.
              <div className="rounded-lg border-l-2 border-amber-500 bg-amber-500/5 px-3 py-2">
                <p className="text-caption text-amber-800 dark:text-amber-300">
                  Left out, because {dns.excluded.length === 1 ? "it does" : "they do"} not
                  point here yet:{" "}
                  {dns.excluded.map((e) => e.name).join(", ")}. Point{" "}
                  {dns.excluded.length === 1 ? "it" : "them"} at this server and turn HTTPS on
                  again to include {dns.excluded.length === 1 ? "it" : "them"}.
                </p>
              </div>
            )}
          </div>
        ) : (
          /* Not a failure — the normal state of a domain nobody has pointed yet. So it
             shows the exact record to create rather than an error. */
          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <ShieldAlert size={15} className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
              <p className="text-small text-muted-foreground">{dns?.message}</p>
            </div>

            {dns?.record && (
              <div className="rounded-lg border border-border bg-muted/40 p-3">
                <p className="text-caption text-muted-foreground">Add this DNS record</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-5 gap-y-1 font-mono text-sm text-foreground">
                  <span><span className="text-muted-foreground">type </span>{dns.record.type}</span>
                  <span><span className="text-muted-foreground">name </span>{dns.record.name}</span>
                  <span><span className="text-muted-foreground">value </span>{dns.record.value}</span>
                  <button
                    type="button"
                    onClick={() => {
                      navigator.clipboard.writeText(dns.record.value)
                      setCopied(true); setTimeout(() => setCopied(false), 1500)
                    }}
                    className="inline-flex items-center gap-1 text-caption text-muted-foreground hover:text-foreground"
                  >
                    <Copy size={11} /> {copied ? "copied" : "copy address"}
                  </button>
                </div>
              </div>
            )}

            <div className="flex flex-wrap items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => qc.invalidateQueries({ queryKey: ["ssl-readiness", siteId] })}
              >
                Check again
              </Button>
              {/* Ploi's "skip DNS verification". Offered only where our check can be wrong:
                  the domain DOES resolve, just not to this server — which is exactly what a
                  Cloudflare proxy or a CDN looks like, and those certificates issue fine. A
                  domain that resolves nowhere cannot be validated by anyone, so there is
                  nothing to override and the button would only spend an attempt. */}
              {dns?.reason === "points somewhere else" && (
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={turnOn.isPending}
                  onClick={() => { setNote(null); turnOn.mutate({ force: true }) }}
                >
                  Request anyway
                </Button>
              )}
            </div>
            {dns?.reason === "points somewhere else" && (
              <p className="text-caption text-muted-foreground">
                “Request anyway” skips this check. Use it if the site sits behind Cloudflare
                or a CDN — the request still reaches this server, so the certificate works.
                If it is wrong, it spends one of the five attempts allowed each week.
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  )
}

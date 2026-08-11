import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { FileKey, Loader2, ShieldCheck } from "lucide-react"
import { checkCertificate, installCertificate, type CertFacts } from "@/api/sites"
import { Button } from "@/components/ui"

/**
 * Install a certificate the customer already has.
 *
 * Let's Encrypt covers most sites; the ones it does not are exactly the ones somebody has
 * already paid for — a wildcard from a registrar, a certificate a client insists on, or a
 * Cloudflare origin certificate.
 *
 * The shape of the screen is the safety. **Check first, install second**, because everything
 * that can go wrong here is decidable from the pasted text alone: a key that does not belong
 * to the certificate stops the web server from starting, and a certificate for the wrong
 * domain shows a warning to every visitor. Neither should be discovered on a live site.
 *
 * Behind a `<details>` rather than on the page, because it is the exception — most people
 * want the free button above it, and putting two ways to do one job side by side makes the
 * simple one look like a choice that needs thinking about.
 */
export default function InstallCertificate({ siteId, domain }: {
  siteId: string
  domain: string
}) {
  const qc = useQueryClient()
  const [cert, setCert] = useState("")
  const [key, setKey] = useState("")
  const [facts, setFacts] = useState<CertFacts | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)

  const fail = (e: { response?: { data?: { detail?: string } } }) => {
    setFacts(null)
    setError(e.response?.data?.detail ?? "That certificate could not be read.")
  }

  const look = useMutation({
    mutationFn: () => checkCertificate(siteId, cert, key),
    onSuccess: (f) => { setFacts(f); setError(null) },
    onError: fail,
  })

  const install = useMutation({
    mutationFn: () => installCertificate(siteId, cert, key),
    onSuccess: (f) => {
      setError(null)
      setDone(f.message ?? "The certificate is installed.")
      // Cleared the moment it is on the server. We do not keep it and neither should the
      // screen — this box held a private key.
      setCert(""); setKey(""); setFacts(null)
      qc.invalidateQueries({ queryKey: ["site", siteId] })
      qc.invalidateQueries({ queryKey: ["ssl-readiness", siteId] })
    },
    onError: fail,
  })

  // Editing either box invalidates what was checked — a summary that no longer describes
  // what is about to be installed is worse than none, because it carries the same authority.
  const edit = (set: (v: string) => void) => (v: string) => {
    set(v); setFacts(null); setError(null); setDone(null)
  }

  const busy = look.isPending || install.isPending

  return (
    <details className="rounded-xl border border-border bg-card">
      <summary className="flex cursor-pointer items-center gap-2 px-4 py-3 text-sm
                          font-medium text-foreground">
        <FileKey size={15} className="text-muted-foreground" />
        I already have a certificate
      </summary>

      <div className="space-y-3 border-t border-border p-4">
        <p className="text-small text-muted-foreground">
          For a wildcard certificate, one bought from a supplier, or a Cloudflare origin
          certificate. Paste both parts exactly as you received them.
        </p>
        <p className="text-caption text-muted-foreground">
          A certificate installed this way <strong>does not renew itself</strong> — unlike the
          free one above. ServerAlly will warn you before it expires, but replacing it is
          yours to do.
        </p>

        <label className="block">
          <span className="text-caption text-muted-foreground">
            Certificate (and the chain, if you were given one)
          </span>
          <textarea
            value={cert}
            onChange={(e) => edit(setCert)(e.target.value)}
            rows={5}
            spellCheck={false}
            placeholder="-----BEGIN CERTIFICATE-----"
            className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2
                       font-mono text-caption text-foreground"
          />
        </label>

        <label className="block">
          <span className="text-caption text-muted-foreground">Private key</span>
          <textarea
            value={key}
            onChange={(e) => edit(setKey)(e.target.value)}
            rows={5}
            spellCheck={false}
            placeholder="-----BEGIN PRIVATE KEY-----"
            className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2
                       font-mono text-caption text-foreground"
          />
        </label>

        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" disabled={busy || !cert.trim() || !key.trim()}
                  onClick={() => look.mutate()}>
            {look.isPending && <Loader2 size={13} className="animate-spin" />}
            Check it
          </Button>
          {facts && (
            <Button size="sm" disabled={busy} onClick={() => install.mutate()}>
              {install.isPending && <Loader2 size={13} className="animate-spin" />}
              Install it
            </Button>
          )}
        </div>

        {facts && (
          <div className="rounded-lg border-l-2 border-emerald-500 bg-emerald-500/5 px-3 py-2">
            <p className="flex items-center gap-1.5 text-small text-foreground">
              <ShieldCheck size={13} className="text-emerald-600 dark:text-emerald-400" />
              Valid for <span className="font-mono">{facts.names.join(", ")}</span>, covering{" "}
              {domain}.
            </p>
            <p className="mt-0.5 text-caption text-muted-foreground">
              Issued by {facts.issuer} · expires {facts.expires} ({facts.days_left} days)
              {facts.chain_length > 1 && ` · ${facts.chain_length} certificates in the chain`}
            </p>
            {facts.chain_length === 1 && !facts.self_signed && (
              // Said, not refused: an origin certificate legitimately has no chain, and a
              // genuinely missing intermediate fails on some devices and not others.
              <p className="mt-1 text-caption text-amber-700 dark:text-amber-400">
                No chain was included. If your supplier gave you an intermediate certificate,
                paste it below this one — without it some browsers will reject the site.
              </p>
            )}
          </div>
        )}

        {done && (
          <p className="rounded-lg border-l-2 border-emerald-500 bg-emerald-500/5 px-3 py-2
                        text-small text-emerald-700 dark:text-emerald-400">{done}</p>
        )}
        {error && (
          <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                        text-small text-destructive">{error}</p>
        )}
      </div>
    </details>
  )
}

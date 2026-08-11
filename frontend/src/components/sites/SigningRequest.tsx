import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Copy, FileSignature, Loader2 } from "lucide-react"
import { createSigningRequest } from "@/api/sites"
import { Button } from "@/components/ui"

/**
 * Create a certificate signing request — Ploi's "create signing request".
 *
 * The half that comes before "install a certificate you already have": a commercial
 * authority will not issue one until you send them a CSR.
 *
 * **The private key is made on the server and stays there.** So the only thing this screen
 * ever shows is the request itself, which is public by design — and when the certificate
 * comes back, the install form finds the key already waiting and nobody has to handle it.
 */
export default function SigningRequest({ siteId, domain }: {
  siteId: string
  domain: string
}) {
  const [fields, setFields] = useState({
    country: "", state: "", locality: "", organisation: "", unit: "",
  })
  const [csr, setCsr] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const make = useMutation({
    mutationFn: () => createSigningRequest(siteId, fields),
    onSuccess: (r) => { setCsr(r.csr); setError(null) },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      setCsr(null)
      setError(e.response?.data?.detail ?? "The request could not be created.")
    },
  })

  const set = (k: keyof typeof fields) => (v: string) =>
    setFields({ ...fields, [k]: v })

  const Field = ({ k, label, placeholder }: {
    k: keyof typeof fields; label: string; placeholder: string
  }) => (
    <label className="block">
      <span className="text-caption text-muted-foreground">{label}</span>
      <input value={fields[k]} onChange={(e) => set(k)(e.target.value)}
             placeholder={placeholder}
             className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2
                        text-caption text-foreground" />
    </label>
  )

  return (
    <details className="rounded-xl border border-border bg-card">
      <summary className="flex cursor-pointer items-center gap-2 px-4 py-3 text-sm
                          font-medium text-foreground">
        <FileSignature size={15} className="text-muted-foreground" />
        Create a signing request
      </summary>

      <div className="space-y-3 border-t border-border p-4">
        <p className="text-small text-muted-foreground">
          If you are buying a certificate, the supplier asks for this first. The private key
          is created on your server and stays there — when the certificate arrives, paste it
          into “I already have a certificate” above and it will find the key by itself.
        </p>
        <p className="text-caption text-muted-foreground">
          Only the organisation details below are worth filling in, and only for a certificate
          that names your company. The domain <span className="font-mono">{domain}</span> and
          the rest of its addresses are included automatically.
        </p>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field k="organisation" label="Organisation" placeholder="Acme Ltd" />
          <Field k="unit" label="Department (optional)" placeholder="IT" />
          <Field k="locality" label="City" placeholder="London" />
          <Field k="state" label="Region" placeholder="England" />
          <Field k="country" label="Country code" placeholder="GB" />
        </div>

        <Button size="sm" variant="outline" disabled={make.isPending}
                onClick={() => make.mutate()}>
          {make.isPending && <Loader2 size={13} className="animate-spin" />}
          Create the request
        </Button>

        {error && (
          <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                        text-small text-destructive">{error}</p>
        )}

        {csr && (
          <div>
            <div className="mb-1 flex items-center gap-2">
              <span className="text-caption text-muted-foreground">
                Send this to your certificate supplier
              </span>
              <button type="button"
                      onClick={() => {
                        navigator.clipboard.writeText(csr)
                        setCopied(true); setTimeout(() => setCopied(false), 1500)
                      }}
                      className="inline-flex items-center gap-1 text-caption
                                 text-muted-foreground hover:text-foreground">
                <Copy size={11} /> {copied ? "copied" : "copy"}
              </button>
            </div>
            <pre className="max-h-56 overflow-auto rounded-lg bg-muted p-3 font-mono
                            text-caption text-foreground">{csr}</pre>
          </div>
        )}
      </div>
    </details>
  )
}

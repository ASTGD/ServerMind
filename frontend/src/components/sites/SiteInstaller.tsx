import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Globe, Rocket, Package, Loader2, Sparkles, LayoutPanelTop, Check } from "lucide-react"
import { getSiteCatalogue, createSite, type SiteType } from "@/api/sites"
import { Button } from "@/components/ui"
import { strongPassword } from "@/lib/password"

/**
 * What do you want to put on this server?
 *
 * Lives ON the Sites page rather than in a dialog. A modal was the wrong container for
 * this: twelve options in an overlay meant a scrolling list with the last few cut off, and
 * a covered page loses the thing the choice is about — the server and what is already on
 * it. Inline, the options get the full width and nothing is hidden behind them.
 *
 * The list comes from the backend, not from this file. Adding a type is then one entry
 * plus a playbook — which is the whole promise of a catalogue. A copy here would drift the
 * first time either side was edited, and the form would send a variable the installer does
 * not read, or miss one it does.
 *
 * Choosing collapses the grid to the one chosen, rather than replacing the whole panel:
 * you keep seeing what you picked while you answer its questions, and changing your mind
 * is one click rather than a step backwards.
 */

const GROUP_ICON: Record<string, typeof Globe> = {
  websites: Globe,
  applications: Rocket,
  apps: Package,
}

interface Props {
  serverId: string
  /** Shown when the server is a control panel, which owns its own websites. */
  panelOnly?: boolean
  onClose: () => void
  onAsk?: () => void
}

export default function SiteInstaller({ serverId, panelOnly, onClose, onAsk }: Props) {
  const qc = useQueryClient()
  const [chosen, setChosen] = useState<SiteType | null>(null)
  const [domain, setDomain] = useState("")
  const [values, setValues] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  const { data: catalogue, isLoading } = useQuery({
    queryKey: ["site-catalogue"],
    queryFn: getSiteCatalogue,
    enabled: !panelOnly,
    staleTime: 5 * 60_000,
  })

  const create = useMutation({
    mutationFn: () =>
      createSite(serverId, { domain, site_type: chosen!.id, variables: values }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["server-sites", serverId] })
      qc.invalidateQueries({ queryKey: ["sites"] })
      onClose()
    },
    // The server's message names the actual problem — an unusable domain, a duplicate, a
    // missing installer — so show it rather than a generic failure.
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "The site could not be created."),
  })

  function pick(type: SiteType) {
    setChosen(type)
    setError(null)
    // Prefill the installer's own defaults so the common case is one field and a button —
    // and generate the secrets, which have no default and are exactly where a customer
    // asked to invent one invents a weak one. Two of these (Nextcloud, n8n) are what they
    // will log in with, on a server anyone on the internet can reach.
    setValues(Object.fromEntries(type.fields.map(
      (f) => [f.name, f.default || (f.secret ? strongPassword() : "")],
    )))
  }

  return (
    <section className="rounded-xl border border-border bg-card">
      <header className="flex items-center justify-between gap-4 border-b border-border px-4 py-3">
        <div>
          <h3 className="text-sm font-medium text-foreground">Add a website</h3>
          <p className="text-caption text-muted-foreground">
            {chosen ? chosen.blurb : "Choose what should go on this server."}
          </p>
        </div>
        <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
      </header>

      {/* A control panel manages its own websites — anything we wrote directly would be
          invisible to it, so the installers are not offered at all rather than offered and
          then refused. */}
      {panelOnly ? (
        <div className="space-y-2 p-4">
          <div className="flex items-start gap-3 rounded-lg border border-border p-3">
            <LayoutPanelTop size={15} className="mt-0.5 shrink-0 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium text-foreground">Create it in the control panel</p>
              <p className="mt-0.5 text-small text-muted-foreground">
                This server runs a control panel, which manages its own websites. Creating
                one any other way would be invisible to it.
              </p>
            </div>
          </div>
          {onAsk && <AskAllyRow onAsk={onAsk} />}
        </div>
      ) : isLoading ? (
        <div className="flex justify-center py-12 text-muted-foreground">
          <Loader2 size={18} className="animate-spin" />
        </div>
      ) : chosen ? (
        <div className="p-4">
          <ChosenRow type={chosen} onChange={() => { setChosen(null); setError(null) }} />

          <form
            onSubmit={(e) => { e.preventDefault(); setError(null); create.mutate() }}
            className="mt-4 max-w-xl space-y-3"
          >
            <Field label="Domain" hint="Point this domain's DNS at this server, now or later — the site is built either way.">
              <input
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="shop.example.com"
                required
                autoFocus
                className={INPUT}
              />
            </Field>

            {chosen.fields.map((f) => (
              <Field
                key={f.name}
                label={f.label}
                // Shown, never masked: this is the only time it is ever displayed, and for
                // Nextcloud and n8n it is the login itself. Hiding it behind dots would
                // mean the customer cannot check what they are about to be given.
                hint={f.secret ? "Save this somewhere — it is not stored here and cannot be shown again." : undefined}
              >
                {f.secret ? (
                  <div className="mt-1 flex gap-2">
                    <input
                      value={values[f.name] ?? ""}
                      onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
                      required={f.required}
                      className={INPUT.replace("mt-1 ", "")}
                    />
                    <Button type="button" variant="outline" size="sm"
                            onClick={() => setValues({ ...values, [f.name]: strongPassword() })}>
                      New
                    </Button>
                  </div>
                ) : (
                  <input
                    value={values[f.name] ?? ""}
                    onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
                    required={f.required}
                    className={INPUT}
                  />
                )}
              </Field>
            ))}

            {error && (
              <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-destructive">
                {error}
              </p>
            )}

            <div className="flex items-center gap-3 pt-1">
              <Button type="submit" disabled={create.isPending}>
                {create.isPending ? "Starting…" : `Create ${chosen.label}`}
              </Button>
              <p className="text-caption text-muted-foreground">
                It builds in the background — you can leave this page.
              </p>
            </div>
          </form>
        </div>
      ) : (
        <div className="space-y-5 p-4">
          {catalogue?.groups.map((group) => {
            const items = catalogue.types.filter((t) => t.group === group.id)
            if (!items.length) return null
            const Icon = GROUP_ICON[group.id] ?? Globe
            return (
              <div key={group.id}>
                <div className="flex items-baseline gap-2">
                  <Icon size={13} className="translate-y-0.5 text-muted-foreground" />
                  <h4 className="text-sm font-medium text-foreground">{group.label}</h4>
                  <p className="text-caption text-muted-foreground">{group.blurb}</p>
                </div>
                <div className="mt-2 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                  {items.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => pick(t)}
                      className="rounded-lg border border-border p-3 text-left transition-colors hover:border-primary/60 hover:bg-accent"
                    >
                      <p className="text-sm font-medium text-foreground">{t.label}</p>
                      <p className="mt-0.5 text-caption text-muted-foreground">{t.blurb}</p>
                      {t.est_seconds ? (
                        <p className="mt-1.5 text-caption text-muted-foreground/70">
                          about {Math.max(1, Math.round(t.est_seconds / 60))} min
                        </p>
                      ) : null}
                    </button>
                  ))}
                </div>
              </div>
            )
          })}

          {onAsk && <AskAllyRow onAsk={onAsk} />}
        </div>
      )}
    </section>
  )
}

const INPUT =
  "mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground"

function Field({ label, hint, children }: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div>
      <label className="text-caption text-muted-foreground">{label}</label>
      {children}
      {hint && <p className="mt-1 text-caption text-muted-foreground">{hint}</p>}
    </div>
  )
}

/** What you picked, kept in view while you answer its questions. */
function ChosenRow({ type, onChange }: { type: SiteType; onChange: () => void }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-primary/40 bg-primary/[0.04] p-3">
      <div className="flex items-start gap-2.5">
        <Check size={15} className="mt-0.5 shrink-0 text-primary" />
        <div>
          <p className="text-sm font-medium text-foreground">{type.label}</p>
          {type.est_seconds ? (
            <p className="text-caption text-muted-foreground">
              takes about {Math.max(1, Math.round(type.est_seconds / 60))} min
            </p>
          ) : null}
        </div>
      </div>
      <button
        type="button"
        onClick={onChange}
        className="shrink-0 text-caption text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
      >
        Change
      </button>
    </div>
  )
}

function AskAllyRow({ onAsk }: { onAsk: () => void }) {
  return (
    <button
      onClick={onAsk}
      className="flex w-full items-start gap-3 rounded-lg border border-dashed border-border p-3 text-left hover:bg-accent"
    >
      <Sparkles size={15} className="mt-0.5 shrink-0 text-primary" />
      <div>
        <p className="text-sm font-medium text-foreground">Something else — ask Ally</p>
        <p className="mt-0.5 text-caption text-muted-foreground">
          For an unusual layout, an existing site to work around, or anything not listed here.
        </p>
      </div>
    </button>
  )
}

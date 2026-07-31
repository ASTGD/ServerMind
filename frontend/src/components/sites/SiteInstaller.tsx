import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Globe, Rocket, Package, Loader2, LayoutPanelTop, Check, ChevronDown,
} from "lucide-react"
import { getSiteCatalogue, installOnSite, type SiteType } from "@/api/sites"
import { Button } from "@/components/ui"
import { strongPassword } from "@/lib/password"

/**
 * What runs on this site.
 *
 * Lives on ONE site's page, not on the list of sites. A site is added by its domain alone,
 * and choosing what goes on it is a separate question asked afterwards — which is how
 * someone actually arrives at it ("I have shop.example.com, now put WordPress on it").
 * Putting the catalogue on the list meant deciding both at once, before the site existed.
 *
 * The list comes from the backend, not from this file. Adding a type is then one entry
 * plus a playbook — a copy here would drift the first time either side was edited, and the
 * form would send a variable the installer does not read, or miss one it does.
 */

const GROUP_ICON: Record<string, typeof Globe> = {
  websites: Globe,
  applications: Rocket,
  apps: Package,
}

interface Props {
  siteId: string
  serverId: string
  /** A control panel owns its own sites, so nothing here can be written behind its back. */
  panelOnly?: boolean
}

export default function SiteInstaller({ siteId, serverId, panelOnly }: Props) {
  const qc = useQueryClient()
  const [chosen, setChosen] = useState<SiteType | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [showAll, setShowAll] = useState(false)

  const { data: catalogue, isLoading } = useQuery({
    queryKey: ["site-catalogue"],
    queryFn: getSiteCatalogue,
    enabled: !panelOnly,
    staleTime: 5 * 60_000,
  })

  const install = useMutation({
    mutationFn: () => installOnSite(siteId, { site_type: chosen!.id, variables: values }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["site", siteId] })
      qc.invalidateQueries({ queryKey: ["server-sites", serverId] })
      qc.invalidateQueries({ queryKey: ["sites"] })
    },
    // The server's message names the actual problem — a folder with files in it, a missing
    // installer, a server that is not ready — so show it rather than a generic failure.
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "It could not be installed."),
  })

  const popular = (catalogue?.types ?? []).filter((t) => t.popular)
  const rest = (catalogue?.types ?? []).filter((t) => !t.popular)

  function pick(type: SiteType) {
    setChosen(type)
    setError(null)
    // Prefill the installer's own defaults, and generate the secrets — those have no
    // default and are exactly where a customer asked to invent one invents a weak one.
    // For Nextcloud and n8n it is the password they will log in with, on a server anyone
    // on the internet can reach.
    setValues(Object.fromEntries(type.fields.map(
      (f) => [f.name, f.default || (f.secret ? strongPassword() : "")],
    )))
  }

  if (panelOnly) {
    return (
      <section className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-start gap-3">
          <LayoutPanelTop size={15} className="mt-0.5 shrink-0 text-muted-foreground" />
          <div>
            <p className="text-sm font-medium text-foreground">
              This server runs a control panel
            </p>
            <p className="mt-0.5 text-small text-muted-foreground">
              It manages its own sites, so anything installed any other way would be
              invisible to it. Use the panel, or ask Ally.
            </p>
          </div>
        </div>
      </section>
    )
  }

  return (
    <section className="rounded-xl border border-border bg-card">
      <header className="border-b border-border px-4 py-3">
        <h3 className="text-sm font-medium text-foreground">Install something here</h3>
        <p className="text-caption text-muted-foreground">
          {chosen ? chosen.blurb : "Nothing runs on this site yet. Choose what should."}
        </p>
      </header>

      {isLoading ? (
        <div className="flex justify-center py-12 text-muted-foreground">
          <Loader2 size={18} className="animate-spin" />
        </div>
      ) : (
        <form
          onSubmit={(e) => { e.preventDefault(); setError(null); install.mutate() }}
          className="space-y-4 p-4"
        >
          {chosen ? (
            <div className="max-w-xl space-y-3">
              <ChosenRow type={chosen} onChange={() => { setChosen(null); setError(null) }} />

              {chosen.fields.map((f) => (
                <Field
                  key={f.name}
                  label={f.label}
                  // Shown, never masked: this is the only time it is displayed, and for
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
                <Button type="submit" disabled={install.isPending}>
                  {install.isPending ? "Starting…" : `Install ${chosen.label}`}
                </Button>
                <p className="text-caption text-muted-foreground">
                  It runs in the background — you can leave this page.
                </p>
              </div>
            </div>
          ) : (
            <>
              {/* The common few first, without group headings. Twelve tiles under three
                  headings is a catalogue to study; eight is a choice to make, and it is the
                  right choice for almost everyone. The rest are one click away rather than
                  gone — the headings come back with them, which is when they help. */}
              {showAll ? (
                <div className="space-y-4">
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
                        <TypeGrid items={items} onPick={pick} />
                      </div>
                    )
                  })}
                </div>
              ) : (
                <TypeGrid items={popular} onPick={pick} />
              )}

              {!showAll && rest.length > 0 && (
                <button
                  type="button"
                  onClick={() => setShowAll(true)}
                  className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-border py-2 text-caption text-muted-foreground hover:bg-accent hover:text-foreground"
                >
                  <ChevronDown size={13} />
                  Show all {(catalogue?.types.length ?? 0)} options
                </button>
              )}
            </>
          )}
        </form>
      )}
    </section>
  )
}

/** Every button inside the form is explicitly not a submit — a tile that submitted would
 *  try to install with nothing chosen. */
function TypeGrid({ items, onPick }: {
  items: SiteType[]
  onPick: (t: SiteType) => void
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((t) => (
        <button
          key={t.id}
          type="button"
          onClick={() => onPick(t)}
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

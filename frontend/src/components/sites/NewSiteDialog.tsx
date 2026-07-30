import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Globe, Rocket, Package, Loader2, ArrowLeft, Sparkles, LayoutPanelTop } from "lucide-react"
import { getSiteCatalogue, createSite, type SiteType } from "@/api/sites"

/**
 * What do you want to put on this server?
 *
 * The list comes from the backend, not from this file. Adding a type is then one entry plus
 * a playbook — which is the whole promise of a catalogue. A copy here would drift the first
 * time either side was edited, and the form would send a variable the installer does not
 * read, or miss one it does.
 *
 * Two steps on purpose: choose the thing, then answer only that thing's questions. A single
 * form showing every field for every type is how a control panel ends up asking a customer
 * for a database name before they have said they want WordPress.
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

export default function NewSiteDialog({ serverId, panelOnly, onClose, onAsk }: Props) {
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
    // The server's message names the actual problem — an unusable domain, a duplicate,
    // a missing installer — so show it rather than a generic failure.
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "The site could not be created."),
  })

  function pick(type: SiteType) {
    setChosen(type)
    setError(null)
    // Prefill the installer's own defaults so the common case is one click away.
    setValues(Object.fromEntries(type.fields.map((f) => [f.name, f.default])))
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-16">
      <div className="w-full max-w-2xl rounded-xl border border-border bg-card p-5 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-h3 text-foreground">
              {chosen ? chosen.label : "Add a website"}
            </h3>
            <p className="mt-0.5 text-small text-muted-foreground">
              {chosen ? chosen.blurb : "What should go on this server?"}
            </p>
          </div>
          <button
            onClick={onClose}
            className="rounded-md border border-border px-2 py-1 text-caption text-muted-foreground hover:bg-accent"
          >
            Cancel
          </button>
        </div>

        {/* A control panel manages its own websites — anything we wrote directly would be
            invisible to it, so the installers are not offered at all rather than offered
            and then refused. */}
        {panelOnly ? (
          <div className="mt-4 space-y-3">
            <div className="flex items-start gap-3 rounded-lg border border-border p-4">
              <LayoutPanelTop size={16} className="mt-0.5 text-muted-foreground" />
              <div>
                <p className="text-sm font-medium text-foreground">Create it in the control panel</p>
                <p className="mt-0.5 text-small text-muted-foreground">
                  This server runs a control panel, which manages its own websites. Creating
                  one any other way would be invisible to it.
                </p>
              </div>
            </div>
            {onAsk && (
              <button
                onClick={onAsk}
                className="flex w-full items-start gap-3 rounded-lg border border-border p-4 text-left hover:bg-accent"
              >
                <Sparkles size={16} className="mt-0.5 text-primary" />
                <div>
                  <p className="text-sm font-medium text-foreground">Let Ally set it up</p>
                  <p className="mt-0.5 text-small text-muted-foreground">
                    Ally looks at this server first and adapts.
                  </p>
                </div>
              </button>
            )}
          </div>
        ) : isLoading ? (
          <div className="flex justify-center py-10 text-muted-foreground">
            <Loader2 size={18} className="animate-spin" />
          </div>
        ) : !chosen ? (
          <div className="mt-4 space-y-5">
            {catalogue?.groups.map((group) => {
              const items = catalogue.types.filter((t) => t.group === group.id)
              if (!items.length) return null
              const Icon = GROUP_ICON[group.id] ?? Globe
              return (
                <div key={group.id}>
                  <div className="flex items-center gap-1.5">
                    <Icon size={13} className="text-muted-foreground" />
                    <h4 className="text-sm font-medium text-foreground">{group.label}</h4>
                  </div>
                  <p className="mt-0.5 text-caption text-muted-foreground">{group.blurb}</p>
                  <div className="mt-2 grid gap-2 sm:grid-cols-2">
                    {items.map((t) => (
                      <button
                        key={t.id}
                        onClick={() => pick(t)}
                        className="rounded-lg border border-border p-3 text-left transition-colors hover:border-primary/50 hover:bg-accent"
                      >
                        <p className="text-sm font-medium text-foreground">{t.label}</p>
                        <p className="mt-0.5 text-caption text-muted-foreground">{t.blurb}</p>
                        {t.est_seconds ? (
                          <p className="mt-1 text-caption text-muted-foreground/70">
                            about {Math.max(1, Math.round(t.est_seconds / 60))} min
                          </p>
                        ) : null}
                      </button>
                    ))}
                  </div>
                </div>
              )
            })}

            {onAsk && (
              <button
                onClick={onAsk}
                className="flex w-full items-start gap-3 rounded-lg border border-dashed border-border p-3 text-left hover:bg-accent"
              >
                <Sparkles size={15} className="mt-0.5 text-primary" />
                <div>
                  <p className="text-sm font-medium text-foreground">Something else — ask Ally</p>
                  <p className="mt-0.5 text-caption text-muted-foreground">
                    For an unusual layout, an existing site to work around, or anything not
                    listed here.
                  </p>
                </div>
              </button>
            )}
          </div>
        ) : (
          <form
            onSubmit={(e) => { e.preventDefault(); setError(null); create.mutate() }}
            className="mt-4 space-y-3"
          >
            <button
              type="button"
              onClick={() => { setChosen(null); setError(null) }}
              className="flex items-center gap-1 text-caption text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft size={12} /> Choose something else
            </button>

            <div>
              <label className="text-caption text-muted-foreground">Domain</label>
              <input
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="shop.example.com"
                required
                autoFocus
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground"
              />
              <p className="mt-1 text-caption text-muted-foreground">
                Point this domain's DNS at this server, now or later — the site is built
                either way.
              </p>
            </div>

            {chosen.fields.map((f) => (
              <div key={f.name}>
                <label className="text-caption text-muted-foreground">{f.label}</label>
                <input
                  type={f.secret ? "password" : "text"}
                  value={values[f.name] ?? ""}
                  onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}
                  required={f.required}
                  className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground"
                />
              </div>
            ))}

            {error && (
              <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-destructive">
                {error}
              </p>
            )}

            <div className="flex items-center gap-2 pt-1">
              <button
                type="submit"
                disabled={create.isPending}
                className="rounded-lg bg-primary px-3 py-1.5 text-small font-medium text-primary-foreground disabled:opacity-60"
              >
                {create.isPending ? "Starting…" : `Create ${chosen.label}`}
              </button>
              <p className="text-caption text-muted-foreground">
                It builds in the background — you can leave this page.
              </p>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

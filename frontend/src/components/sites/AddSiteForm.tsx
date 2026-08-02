import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { LayoutPanelTop, Loader2, Search, Sparkles } from "lucide-react"
import { createSite, getSiteCatalogue, type SiteType } from "@/api/sites"
import { Button, Input, Label } from "@/components/ui"

/**
 * Adding a site is one question: what domain?
 *
 * A site IS a domain — everything else about it (WordPress or Laravel, which database,
 * which password) is a question about what goes ON it, and asking all of that before the
 * site exists means deciding two things at once. So the plain path builds an empty site:
 * the folder, the address, and a page that loads. What runs there is chosen afterwards, on
 * the site's own page, where the question actually belongs.
 *
 * Advanced settings is for the person who already knows what they want and would rather
 * not make two trips. It is hidden by default and its contents are fetched only when it is
 * opened, so the common path costs nothing.
 */

interface Props {
  serverId: string
  /** A control panel owns its own sites; one written behind its back is invisible to it. */
  panelOnly?: boolean
  onAsk?: () => void
  /** Offered only when nothing is listed yet — see the note by the button. */
  showFind?: boolean
  onFind?: () => void
}

export default function AddSiteForm({
  serverId, panelOnly, onAsk, showFind, onFind,
}: Props) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [domain, setDomain] = useState("")
  const [advanced, setAdvanced] = useState(false)
  const [siteType, setSiteType] = useState("static")
  const [vars, setVars] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)

  // Only once somebody asks for it. The plain path is a domain and a button.
  const { data: catalogue, isLoading: loadingTypes } = useQuery({
    queryKey: ["site-catalogue"],
    queryFn: getSiteCatalogue,
    enabled: advanced && !panelOnly,
  })
  const chosen = catalogue?.types.find((t) => t.id === siteType)

  const create = useMutation({
    mutationFn: () => createSite(serverId, { domain, site_type: siteType, variables: vars }),
    onSuccess: (site) => {
      qc.invalidateQueries({ queryKey: ["server-sites", serverId] })
      qc.invalidateQueries({ queryKey: ["sites"] })
      // Straight to the new site, because the next thing anyone wants is to put something
      // on it — and that only exists there.
      navigate(`/servers/${serverId}/sites/${site.id}`)
    },
    // The server's message names the actual problem — an unusable domain, a duplicate, a
    // server with no web server on it — so show it rather than a generic failure.
    onError: (e: unknown) => setError(
      (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? "The site could not be added."),
  })

  if (panelOnly) {
    return (
      <Card>
        <Explain title="New site">
          This server runs a control panel, and the panel owns its own sites.
        </Explain>
        <div className="p-5 sm:pl-0">
          <div className="flex items-start gap-3 rounded-lg border border-border p-3">
            <LayoutPanelTop size={15} className="mt-0.5 shrink-0 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium text-foreground">Create it in the control panel</p>
              <p className="mt-0.5 text-small text-muted-foreground">
                A site created any other way would be invisible to it, and would never get
                its certificate renewed.
              </p>
            </div>
          </div>
          {onAsk && (
            <button type="button" onClick={onAsk}
              className="mt-3 inline-flex items-center gap-1.5 text-caption text-muted-foreground hover:text-foreground">
              <Sparkles size={13} className="text-primary" /> Or ask Ally to set one up
            </button>
          )}
        </div>
      </Card>
    )
  }

  return (
    <form onSubmit={(e) => { e.preventDefault(); setError(null); create.mutate() }}>
      <Card>
        <Explain title="New site">
          Create a new site on this server. Give it a domain — what runs on it is chosen
          afterwards, on the site's own page. Press Advanced settings to choose now instead.
        </Explain>

        <div className="space-y-3 p-5 sm:pl-0">
          <div>
            <Label htmlFor="new-site-domain">
              Domain <span className="text-destructive">*</span>
            </Label>
            <Input
              id="new-site-domain"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              placeholder="Enter a domain (e.g. shop.example.com)"
              required
              className="font-mono"
            />
            <p className="mt-1 text-caption text-muted-foreground">
              Point this domain's DNS at this server, now or later — the site is built
              either way.
            </p>
          </div>

          {advanced && (
            <div className="space-y-3 border-t border-border pt-3">
              {loadingTypes ? (
                <p className="flex items-center gap-2 text-small text-muted-foreground">
                  <Loader2 size={13} className="animate-spin" /> Loading what can go here…
                </p>
              ) : (
                <>
                  <div>
                    <Label htmlFor="new-site-type">What to put on it</Label>
                    <select
                      id="new-site-type"
                      value={siteType}
                      onChange={(e) => { setSiteType(e.target.value); setVars({}) }}
                      className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground"
                    >
                      {(catalogue?.types ?? []).map((t) => (
                        <option key={t.id} value={t.id}>{t.label}</option>
                      ))}
                    </select>
                    {chosen?.blurb && (
                      <p className="mt-1 text-caption text-muted-foreground">{chosen.blurb}</p>
                    )}
                  </div>
                  {/* Whatever that installer asks for, and nothing we invented: the fields
                      come from the same catalogue the installer is defined in. */}
                  {(chosen?.fields ?? []).map((f) => (
                    <FieldFor key={f.name} field={f}
                      value={vars[f.name] ?? f.default}
                      onChange={(v) => setVars((s) => ({ ...s, [f.name]: v }))} />
                  ))}
                </>
              )}
            </div>
          )}

          {error && (
            <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-destructive">
              {error}
            </p>
          )}

          {/* An empty list means one of two things, and only the customer knows which: a
              server with nothing on it, or one whose sites we have not looked for yet.
              Someone who has just connected a box running twenty sites should not be asked
              to add the twenty-first. */}
          {showFind && (
            <p className="text-caption text-muted-foreground">
              Already have websites on this server?{" "}
              <button type="button" onClick={onFind}
                className="inline-flex items-center gap-1 font-medium text-foreground underline-offset-2 hover:underline">
                <Search size={11} /> Look for them
              </button>{" "}
              — ServerAlly reads the web server's own configuration and lists what is there.
            </p>
          )}
        </div>

        {/* The actions sit on their own bar, so the primary one is in the same place on
            every card of this shape rather than wherever the form happened to end. */}
        <footer className="col-span-full flex flex-wrap items-center justify-between gap-3 border-t border-border bg-muted/30 px-5 py-3">
          {onAsk ? (
            <button type="button" onClick={onAsk}
              className="inline-flex items-center gap-1.5 text-caption text-muted-foreground hover:text-foreground">
              <Sparkles size={13} className="text-primary" /> Or ask Ally to set one up
            </button>
          ) : <span />}
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="sm"
              onClick={() => setAdvanced((v) => !v)}>
              Advanced settings
            </Button>
            <Button type="submit" size="sm" disabled={create.isPending || !domain.trim()}>
              {create.isPending
                ? <><Loader2 size={13} className="animate-spin" /> Creating…</>
                : "Create site"}
            </Button>
          </div>
        </footer>
      </Card>
    </form>
  )
}

/** The two-column shell: what this is on the left, what it needs on the right. */
function Card({ children }: { children: React.ReactNode }) {
  return (
    <section className="grid overflow-hidden rounded-xl border border-border bg-card sm:grid-cols-[minmax(0,280px)_minmax(0,1fr)]">
      {children}
    </section>
  )
}

function Explain({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="p-5 sm:pr-6">
      <h3 className="text-sm font-medium text-foreground">{title}</h3>
      <p className="mt-1 text-caption text-muted-foreground">{children}</p>
    </div>
  )
}

function FieldFor({ field, value, onChange }: {
  field: SiteType["fields"][number]
  value: string
  onChange: (v: string) => void
}) {
  return (
    <div>
      <Label htmlFor={`nsf-${field.name}`}>
        {field.label}
        {field.required && <span className="text-destructive"> *</span>}
      </Label>
      <Input
        id={`nsf-${field.name}`}
        type={field.secret ? "password" : "text"}
        value={value}
        required={field.required}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

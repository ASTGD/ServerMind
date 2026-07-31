import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { LayoutPanelTop, Sparkles } from "lucide-react"
import { createSite } from "@/api/sites"
import { Button } from "@/components/ui"

/**
 * Adding a site is one question: what domain?
 *
 * A site IS a domain — everything else about it (WordPress or Laravel, which database,
 * which password) is a question about what goes ON it, and asking all of that before the
 * site exists means deciding two things at once. So this builds an empty site: the folder,
 * the address, and a page that loads. What runs there is chosen afterwards, on the site's
 * own page, where the question actually belongs.
 *
 * "Empty" is deliberate rather than a default with PHP switched on. It works on any server
 * that has a web server at all, and it keeps every other type — including "PHP website" —
 * a single, consistent choice made in one place.
 */

interface Props {
  serverId: string
  /** A control panel owns its own sites; one written behind its back is invisible to it. */
  panelOnly?: boolean
  onClose?: () => void
  onAsk?: () => void
}

export default function AddSiteForm({ serverId, panelOnly, onClose, onAsk }: Props) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [domain, setDomain] = useState("")
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () => createSite(serverId, { domain, site_type: "static", variables: {} }),
    onSuccess: (site) => {
      qc.invalidateQueries({ queryKey: ["server-sites", serverId] })
      qc.invalidateQueries({ queryKey: ["sites"] })
      // Straight to the new site, because the next thing anyone wants is to put something
      // on it — and that only exists there.
      navigate(`/servers/${serverId}/sites/${site.id}`)
    },
    // The server's message names the actual problem — an unusable domain, a duplicate, a
    // server with no web server on it — so show it rather than a generic failure.
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "The site could not be added."),
  })

  return (
    <section className="rounded-xl border border-border bg-card">
      <header className="flex items-start justify-between gap-4 border-b border-border px-4 py-3">
        <div>
          <h3 className="text-sm font-medium text-foreground">Add a site</h3>
          <p className="text-caption text-muted-foreground">
            {panelOnly
              ? "This server runs a control panel."
              : "Give it a domain. You choose what runs on it next."}
          </p>
        </div>
        {onClose && (
          <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
        )}
      </header>

      {panelOnly ? (
        <div className="space-y-2 p-4">
          <div className="flex items-start gap-3 rounded-lg border border-border p-3">
            <LayoutPanelTop size={15} className="mt-0.5 shrink-0 text-muted-foreground" />
            <div>
              <p className="text-sm font-medium text-foreground">Create it in the control panel</p>
              <p className="mt-0.5 text-small text-muted-foreground">
                This server's panel manages its own sites. One created any other way would
                be invisible to it, and would never get its certificate renewed.
              </p>
            </div>
          </div>
          {onAsk && <AskAlly onAsk={onAsk} />}
        </div>
      ) : (
        <form
          onSubmit={(e) => { e.preventDefault(); setError(null); create.mutate() }}
          className="space-y-3 p-4"
        >
          <div className="max-w-xl">
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

          {error && (
            <p className="max-w-xl rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-destructive">
              {error}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-3 pt-1">
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Adding…" : "Add site"}
            </Button>
            {onAsk && (
              <button
                type="button"
                onClick={onAsk}
                className="inline-flex items-center gap-1.5 text-caption text-muted-foreground hover:text-foreground"
              >
                <Sparkles size={13} className="text-primary" /> Or ask Ally to set one up
              </button>
            )}
          </div>
        </form>
      )}
    </section>
  )
}

function AskAlly({ onAsk }: { onAsk: () => void }) {
  return (
    <button
      type="button"
      onClick={onAsk}
      className="flex w-full items-start gap-3 rounded-lg border border-dashed border-border p-3 text-left hover:bg-accent"
    >
      <Sparkles size={15} className="mt-0.5 shrink-0 text-primary" />
      <div>
        <p className="text-sm font-medium text-foreground">Ask Ally instead</p>
        <p className="mt-0.5 text-caption text-muted-foreground">
          Ally looks at this server first and uses the right method for it.
        </p>
      </div>
    </button>
  )
}

import { useState } from "react"
import { useNavigate, useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Loader2 } from "lucide-react"
import {
  forgetSite, getSiteTypeOptions, removeSite, setSiteType, type SiteDetail,
} from "@/api/sites"
import { Button } from "@/components/ui"
import SiteNotes from "@/components/sites/SiteNotes"
import { wasCreatedHere } from "@/lib/siteInstall"

/**
 * Everything about the site itself, rather than about what runs on it.
 *
 * Removal lives here because this is where someone looks for it — and because it is the
 * most destructive thing on any site screen, it says exactly what will be destroyed before
 * asking, and takes the domain typed back. There is no undo anywhere in this system.
 *
 * A site ServerAlly did not build is deliberately not removable: its files are laid out in
 * a way we did not choose. Untracking it is offered instead, which changes nothing on the
 * server.
 */
export default function SiteSettings() {
  const { site } = useOutletContext<{ site: SiteDetail }>()
  const navigate = useNavigate()
  const [typed, setTyped] = useState("")
  const [dropDb, setDropDb] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const ours = wasCreatedHere(site)
  const backToServer = () => navigate(`/servers/${site.server.id}/sites`)

  const remove = useMutation({
    mutationFn: () => removeSite(site.id, { confirm_domain: typed, drop_database: dropDb }),
    onSuccess: backToServer,
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "The site could not be removed."),
  })

  const forget = useMutation({
    mutationFn: () => forgetSite(site.id),
    onSuccess: backToServer,
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "It could not be untracked."),
  })

  return (
    <div className="space-y-4">
      <section className="rounded-xl border border-border bg-card p-4">
        <h2 className="text-sm font-medium text-foreground">About this site</h2>
        <dl className="mt-3 space-y-2 text-small">
          <Row label="Domain" value={site.domain} mono />
          <Row label="Server" value={site.server.name} />
          {site.doc_root && <Row label="Folder" value={site.doc_root} mono />}
          <Row label="Running" value={site.app_type + (site.app_version ? ` ${site.app_version}` : "")} />
          <Row label="Added" value={ours ? "created by ServerAlly" : "found on the server"} />
          {/* Ploi shows this too, and for the same reason: it is what you pass to the API
              or to an AI assistant over MCP when you mean THIS site. */}
          <Row label="Site ID" value={site.id} mono />
        </dl>
      </section>

      <ProjectType site={site} />
      <SiteNotes site={site} />

      <section className="rounded-xl border border-destructive/40 bg-card p-4">
        <h2 className="flex items-center gap-2 text-sm font-medium text-destructive">
          <AlertTriangle size={14} /> {ours ? "Remove this site" : "Stop tracking this site"}
        </h2>

        {ours ? (
          <>
            <p className="mt-1 text-small text-muted-foreground">
              This deletes it from the server. Everything below goes, and there is no copy
              of any of it here:
            </p>
            <ul className="mt-2 space-y-0.5 text-small text-muted-foreground">
              <li>· its files{site.doc_root ? ` in ${site.doc_root.replace(/\/public$/, "")}` : ""}</li>
              <li>· its web server configuration, so the domain stops being served</li>
              <li>· its HTTPS certificate</li>
            </ul>

            <label className="mt-3 flex items-start gap-2 text-small text-foreground">
              <input
                type="checkbox"
                checked={dropDb}
                onChange={(e) => setDropDb(e.target.checked)}
                className="mt-0.5"
              />
              <span>
                Also delete its database
                <span className="block text-caption text-muted-foreground">
                  Only the database this site created. Leave this off if anything else uses it.
                </span>
              </span>
            </label>

            <form
              onSubmit={(e) => { e.preventDefault(); setError(null); remove.mutate() }}
              className="mt-3 max-w-md space-y-2"
            >
              <label className="text-caption text-muted-foreground">
                Type <span className="font-mono text-foreground">{site.domain}</span> to confirm
              </label>
              <input
                value={typed}
                onChange={(e) => setTyped(e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground"
              />
              {error && (
                <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-destructive">
                  {error}
                </p>
              )}
              <Button type="submit" variant="danger"
                      disabled={remove.isPending || typed !== site.domain}>
                {remove.isPending ? "Removing…" : "Remove this site from the server"}
              </Button>
            </form>
          </>
        ) : (
          <>
            <p className="mt-1 text-small text-muted-foreground">
              ServerAlly found this site rather than building it, so it is not deleted from
              here — its files are laid out in a way we did not choose, and guessing would
              risk destroying something that cannot be recovered. Untracking it removes it
              from your list and changes nothing on the server.
            </p>
            {error && (
              <p className="mt-2 rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-destructive">
                {error}
              </p>
            )}
            <Button className="mt-3" variant="outline" size="sm"
                    disabled={forget.isPending} onClick={() => { setError(null); forget.mutate() }}>
              {forget.isPending ? "Removing from the list…" : "Stop tracking it"}
            </Button>
          </>
        )}
      </section>
    </div>
  )
}

/**
 * What this site is — Ploi's "Project type".
 *
 * They never detect; they ask, so they always have an answer. We detect, which is better
 * when it works and has nothing to fall back on when it does not: a site we cannot name
 * stays Unknown for ever and gets no application section at all. This is the fallback.
 *
 * The card only argues for itself when it needs to. On a site we named correctly it is a
 * quiet line saying what we found; on an Unknown one it says plainly what that costs and
 * what picking a type will give them.
 */
function ProjectType({ site }: { site: SiteDetail }) {
  const qc = useQueryClient()
  const [error, setError] = useState<string | null>(null)

  const opts = useQuery({
    queryKey: ["site-type", site.id],
    queryFn: () => getSiteTypeOptions(site.id),
  })

  const save = useMutation({
    mutationFn: (value: string) => setSiteType(site.id, value),
    onSuccess: () => {
      setError(null)
      // The menu, the breadcrumb and the application section all read the site.
      qc.invalidateQueries({ queryKey: ["site", site.id] })
      qc.invalidateQueries({ queryKey: ["site-type", site.id] })
      qc.invalidateQueries({ queryKey: ["sites"] })
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "That could not be saved."),
  })

  const unknown = site.app_type === "unknown"
  const chosen = opts.data?.chosen ?? false

  return (
    <section className="rounded-xl border border-border bg-card p-4">
      <h2 className="text-sm font-medium text-foreground">What this site is</h2>

      {unknown && !chosen ? (
        <p className="mt-1 text-small text-muted-foreground">
          We could not tell what runs here by looking at the server, so this site has no
          application section. Tell us and it appears.
        </p>
      ) : (
        <p className="mt-1 text-small text-muted-foreground">
          {chosen
            ? "You set this. A scan will not change it back."
            : "Detected by looking at the server. Change it if we got it wrong."}
        </p>
      )}

      {opts.isLoading ? (
        <p className="mt-3 text-small text-muted-foreground">Checking…</p>
      ) : (
        <div className="mt-3 max-w-sm">
          <select
            value={chosen ? site.app_type : ""}
            disabled={save.isPending}
            onChange={(e) => { setError(null); save.mutate(e.target.value) }}
            className="w-full rounded-lg border border-border bg-background px-3 py-2
                       text-small text-foreground"
          >
            <option value="">
              Detect automatically{!chosen && site.app_type !== "unknown"
                ? ` — currently ${site.app_type}` : ""}
            </option>
            {(opts.data?.options ?? []).map((o) => (
              <option key={o.value} value={o.value}>{o.label}</option>
            ))}
          </select>
          {save.isPending && (
            <p className="mt-2 flex items-center gap-1.5 text-caption text-muted-foreground">
              <Loader2 size={12} className="animate-spin" /> Saving…
            </p>
          )}
          <p className="mt-2 text-caption text-muted-foreground">
            Only types ServerAlly has tools for are listed. Choosing one decides which
            application section this site gets and which commands run against it.
            {chosen && " Going back to Detect automatically forgets your answer, so this "
              + "site is Unknown again until the next scan of the server."}
          </p>
        </div>
      )}

      {error && (
        <p className="mt-2 rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                      text-small text-destructive">{error}</p>
      )}
    </section>
  )
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={`truncate text-foreground ${mono ? "font-mono text-caption" : ""}`}>{value}</dd>
    </div>
  )
}

import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { AlertTriangle, Loader2, Replace } from "lucide-react"
import { wpSearchReplace, type WpReplaceResult } from "@/api/sites"
import { Button } from "@/components/ui"

/**
 * Replace one string with another across a WordPress site — what you need when the domain
 * changes.
 *
 * The most dangerous thing on this screen: it rewrites the database in bulk and there is no
 * undo. So the shape of the screen IS the safety.
 *
 * **The real button only exists once a dry run has been seen, and only for the terms that
 * dry run described.** Editing either box afterwards clears the result — a confirmation that
 * no longer describes what is about to happen is worse than no confirmation, because it
 * carries the authority of one.
 */
export default function WpSearchReplace({ siteId }: { siteId: string }) {
  const [search, setSearch] = useState("")
  const [replace, setReplace] = useState("")
  //: What the preview was for. Kept so a later edit can invalidate it.
  const [previewed, setPreviewed] = useState<{ search: string; replace: string } | null>(null)
  const [result, setResult] = useState<WpReplaceResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = useMutation({
    mutationFn: (dry: boolean) => wpSearchReplace(siteId, search, replace, dry),
    onSuccess: (r) => {
      setResult(r)
      setError(null)
      setPreviewed(r.dry_run ? { search, replace } : null)
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      setResult(null)
      setPreviewed(null)
      setError(e.response?.data?.detail ?? "That could not be run.")
    },
  })

  // Edited since the preview? Then the preview no longer describes what would happen.
  const edit = (setter: (v: string) => void) => (v: string) => {
    setter(v)
    setPreviewed(null)
    setResult(null)
  }

  const stale = previewed !== null
    && (previewed.search !== search || previewed.replace !== replace)
  const canCommit = !!previewed && !stale && (result?.total ?? 0) > 0 && !!result?.dry_run

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <Replace size={15} className="text-muted-foreground" />
        <h3 className="text-h3 text-foreground">Search and replace</h3>
      </div>
      <p className="mt-1 text-small text-muted-foreground">
        Change every mention of one thing to another across this site's content and settings
        — what you need after moving to a new domain. Links inside posts, widgets and theme
        options are all covered.
      </p>
      <p className="mt-2 text-caption text-muted-foreground">
        Permanent identifiers on posts are left alone, so feed readers do not re-send your
        whole archive. Other sites sharing this database are never touched.
      </p>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="text-caption text-muted-foreground">Find</span>
          <input value={search} onChange={(e) => edit(setSearch)(e.target.value)}
                 placeholder="http://old-domain.com"
                 className="mt-1 w-full rounded-lg border border-border bg-background px-3
                            py-2 font-mono text-caption text-foreground" />
        </label>
        <label className="block">
          <span className="text-caption text-muted-foreground">Replace with</span>
          <input value={replace} onChange={(e) => edit(setReplace)(e.target.value)}
                 placeholder="https://new-domain.com"
                 className="mt-1 w-full rounded-lg border border-border bg-background px-3
                            py-2 font-mono text-caption text-foreground" />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline"
                disabled={run.isPending || !search.trim() || search === replace}
                onClick={() => { setError(null); run.mutate(true) }}>
          {run.isPending && <Loader2 size={14} className="animate-spin" />}
          Check what would change
        </Button>
        {canCommit && (
          <Button size="sm" variant="danger" disabled={run.isPending}
                  onClick={() => { setError(null); run.mutate(false) }}>
            Replace {result!.total.toLocaleString()}{" "}
            {result!.total === 1 ? "value" : "values"}
          </Button>
        )}
      </div>

      {result && (
        <div className={`mt-3 rounded-lg border-l-2 px-3 py-2.5 ${
          result.dry_run
            ? "border-amber-500 bg-amber-500/5"
            : "border-emerald-500 bg-emerald-500/5"}`}>
          <p className="text-small text-foreground">{result.message}</p>
          {result.changes.length > 0 && (
            <ul className="mt-2 space-y-0.5">
              {result.changes.map((c) => (
                <li key={`${c.table}.${c.column}`}
                    className="text-caption text-muted-foreground">
                  <span className="font-mono">{c.table}</span> · {c.column} —{" "}
                  {c.rows.toLocaleString()} {c.rows === 1 ? "value" : "values"}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {stale && (
        <p className="mt-2 flex items-start gap-1.5 text-caption text-amber-700
                      dark:text-amber-400">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          You changed the words, so check again before replacing.
        </p>
      )}

      {error && (
        <p className="mt-2 rounded-lg border-l-2 border-destructive bg-destructive/5 px-3
                      py-2 text-small text-destructive">{error}</p>
      )}
    </div>
  )
}

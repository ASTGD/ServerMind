import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2, NotebookPen, X } from "lucide-react"
import { listSiteTags, setSiteDetails, type SiteDetail } from "@/api/sites"
import { Button } from "@/components/ui"

/**
 * A note about this site, and how it is grouped — Ploi's "Site notes" and "Project grouping".
 *
 * The only two fields on a site that are purely the customer's own: nothing derives them, so
 * nothing can recover them. That is what makes them worth a database column rather than a
 * file on the server, which a redeploy would take away.
 *
 * **Tags already in use are offered.** Grouping only groups if the spelling matches, and
 * somebody who retypes "acme" as "Acme" has made a second group without noticing. The
 * backend dedupes case-insensitively as a floor; offering the list is what stops it
 * happening at all.
 */
export default function SiteNotes({ site }: { site: SiteDetail }) {
  const qc = useQueryClient()
  const [notes, setNotes] = useState(site.notes ?? "")
  const [tags, setTags] = useState<string[]>(site.tags ?? [])
  const [draft, setDraft] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const { data: known } = useQuery({
    queryKey: ["site-tags"],
    queryFn: listSiteTags,
    staleTime: 60_000,
  })

  const save = useMutation({
    mutationFn: () => setSiteDetails(site.id, { notes, tags }),
    onSuccess: () => {
      setError(null)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      qc.invalidateQueries({ queryKey: ["site", site.id] })
      qc.invalidateQueries({ queryKey: ["site-tags"] })
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      setSaved(false)
      setError(e.response?.data?.detail ?? "That could not be saved.")
    },
  })

  const add = (tag: string) => {
    const clean = tag.trim()
    if (!clean) return
    if (!tags.some((t) => t.toLowerCase() === clean.toLowerCase())) setTags([...tags, clean])
    setDraft("")
    setSaved(false)
  }

  const unused = (known?.tags ?? []).filter(
    (t) => !tags.some((mine) => mine.toLowerCase() === t.toLowerCase()))

  return (
    <section className="rounded-xl border border-border bg-card">
      <header className="flex items-center gap-2 border-b border-border px-4 py-3">
        <NotebookPen size={15} className="text-muted-foreground" />
        <div>
          <h3 className="text-sm font-medium text-foreground">Notes and grouping</h3>
          <p className="text-caption text-muted-foreground">
            Only you see these. They are not read from the server.
          </p>
        </div>
      </header>

      <div className="space-y-3 p-4">
        <label className="block">
          <span className="text-caption text-muted-foreground">Notes</span>
          <textarea
            value={notes}
            onChange={(e) => { setNotes(e.target.value); setSaved(false) }}
            rows={4}
            placeholder="Renews in March · they edit the theme themselves · billing goes to…"
            className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2
                       text-small text-foreground"
          />
        </label>

        <div>
          <span className="text-caption text-muted-foreground">Tags</span>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {tags.map((t) => (
              <span key={t} className="inline-flex items-center gap-1 rounded-full bg-muted
                                       px-2 py-0.5 text-caption text-foreground">
                {t}
                <button type="button" aria-label={`Remove ${t}`}
                        onClick={() => { setTags(tags.filter((x) => x !== t)); setSaved(false) }}
                        className="text-muted-foreground hover:text-foreground">
                  <X size={11} />
                </button>
              </span>
            ))}
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(draft) }
                if (e.key === "Backspace" && !draft && tags.length) setTags(tags.slice(0, -1))
              }}
              onBlur={() => add(draft)}
              placeholder={tags.length ? "" : "client name, retainer…"}
              className="min-w-[140px] flex-1 rounded-lg border border-border bg-background
                         px-2.5 py-1 text-caption text-foreground"
            />
          </div>
          {unused.length > 0 && (
            <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
              <span className="text-caption text-muted-foreground">Already using:</span>
              {unused.slice(0, 10).map((t) => (
                <button key={t} type="button" onClick={() => add(t)}
                        className="rounded-full border border-border px-2 py-0.5
                                   text-caption text-muted-foreground hover:text-foreground">
                  {t}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center gap-3">
          <Button size="sm" disabled={save.isPending} onClick={() => save.mutate()}>
            {save.isPending && <Loader2 size={13} className="animate-spin" />}
            Save
          </Button>
          {saved && (
            <span className="text-caption text-emerald-700 dark:text-emerald-400">Saved</span>
          )}
        </div>

        {error && (
          <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                        text-small text-destructive">{error}</p>
        )}
      </div>
    </section>
  )
}

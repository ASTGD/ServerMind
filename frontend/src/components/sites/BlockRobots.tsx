import { useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { EyeOff, Loader2 } from "lucide-react"

import { getRobots, setRobots } from "@/api/sites"
import { Button } from "@/components/ui"

/**
 * Keep a site out of search engines.
 *
 * A header rather than a robots.txt file, because robots.txt only asks a crawler not to
 * FETCH a page — it does not stop the page being listed. And the state shown here is read
 * from a real request rather than from the config, because what a crawler actually receives
 * is the only thing that decides whether the site gets indexed.
 */
export default function BlockRobots({ siteId }: { siteId: string }) {
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  const q = useQuery({ queryKey: ["robots", siteId], queryFn: () => getRobots(siteId) })
  if (q.isLoading || !q.data?.ok) return null
  const blocked = !!q.data.blocked

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <EyeOff size={15} className="text-muted-foreground" />
        <h3 className="text-h3 text-foreground">Search engines</h3>
      </div>
      <p className="mt-1 text-small text-muted-foreground">
        A staging site or a demo on a temporary address gets crawled and ranked like any
        other — and when the real domain arrives it inherits duplicate content while the
        throwaway URL keeps appearing in results. This asks search engines to leave it alone.
      </p>
      <p className="mt-2 text-caption text-muted-foreground">
        It is a request, not a lock — crawlers choose whether to honour it. Anything that
        must not be seen at all needs a password instead.
      </p>

      <div className="mt-3 flex items-center gap-3">
        <Button size="sm" variant={blocked ? "outline" : "primary"} disabled={busy}
                onClick={() => {
                  setBusy(true); setNote(null)
                  setRobots(siteId, !blocked)
                    .then(async (r) => {
                      await qc.invalidateQueries({ queryKey: ["robots", siteId] })
                      setNote({ ok: true, text: r.message })
                    })
                    .catch((e: { response?: { data?: { detail?: string } } }) =>
                      setNote({ ok: false, text: e.response?.data?.detail ?? "That did not work." }))
                    .finally(() => setBusy(false))
                }}>
          {busy && <Loader2 size={14} className="animate-spin" />}
          {blocked ? "Allow search engines again" : "Keep this site out of search engines"}
        </Button>
        <span className="text-caption text-muted-foreground">
          {blocked ? "Currently hidden" : "Currently indexable"}
        </span>
      </div>

      {note && (
        <p className={`mt-2 rounded-lg border-l-2 px-3 py-2 text-small ${
          note.ok ? "border-emerald-500 bg-emerald-500/5 text-foreground"
                  : "border-destructive bg-destructive/5 text-destructive"}`}>
          {note.text}
        </p>
      )}
    </div>
  )
}

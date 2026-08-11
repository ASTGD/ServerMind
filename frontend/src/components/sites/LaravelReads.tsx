import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Eye, Loader2, ShieldCheck } from "lucide-react"
import { readLaravel, type LaravelRead } from "@/api/sites"
import { Button } from "@/components/ui"
import { cn } from "@/lib/utils"

/**
 * Looking at a Laravel site, as opposed to operating it.
 *
 * Until now this screen offered only the WRITING half — it could run migrations but not show
 * which were pending, restart the queue but not show what had failed. That is backwards for
 * troubleshooting, which is what somebody opens this screen to do.
 *
 * Kept visually apart from the action buttons for the same reason the backend keeps them in
 * separate maps: these change nothing, and someone scanning the screen in a hurry should be
 * able to see which is which without reading labels carefully.
 */
const READS = [
  { key: "about", label: "Overview", blurb: "Versions, environment and drivers" },
  { key: "migrate_status", label: "Migrations", blurb: "What has run, what is waiting" },
  { key: "route_list", label: "Routes", blurb: "Every URL this app answers" },
  { key: "schedule_list", label: "Scheduled work", blurb: "What runs, and when next" },
  { key: "queue_failed", label: "Failed jobs", blurb: "Work the queue could not finish" },
  { key: "env", label: "Environment", blurb: "Which environment it thinks it is" },
]

export default function LaravelReads({ siteId }: { siteId: string }) {
  const [open, setOpen] = useState<string | null>(null)
  const [result, setResult] = useState<LaravelRead | null>(null)
  const [error, setError] = useState<string | null>(null)

  const look = useMutation({
    mutationFn: (which: string) => readLaravel(siteId, which),
    onSuccess: (r) => { setResult(r); setError(null) },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      setResult(null)
      setError(e.response?.data?.detail ?? "That could not be read.")
    },
  })

  const show = (key: string) => {
    setOpen(key)
    setResult(null)
    setError(null)
    look.mutate(key)
  }

  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="flex items-center gap-2 px-4 py-3">
        <Eye size={15} className="text-muted-foreground" />
        <div>
          <p className="text-sm font-medium text-foreground">Have a look</p>
          <p className="text-small text-muted-foreground">
            None of these change anything.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-2 border-t border-border px-4 py-2.5">
        {READS.map((r) => (
          <Button
            key={r.key}
            size="sm"
            variant={open === r.key ? "secondary" : "outline"}
            title={r.blurb}
            disabled={look.isPending}
            onClick={() => show(r.key)}
          >
            {look.isPending && open === r.key && (
              <Loader2 size={13} className="animate-spin" />
            )}
            {r.label}
          </Button>
        ))}
      </div>

      {(look.isPending || result || error) && (
        <div className="border-t border-border px-4 py-3">
          {look.isPending ? (
            <p className="text-small text-muted-foreground">Asking the server…</p>
          ) : error ? (
            <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                          text-small text-destructive">{error}</p>
          ) : result ? (
            <>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="text-small font-medium text-foreground">{result.label}</span>
                {!result.ok && result.reason && (
                  <span className="text-caption text-amber-700 dark:text-amber-400">
                    {result.reason}
                  </span>
                )}
                {!!result.hidden && (
                  // Said out loud rather than done quietly: somebody comparing this with
                  // what they see over SSH should know why the two differ.
                  <span className="inline-flex items-center gap-1 rounded-full bg-muted
                                   px-2 py-0.5 text-caption text-muted-foreground">
                    <ShieldCheck size={11} />
                    {result.hidden} secret{result.hidden === 1 ? "" : "s"} hidden
                  </span>
                )}
                {result.trimmed && (
                  <span className="text-caption text-muted-foreground">shortened</span>
                )}
              </div>
              <pre className={cn(
                "max-h-96 overflow-auto rounded-lg bg-slate-950 p-3 text-caption",
                "leading-relaxed text-slate-200",
              )}>
                {result.output || "Nothing to show."}
              </pre>
            </>
          ) : null}
        </div>
      )}
    </div>
  )
}

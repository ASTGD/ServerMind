import { useState } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { AlertTriangle, Loader2, Terminal } from "lucide-react"
import { getAppCommands, runArtisan, type AppCommand } from "@/api/sites"
import { Button } from "@/components/ui"
import { cn } from "@/lib/utils"

/**
 * The rest of the artisan commands, and the customer's own.
 *
 * The panel above this one is curated: it leads with the two or three things that are
 * actually wrong and the buttons that fix them. This is the long tail — Ploi's grid — kept
 * behind a fold so it does not compete with the part that tells you what to do.
 *
 * **The confirmation is per command and says why.** Four of these destroy or duplicate
 * something a customer would miss; the rest clear a cache. Asking about all of them equally
 * is how people learn to click through the question.
 */
export default function LaravelCommands({ siteId, onRan }: {
  siteId: string
  onRan?: () => void
}) {
  const [custom, setCustom] = useState("")
  const [output, setOutput] = useState<{ ok: boolean; text: string; hidden: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [asked, setAsked] = useState<AppCommand | null>(null)

  const { data } = useQuery({
    queryKey: ["app-commands", siteId],
    queryFn: () => getAppCommands(siteId),
    staleTime: Infinity,      // a static list; refetching it says nothing new
  })

  const run = useMutation({
    mutationFn: (cmd: string) => runArtisan(siteId, cmd),
    onSuccess: (r) => {
      setOutput({ ok: r.ok, text: r.output, hidden: r.hidden })
      setError(null)
      onRan?.()
    },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      setOutput(null)
      setError(e.response?.data?.detail ?? "That command could not be run.")
    },
  })

  if (!data?.groups.length) return null

  return (
    <details className="rounded-xl border border-border bg-card">
      <summary className="flex cursor-pointer items-center gap-2 px-4 py-3 text-sm
                          font-medium text-foreground">
        <Terminal size={15} className="text-muted-foreground" />
        All commands
      </summary>

      <div className="space-y-4 border-t border-border p-4">
        {data.groups.map((g) => (
          <div key={g.name}>
            <p className="text-caption uppercase tracking-wide text-muted-foreground">
              {g.name}
            </p>
            <div className="mt-1.5 flex flex-wrap gap-2">
              {g.commands.map((c) => (
                <Button
                  key={c.key}
                  size="sm"
                  variant={c.confirm ? "outline" : "ghost"}
                  title={c.blurb}
                  disabled={run.isPending}
                  onClick={() => (c.confirm ? setAsked(c) : run.mutate(c.key))}
                  className={cn(c.confirm && "border-amber-500/50")}
                >
                  {c.label}
                </Button>
              ))}
            </div>
          </div>
        ))}

        {asked && (
          <div className="rounded-lg border-l-2 border-amber-500 bg-amber-500/5 px-3 py-2.5">
            <p className="flex items-start gap-1.5 text-small text-foreground">
              <AlertTriangle size={13} className="mt-0.5 shrink-0 text-amber-600
                                                  dark:text-amber-400" />
              {asked.blurb}
            </p>
            <div className="mt-2 flex gap-2">
              <Button size="sm" variant="danger"
                      onClick={() => { run.mutate(asked.key); setAsked(null) }}>
                {asked.label}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => setAsked(null)}>Cancel</Button>
            </div>
          </div>
        )}

        {data.custom && (
          <div className="border-t border-border pt-3">
            <p className="text-caption uppercase tracking-wide text-muted-foreground">
              Your own command
            </p>
            <p className="mt-1 text-small text-muted-foreground">
              An application defines its own commands. Type one — for example{" "}
              <span className="font-mono">app:send-invoices</span>.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <input
                value={custom}
                onChange={(e) => { setCustom(e.target.value); setError(null) }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && custom.trim() && !run.isPending) {
                    run.mutate(custom)
                  }
                }}
                spellCheck={false}
                placeholder="app:send-invoices"
                className="min-w-[220px] flex-1 rounded-lg border border-border bg-background
                           px-3 py-2 font-mono text-caption text-foreground"
              />
              <Button size="sm" variant="outline"
                      disabled={run.isPending || !custom.trim()}
                      onClick={() => run.mutate(custom)}>
                {run.isPending && <Loader2 size={13} className="animate-spin" />}
                Run
              </Button>
            </div>
          </div>
        )}

        {error && (
          <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                        text-small text-destructive">{error}</p>
        )}

        {output && (
          <div>
            <div className="mb-1 flex items-center gap-2">
              <span className={cn("text-caption",
                output.ok ? "text-emerald-700 dark:text-emerald-400" : "text-destructive")}>
                {output.ok ? "Finished" : "Reported a failure"}
              </span>
              {output.hidden > 0 && (
                <span className="text-caption text-muted-foreground">
                  {output.hidden} secret{output.hidden === 1 ? "" : "s"} hidden
                </span>
              )}
            </div>
            <pre className="max-h-72 overflow-auto rounded-lg bg-slate-950 p-3 text-caption
                            leading-relaxed text-slate-200">
              {output.text || "It printed nothing."}
            </pre>
          </div>
        )}
      </div>
    </details>
  )
}

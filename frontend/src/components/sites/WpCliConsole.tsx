import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { Loader2, ShieldCheck, TerminalSquare } from "lucide-react"
import { runWpCli } from "@/api/sites"
import { Button } from "@/components/ui"

/** A few that answer a question rather than change something — a starting point, not a menu. */
const EXAMPLES = ["plugin list", "core version", "user list", "option get siteurl",
                  "cache flush", "rewrite flush"]

/**
 * The WP-CLI console — Ploi's WordPress → WP-CLI tab.
 *
 * wp-cli is how WordPress is actually administered from a server, and a plugin brings its own
 * commands, so no fixed list could cover what somebody legitimately needs. What IS bounded is
 * said plainly rather than discovered by being refused: anything that can empty the database
 * or run arbitrary PHP belongs in the terminal, where you can see what you are doing.
 */
export default function WpCliConsole({ siteId }: { siteId: string }) {
  const [command, setCommand] = useState("")
  const [result, setResult] = useState<{ ok: boolean; output: string; hidden: number } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = useMutation({
    mutationFn: (c: string) => runWpCli(siteId, c),
    onSuccess: (r) => { setResult(r); setError(null) },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      setResult(null)
      setError(e.response?.data?.detail ?? "That command could not be run.")
    },
  })

  const go = () => { if (command.trim() && !run.isPending) run.mutate(command) }

  return (
    <details className="rounded-xl border border-border bg-card">
      <summary className="flex cursor-pointer items-center gap-2 px-4 py-3 text-sm
                          font-medium text-foreground">
        <TerminalSquare size={15} className="text-muted-foreground" />
        WP-CLI
      </summary>

      <div className="space-y-3 border-t border-border p-4">
        <p className="text-small text-muted-foreground">
          Run a WordPress command on this site. It runs as the account that owns the files, in
          this site's folder.
        </p>
        <p className="text-caption text-muted-foreground">
          Commands that can empty the database or run arbitrary PHP —{" "}
          <span className="font-mono">db</span>, <span className="font-mono">eval</span>,{" "}
          <span className="font-mono">shell</span> — are not available here. Use the terminal
          for those.
        </p>

        <div className="flex flex-wrap gap-2">
          <div className="flex min-w-[240px] flex-1 items-center gap-1.5 rounded-lg border
                          border-border bg-background px-2.5">
            <span className="font-mono text-caption text-muted-foreground">wp</span>
            <input
              value={command}
              onChange={(e) => { setCommand(e.target.value); setError(null) }}
              onKeyDown={(e) => { if (e.key === "Enter") go() }}
              spellCheck={false}
              placeholder="plugin list"
              className="w-full bg-transparent py-2 font-mono text-caption text-foreground
                         outline-none"
            />
          </div>
          <Button size="sm" variant="outline" disabled={run.isPending || !command.trim()}
                  onClick={go}>
            {run.isPending && <Loader2 size={13} className="animate-spin" />}
            Run
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-caption text-muted-foreground">Try:</span>
          {EXAMPLES.map((e) => (
            <button key={e} type="button" onClick={() => { setCommand(e); setError(null) }}
                    className="rounded-full border border-border px-2 py-0.5 font-mono
                               text-caption text-muted-foreground hover:text-foreground">
              {e}
            </button>
          ))}
        </div>

        {error && (
          <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                        text-small text-destructive">{error}</p>
        )}

        {result && (
          <div>
            <div className="mb-1 flex items-center gap-2">
              <span className={`text-caption ${result.ok
                ? "text-emerald-700 dark:text-emerald-400" : "text-destructive"}`}>
                {result.ok ? "Finished" : "Reported a failure"}
              </span>
              {result.hidden > 0 && (
                <span className="inline-flex items-center gap-1 text-caption
                                 text-muted-foreground">
                  <ShieldCheck size={11} />
                  {result.hidden} secret{result.hidden === 1 ? "" : "s"} hidden
                </span>
              )}
            </div>
            <pre className="max-h-80 overflow-auto rounded-lg bg-slate-950 p-3 text-caption
                            leading-relaxed text-slate-200">
              {result.output || "It printed nothing."}
            </pre>
          </div>
        )}
      </div>
    </details>
  )
}

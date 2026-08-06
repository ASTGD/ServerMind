import { AlertTriangle, CircleCheck, Loader2, Play, RotateCw, Square } from "lucide-react"

import { type WebAppState } from "@/api/sites"
import { Button } from "@/components/ui"
import { cn } from "@/lib/utils"

/**
 * The long-running program behind a domain — Node, Next.js, Python, Go.
 *
 * The status line is deliberately NOT "the service is running", because that answers a
 * different question from the one the customer is asking. A program can be running while
 * the site is down three separate ways, and each of them is stated in plain words at the
 * top rather than left for somebody to infer from a green dot.
 */
export default function AppPanel({ data, onAct, busy }: {
  data: WebAppState
  onAct: (action: string) => void
  busy: string | null
}) {
  const problems = data.problems ?? []
  const worst = problems.find((p) => p.level === "critical")
  const working = problems.length === 0
  const restarts = data.restarts ?? 0

  return (
    <div className="space-y-4">
      {/* The verdict, before any of the numbers that make it up. */}
      <div className={cn(
        "rounded-xl border p-5",
        worst ? "border-destructive/40 bg-destructive/5"
          : working ? "border-emerald-500/40 bg-emerald-500/5"
            : "border-amber-500/40 bg-amber-500/5")}>
        <div className="flex items-center gap-2">
          {working
            ? <CircleCheck size={16} className="text-emerald-600 dark:text-emerald-400" />
            : <AlertTriangle size={16} className={worst ? "text-destructive" : "text-amber-500"} />}
          <h3 className="text-h3 text-foreground">
            {working
              ? `${data.runtime} is running and serving this site`
              : worst ? "This site is not working" : "Running, with something to fix"}
          </h3>
        </div>

        {problems.length > 0 && (
          <ul className="mt-2 space-y-1.5">
            {problems.map((p, i) => (
              <li key={i} className="flex gap-2 text-small text-foreground">
                <span className={cn("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                  p.level === "critical" ? "bg-destructive" : "bg-amber-500")} />
                {p.text}
              </li>
            ))}
          </ul>
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          <Button size="sm" onClick={() => onAct("restart")} disabled={!!busy}>
            {busy === "restart" ? <Loader2 size={14} className="animate-spin" />
              : <RotateCw size={14} />}
            Restart
          </Button>
          {data.active ? (
            <Button size="sm" variant="outline" onClick={() => onAct("stop")} disabled={!!busy}>
              {busy === "stop" ? <Loader2 size={14} className="animate-spin" />
                : <Square size={14} />}
              Stop
            </Button>
          ) : (
            <Button size="sm" variant="outline" onClick={() => onAct("start")} disabled={!!busy}>
              {busy === "start" ? <Loader2 size={14} className="animate-spin" />
                : <Play size={14} />}
              Start
            </Button>
          )}
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card p-5">
        <h3 className="text-h3 text-foreground">How it runs</h3>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-small">
            <tbody className="[&_td]:py-1.5 [&_td:first-child]:whitespace-nowrap
                              [&_td:first-child]:pr-6 [&_td:first-child]:text-muted-foreground">
              <tr><td>Runtime</td><td className="text-foreground">{data.runtime}</td></tr>
              <tr>
                <td>Starts with</td>
                <td className="font-mono text-caption text-foreground">
                  {data.command || "—"}
                </td>
              </tr>
              <tr><td>Runs as</td><td className="text-foreground">{data.user || "—"}</td></tr>
              <tr>
                <td>Folder</td>
                <td className="font-mono text-caption text-foreground">
                  {data.directory || "—"}
                </td>
              </tr>
              <tr>
                <td>Port</td>
                <td className="text-foreground">
                  {data.port || "—"}
                  {data.listening === true && (
                    <span className="ml-2 text-caption text-emerald-600 dark:text-emerald-400">
                      listening
                    </span>
                  )}
                  {data.listening === false && (
                    <span className="ml-2 text-caption text-destructive">nothing listening</span>
                  )}
                  {data.proxy_port && data.proxy_port !== data.port && (
                    <span className="ml-2 text-caption text-destructive">
                      web server forwards to {data.proxy_port}
                    </span>
                  )}
                </td>
              </tr>
              <tr>
                <td>State</td>
                <td className="text-foreground">
                  {data.state}
                  {data.pid && data.pid !== "0" && (
                    <span className="text-muted-foreground"> · pid {data.pid}</span>
                  )}
                  {data.memory_mb != null && (
                    <span className="text-muted-foreground"> · {data.memory_mb} MB</span>
                  )}
                </td>
              </tr>
              <tr>
                <td>Restarts</td>
                <td className={restarts >= 3 ? "text-destructive" : "text-foreground"}>
                  {restarts}
                </td>
              </tr>
              <tr>
                <td>After a reboot</td>
                <td className="text-foreground">
                  {data.enabled ? "starts by itself" : "does NOT start by itself"}
                </td>
              </tr>
              <tr>
                <td>Service</td>
                <td className="font-mono text-caption text-muted-foreground">{data.unit}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Only present when the program is not running — on a healthy service the journal
          is noise, and on a dead one it is the only thing that matters. */}
      {data.log && (
        <div className="rounded-xl border border-border bg-card p-5">
          <h3 className="text-h3 text-foreground">What it said before it stopped</h3>
          <pre className="mt-3 overflow-x-auto rounded-lg bg-slate-950 p-3 text-caption
                          leading-relaxed text-slate-200">{data.log}</pre>
        </div>
      )}
    </div>
  )
}

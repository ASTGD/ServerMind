import { useEffect, useState } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Layers, Loader2 } from "lucide-react"

import { addQueueWorkers, getQueueWorkers } from "@/api/sites"
import { Button } from "@/components/ui"

/**
 * Laravel queue workers.
 *
 * Nine numbers, and the screen's job is to explain what each one costs rather than present
 * a form. The time limit is shown against the connection's own `retry_after`, because those
 * two together decide whether a job is processed once or twice — and being wrong there is
 * silent.
 */
export default function QueueWorkers({ siteId }: { siteId: string }) {
  const qc = useQueryClient()
  const [f, setF] = useState({
    connection: "", queue: "default", processes: 1, timeout: 60,
    sleep: 3, tries: 3, backoff: 0, memory: 128, environment: "",
  })
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)

  const q = useQuery({ queryKey: ["queue", siteId], queryFn: () => getQueueWorkers(siteId) })

  useEffect(() => {
    if (q.data?.ok && !f.connection && q.data.default) {
      setF((v) => ({ ...v, connection: q.data!.default! }))
    }
  }, [q.data, f.connection])

  if (q.isLoading) return null
  if (!q.data?.ok) return null

  const conn = (q.data.connections ?? []).find((c) => c.name === f.connection)
  const retry = conn?.retry_after ?? null
  // The comparison that matters, shown before the button rather than after the refusal.
  const wouldDouble = retry !== null && f.timeout >= retry

  const set = (k: string, v: string | number) => setF((s) => ({ ...s, [k]: v }))
  const num = (k: keyof typeof f, label: string, hint: string) => (
    <label className="block">
      <span className="text-caption text-muted-foreground">{label}</span>
      <input type="number" value={f[k] as number}
             onChange={(e) => set(k, Number(e.target.value))}
             className="mt-1 w-full rounded-lg border border-border bg-background px-2 py-1.5
                        text-small text-foreground" />
      <span className="mt-0.5 block text-[11px] text-muted-foreground">{hint}</span>
    </label>
  )

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <Layers size={15} className="text-muted-foreground" />
        <h3 className="text-h3 text-foreground">Queue workers</h3>
      </div>
      <p className="mt-1 text-small text-muted-foreground">
        A queue worker is what actually sends your emails and does the slow jobs your site
        puts aside. Without one, that work is queued and never happens — and nothing reports
        an error.
      </p>

      {(q.data.workers ?? []).length > 0 && (
        <p className="mt-2 text-caption text-muted-foreground">
          Running now: {(q.data.workers ?? []).map((w) => w.name).join(", ")}
        </p>
      )}

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <label className="block">
          <span className="text-caption text-muted-foreground">Connection</span>
          <select value={f.connection} onChange={(e) => set("connection", e.target.value)}
                  className="mt-1 w-full rounded-lg border border-border bg-background px-2
                             py-1.5 text-small text-foreground">
            {(q.data.connections ?? []).map((c) => (
              <option key={c.name} value={c.name}>
                {c.name}{c.name === q.data!.default ? " (default)" : ""}
              </option>
            ))}
          </select>
          <span className="mt-0.5 block text-[11px] text-muted-foreground">
            {conn?.driver ? `${conn.driver} · ` : ""}
            {retry === null ? "retry time unknown" : `puts a job back after ${retry}s`}
          </span>
        </label>
        <label className="block">
          <span className="text-caption text-muted-foreground">Queue</span>
          <input value={f.queue} onChange={(e) => set("queue", e.target.value)}
                 className="mt-1 w-full rounded-lg border border-border bg-background px-2
                            py-1.5 text-small text-foreground" />
          <span className="mt-0.5 block text-[11px] text-muted-foreground">
            which named queue to work
          </span>
        </label>
        {num("processes", "Processes", "each one is its own service")}
        {num("timeout", "Time limit per job", "seconds a job may run")}
        {num("tries", "Attempts", "0 means for ever — one bad job blocks the rest")}
        {num("backoff", "Wait before retry", "seconds after a failure")}
        {num("sleep", "Idle wait", "seconds to wait when there is no work")}
        {num("memory", "Memory (MB)", "worker exits above this and is restarted")}
        <label className="block">
          <span className="text-caption text-muted-foreground">Environment</span>
          <input value={f.environment} onChange={(e) => set("environment", e.target.value)}
                 placeholder="(the app's own)"
                 className="mt-1 w-full rounded-lg border border-border bg-background px-2
                            py-1.5 text-small text-foreground" />
        </label>
      </div>

      {wouldDouble && (
        <div className="mt-3 rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2">
          <p className="flex items-center gap-1.5 text-small font-medium text-destructive">
            <AlertTriangle size={14} /> This would run some jobs twice
          </p>
          <p className="mt-1 text-caption text-foreground">
            A job may run for {f.timeout}s, but this connection puts a job back on the queue
            after {retry}s — so a job still running would be handed to a second worker and
            done twice. Charging a customer twice, or sending the same email twice, with
            nothing reporting an error. Set the time limit below {retry}s.
          </p>
        </div>
      )}

      <div className="mt-3">
        <Button size="sm" disabled={busy || wouldDouble || !f.connection}
                onClick={() => {
                  setBusy(true); setNote(null)
                  addQueueWorkers(siteId, f)
                    .then(async (r) => {
                      await qc.invalidateQueries({ queryKey: ["queue", siteId] })
                      setNote({ ok: true, text: r.message })
                    })
                    .catch((e: { response?: { data?: { detail?: string } } }) =>
                      setNote({ ok: false, text: e.response?.data?.detail ?? "That did not work." }))
                    .finally(() => setBusy(false))
                }}>
          {busy && <Loader2 size={14} className="animate-spin" />}
          Create worker{f.processes > 1 ? "s" : ""}
        </Button>
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

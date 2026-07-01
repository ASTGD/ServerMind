import { useEffect, useRef, useState } from "react"
import { useWebSocket } from "@/hooks/useWebSocket"
import { useAuthStore } from "@/store/authStore"
import {
  X, Loader2, Layers, CheckCircle2, XCircle, ShieldAlert, MinusCircle, Clock, AlertTriangle,
} from "lucide-react"
import type { BatchSpec } from "./ChatMessage"

type SrvStatus = "queued" | "running" | "success" | "failed" | "blocked" | "skipped" | "stalled"

interface Row {
  serverId: string
  serverName: string
  status: SrvStatus
  explanation?: string
}

function StatusIcon({ status }: { status: SrvStatus }) {
  switch (status) {
    case "running": return <Loader2 size={15} className="animate-spin text-indigo-500" />
    case "success": return <CheckCircle2 size={15} className="text-green-500" />
    case "failed": return <XCircle size={15} className="text-destructive" />
    case "blocked": return <ShieldAlert size={15} className="text-amber-500" />
    case "stalled": return <AlertTriangle size={15} className="text-amber-500" />
    case "skipped": return <MinusCircle size={15} className="text-muted-foreground" />
    default: return <Clock size={15} className="text-muted-foreground/50" />
  }
}

/** Runs one action across several servers, streaming per-server status from /ws/batch.
 *  Opening the modal + the reviewed batch card is the approval; hard-blocked commands
 *  are still refused per server. */
export default function BatchRunModal({ batch, onClose }: { batch: BatchSpec; onClose: () => void }) {
  const language = useAuthStore((s) => s.user?.preferred_language) ?? "en"
  const [rows, setRows] = useState<Row[]>(() =>
    batch.targets.map((t) => ({ serverId: t.serverId, serverName: t.serverName, status: "queued" as SrvStatus })),
  )
  const [done, setDone] = useState(false)
  const startedRef = useRef(false)

  const { send, status } = useWebSocket("/ws/batch", {
    onMessage: (raw) => {
      const m = raw as Record<string, unknown>
      switch (m.type) {
        case "server_start":
          setRows((r) => r.map((x) => (x.serverId === m.server_id ? { ...x, status: "running" } : x)))
          break
        case "server_done":
          setRows((r) =>
            r.map((x) =>
              x.serverId === m.server_id
                ? { ...x, status: m.status as SrvStatus, explanation: m.explanation as string }
                : x,
            ),
          )
          break
        case "batch_complete":
        case "error":
          setDone(true)
          break
      }
    },
  })

  useEffect(() => {
    if (status === "open" && !startedRef.current) {
      startedRef.current = true
      send({ type: "run", server_ids: batch.targets.map((t) => t.serverId), prompt: batch.prompt, language })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])

  const finished = rows.filter((r) => r.status !== "queued" && r.status !== "running").length

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-start gap-2.5 border-b border-border px-5 py-4">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500 text-white">
            <Layers size={16} />
          </div>
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold text-foreground">Batch action</h2>
            <p className="truncate text-xs text-muted-foreground">{batch.prompt}</p>
          </div>
          <span className="shrink-0 text-xs text-muted-foreground">
            {finished}/{rows.length}
          </span>
          <button onClick={onClose} aria-label="Close" className="shrink-0 text-muted-foreground hover:text-foreground">
            <X size={18} />
          </button>
        </div>

        {/* Per-server rows */}
        <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
          {rows.map((r) => (
            <div key={r.serverId} className="flex items-start gap-2.5 rounded-lg px-2 py-2">
              <StatusIcon status={r.status} />
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">{r.serverName}</p>
                {r.explanation ? (
                  <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{r.explanation}</p>
                ) : (
                  <p className="mt-0.5 text-xs capitalize text-muted-foreground/70">{r.status}</p>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border px-5 py-3">
          <p className="text-xs text-muted-foreground">
            {done ? "Finished." : status === "open" ? "Running…" : "Connecting…"}
          </p>
          <button
            onClick={onClose}
            className="rounded-lg bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
          >
            {done ? "Done" : "Close"}
          </button>
        </div>
      </div>
    </div>
  )
}

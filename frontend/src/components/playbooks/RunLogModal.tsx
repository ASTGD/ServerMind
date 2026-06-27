import { useState, useRef, useEffect } from "react"
import { X, Square, Loader2, CheckCircle2, XCircle, Clock, Ban, TerminalSquare } from "lucide-react"
import { wsAuthQuery } from "@/api/auth"
import { cancelPlaybookRun } from "@/api/playbooks"

/** WebSocket base derived from the page origin (works on localhost + LAN). */
function wsBase(): string {
  const configured = import.meta.env.VITE_WS_URL as string | undefined
  if (configured) return configured
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    return `${proto}//${window.location.host}`
  }
  return "ws://localhost:8888"
}
const WS_BASE = wsBase()

type State = "connecting" | "running" | "success" | "failed" | "stalled" | "cancelled"

interface Props {
  serverId: string
  runId: string
  title: string
  serverName: string
  onClose: () => void
}

/** Read-only live log for an install already running on a server — opens a
 * WebSocket, rejoins the run, and streams its output (Update 17, Phase 3). */
export default function RunLogModal({ serverId, runId, title, serverName, onClose }: Props) {
  const [state, setState] = useState<State>("connecting")
  const [lines, setLines] = useState<string[]>(["⟳ Connecting to the running install…"])
  const wsRef = useRef<WebSocket | null>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const finishedRef = useRef(false)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [lines])

  useEffect(() => {
    void (async () => {
      const q = await wsAuthQuery()
      const ws = new WebSocket(`${WS_BASE}/ws/playbook-run/${serverId}?${q}`)
      wsRef.current = ws
      ws.onopen = () => ws.send(JSON.stringify({ type: "attach", run_id: runId }))
      ws.onmessage = (e: MessageEvent<string>) => {
        const msg = JSON.parse(e.data) as { type: string; [k: string]: unknown }
        if (msg.type === "started") {
          setState("running")
          setLines([])
        } else if (msg.type === "output") {
          setLines((p) => [...p, (msg.data as string).replace(/\n$/, "")])
        } else if (msg.type === "complete") {
          finishedRef.current = true
          const st = msg.status as string
          setState(
            st === "success" ? "success"
              : st === "cancelled" ? "cancelled"
                : st === "stalled" ? "stalled"
                  : "failed"
          )
          ws.close()
        } else if (msg.type === "error") {
          finishedRef.current = true
          setState("failed")
          setLines((p) => [...p, `ERROR: ${msg.message as string}`])
          ws.close()
        }
      }
      ws.onclose = () => {
        if (!finishedRef.current) setState((s) => (s === "running" || s === "connecting" ? "failed" : s))
      }
    })()
    return () => wsRef.current?.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverId, runId])

  async function handleStop() {
    setLines((p) => [...p, "⏹ Cancelling…"])
    try {
      await cancelPlaybookRun(runId)
    } catch {
      /* the stream resolves when the run ends */
    }
  }

  const statusBadge = {
    connecting: <span className="flex items-center gap-1.5 text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Connecting</span>,
    running: <span className="flex items-center gap-1.5 text-primary"><Loader2 className="h-3.5 w-3.5 animate-spin" /> Running</span>,
    success: <span className="flex items-center gap-1.5 text-green-500"><CheckCircle2 className="h-3.5 w-3.5" /> Completed</span>,
    failed: <span className="flex items-center gap-1.5 text-red-500"><XCircle className="h-3.5 w-3.5" /> Failed</span>,
    stalled: <span className="flex items-center gap-1.5 text-orange-500"><Clock className="h-3.5 w-3.5" /> Stopped responding</span>,
    cancelled: <span className="flex items-center gap-1.5 text-amber-500"><Ban className="h-3.5 w-3.5" /> Cancelled</span>,
  }[state]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="min-w-0">
            <h2 className="truncate font-semibold text-foreground">{title}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">on {serverName}</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3 overflow-y-auto px-6 py-4">
          <div className="text-xs font-medium">{statusBadge}</div>
          <div className="overflow-hidden rounded-lg border border-border">
            <div className="flex items-center gap-2 border-b border-border bg-muted/60 px-3 py-2">
              <TerminalSquare className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="font-mono text-xs text-muted-foreground">live log · run {runId.slice(0, 8)}</span>
            </div>
            <div className="h-80 space-y-0.5 overflow-y-auto bg-black/80 p-3 font-mono text-xs text-green-400">
              {lines.map((line, i) => (
                <div key={i} className="whitespace-pre-wrap break-all leading-relaxed">{line || " "}</div>
              ))}
              <div ref={endRef} />
            </div>
          </div>
        </div>

        <div className="flex justify-end gap-3 border-t border-border px-6 py-4">
          {state === "running" || state === "connecting" ? (
            <button
              onClick={handleStop}
              className="flex items-center gap-2 rounded-lg bg-red-500/90 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-red-500"
            >
              <Square className="h-4 w-4" />
              Stop
            </button>
          ) : null}
          <button
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted/50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}

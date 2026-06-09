import { useState, useRef, useEffect, useCallback } from "react"
import { X, Play, CheckCircle2, XCircle, Loader2 } from "lucide-react"
import type { PlaybookDetail, Server } from "@/types"
import { useAuthStore } from "@/store/authStore"

const WS_URL = import.meta.env.VITE_WS_URL as string

interface Props {
  playbook: PlaybookDetail
  servers: Server[]
  onClose: () => void
  /** When true, sends user_script_id instead of playbook_id to the WS handler */
  isUserScript?: boolean
}

type RunState = "idle" | "running" | "success" | "failed"

export default function RunPlaybookModal({ playbook, servers, onClose, isUserScript = false }: Props) {
  const token = useAuthStore((s) => s.token)
  const [serverId, setServerId] = useState<string>(servers[0]?.id ?? "")
  const [vars, setVars] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {}
    for (const v of playbook.variables ?? []) {
      init[v.name] = v.default ?? ""
    }
    return init
  })
  const [runState, setRunState] = useState<RunState>("idle")
  const [outputLines, setOutputLines] = useState<string[]>([])
  const [runId, setRunId] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const outputEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    outputEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [outputLines])

  useEffect(() => {
    return () => {
      wsRef.current?.close()
    }
  }, [])

  const handleRun = useCallback(() => {
    if (!serverId || !token) return
    const missingRequired = (playbook.variables ?? []).filter(
      (v) => v.required && !vars[v.name]?.trim()
    )
    if (missingRequired.length > 0) {
      alert(`Required: ${missingRequired.map((v) => v.label).join(", ")}`)
      return
    }

    setRunState("running")
    setOutputLines([])

    const ws = new WebSocket(`${WS_URL}/ws/playbook-run/${serverId}?token=${token}`)
    wsRef.current = ws

    ws.onopen = () => {
      ws.send(
        JSON.stringify({
          type: "run",
          ...(isUserScript
            ? { user_script_id: playbook.id }
            : { playbook_id: playbook.id }),
          variables: vars,
        })
      )
    }

    ws.onmessage = (e: MessageEvent<string>) => {
      const msg = JSON.parse(e.data) as { type: string; [k: string]: unknown }
      if (msg.type === "started") {
        setRunId(msg.run_id as string)
      } else if (msg.type === "output") {
        setOutputLines((prev) => [...prev, (msg.data as string).trimEnd()])
      } else if (msg.type === "complete") {
        const status = msg.status as string
        setRunState(status === "success" ? "success" : "failed")
        ws.close()
      } else if (msg.type === "error") {
        setOutputLines((prev) => [...prev, `ERROR: ${msg.message as string}`])
        setRunState("failed")
        ws.close()
      }
    }

    ws.onerror = () => {
      setOutputLines((prev) => [...prev, "WebSocket connection error"])
      setRunState("failed")
    }

    ws.onclose = () => {
      if (runState === "running") setRunState("failed")
    }
  }, [serverId, token, playbook, vars, runState])

  const canRun = runState === "idle" || runState === "success" || runState === "failed"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div>
            <h2 className="font-semibold text-foreground">{playbook.title}</h2>
            <p className="text-xs text-muted-foreground mt-0.5">Run playbook on a server</p>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="overflow-y-auto flex-1 p-6 space-y-5">
          {/* Server selector */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-1.5">
              Target Server
            </label>
            <select
              value={serverId}
              onChange={(e) => setServerId(e.target.value)}
              disabled={!canRun}
              className="w-full rounded-lg border border-border bg-background text-foreground text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-50"
            >
              {servers.length === 0 && (
                <option value="">No servers available</option>
              )}
              {servers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.host}) — {s.os_type ?? s.connection_type}
                </option>
              ))}
            </select>
          </div>

          {/* Variables */}
          {(playbook.variables ?? []).length > 0 && (
            <div>
              <label className="block text-sm font-medium text-foreground mb-3">
                Variables
              </label>
              <div className="space-y-3">
                {(playbook.variables ?? []).map((v) => (
                  <div key={v.name}>
                    <label className="block text-xs text-muted-foreground mb-1">
                      {v.label}
                      {v.required && <span className="text-red-400 ml-1">*</span>}
                    </label>
                    <input
                      type="text"
                      value={vars[v.name] ?? ""}
                      onChange={(e) =>
                        setVars((prev) => ({ ...prev, [v.name]: e.target.value }))
                      }
                      disabled={!canRun}
                      placeholder={v.default || v.label}
                      className="w-full rounded-lg border border-border bg-background text-foreground text-sm px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-50 placeholder:text-muted-foreground/50"
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Output */}
          {outputLines.length > 0 && (
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="text-sm font-medium text-foreground">Output</span>
                {runId && (
                  <span className="text-xs text-muted-foreground">Run {runId.slice(0, 8)}</span>
                )}
              </div>
              <div className="rounded-lg border border-border bg-black/60 font-mono text-xs text-green-400 p-3 max-h-56 overflow-y-auto space-y-0.5">
                {outputLines.map((line, i) => (
                  <div key={i} className="leading-relaxed whitespace-pre-wrap break-all">
                    {line}
                  </div>
                ))}
                {runState === "running" && (
                  <div className="flex items-center gap-1 text-muted-foreground mt-1">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    <span>Running...</span>
                  </div>
                )}
                <div ref={outputEndRef} />
              </div>
            </div>
          )}

          {/* Status */}
          {runState === "success" && (
            <div className="flex items-center gap-2 rounded-lg border border-green-500/20 bg-green-500/10 px-4 py-3 text-sm text-green-400">
              <CheckCircle2 className="h-4 w-4" />
              Playbook completed successfully
            </div>
          )}
          {runState === "failed" && (
            <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              <XCircle className="h-4 w-4" />
              Playbook failed — check the output above
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-border">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm text-muted-foreground hover:text-foreground border border-border hover:bg-muted/50 transition-colors"
          >
            Close
          </button>
          {canRun && (
            <button
              onClick={handleRun}
              disabled={!serverId || runState === "running"}
              className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              {runState === "running" ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Running...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  {runState === "idle" ? "Run Playbook" : "Run Again"}
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

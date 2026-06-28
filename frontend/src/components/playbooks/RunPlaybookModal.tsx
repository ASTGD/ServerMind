import { useState, useRef, useEffect, useCallback } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  X, Play, CheckCircle2, XCircle, Loader2, TerminalSquare,
  ExternalLink, Copy, Check, Eye, EyeOff, PartyPopper, Square, Ban, Clock,
} from "lucide-react"
import type { PlaybookAccessInfo, PlaybookDetail, Server } from "@/types"
import { useAuthStore } from "@/store/authStore"
import { wsAuthQuery } from "@/api/auth"
import { cancelPlaybookRun, runMulti, type FleetRun, type FleetSkip } from "@/api/playbooks"
import { getActiveRuns, getAllActiveRuns } from "@/api/servers"
import BatchRunModal from "./BatchRunModal"
import { failureRemedy } from "@/lib/preflightRemedy"

/**
 * WebSocket base URL — derived from the page origin so the modal works from
 * localhost AND any LAN device without rebuilding (the Vite dev server / nginx
 * proxy forwards /ws to the backend). Falls back to VITE_WS_URL if explicitly set.
 */
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
const MAX_RECONNECTS = 5

/** Format a number of seconds as m:ss. */
function fmt(sec: number): string {
  const s = Math.max(0, Math.floor(sec))
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}:${r.toString().padStart(2, "0")}`
}

/**
 * Fill {{HOST}} and {{VAR}} placeholders in an access-info template using the
 * server host and the variables the user just entered. Runs entirely
 * client-side — passwords come from the form and never round-trip the backend.
 */
function resolveAccess(
  tpl: PlaybookAccessInfo | null | undefined,
  vars: Record<string, string>,
  host: string | undefined,
): PlaybookAccessInfo | null {
  if (!tpl) return null
  const fill = (s?: string): string | undefined => {
    if (!s) return s
    let out = s.replace(/\{\{HOST\}\}/g, host ?? "")
    for (const [k, v] of Object.entries(vars)) {
      out = out.split(`{{${k}}}`).join(v)
    }
    return out
  }
  return {
    name: tpl.name,
    url: fill(tpl.url),
    username: fill(tpl.username),
    password: fill(tpl.password),
    note: fill(tpl.note),
  }
}

/** Small button that copies text to the clipboard with brief visual feedback. */
function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      aria-label={`Copy ${label}`}
      onClick={() => {
        void navigator.clipboard?.writeText(value)
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      }}
      className="shrink-0 text-muted-foreground hover:text-foreground transition-colors p-1"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  )
}

/** "Service is ready" card shown after a successful install that exposes a UI. */
function AccessCard({ access }: { access: PlaybookAccessInfo }) {
  const [showPass, setShowPass] = useState(false)
  return (
    <div className="rounded-lg border border-green-500/30 bg-green-500/5 p-4 space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <PartyPopper className="h-4 w-4 text-green-500" />
        {access.name ? `${access.name} is ready` : "Your service is ready"}
      </div>

      {access.url && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground w-20 shrink-0">URL</span>
          <a
            href={access.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-sm text-primary hover:underline font-mono break-all"
          >
            {access.url}
            <ExternalLink className="h-3 w-3 shrink-0" />
          </a>
          <CopyButton value={access.url} label="URL" />
        </div>
      )}

      {access.username && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground w-20 shrink-0">Username</span>
          <span className="text-sm text-foreground font-mono break-all flex-1">{access.username}</span>
          <CopyButton value={access.username} label="username" />
        </div>
      )}

      {access.password && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground w-20 shrink-0">Password</span>
          <span className="text-sm text-foreground font-mono break-all flex-1">
            {showPass ? access.password : "•".repeat(Math.min(12, access.password.length))}
          </span>
          <button
            type="button"
            aria-label={showPass ? "Hide password" : "Show password"}
            onClick={() => setShowPass((v) => !v)}
            className="shrink-0 text-muted-foreground hover:text-foreground transition-colors p-1"
          >
            {showPass ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
          <CopyButton value={access.password} label="password" />
        </div>
      )}

      {access.note && (
        <p className="text-xs text-muted-foreground leading-relaxed pt-1">{access.note}</p>
      )}
    </div>
  )
}

interface Props {
  playbook: PlaybookDetail
  servers: Server[]
  onClose: () => void
  /** When true, sends user_script_id instead of playbook_id to the WS handler */
  isUserScript?: boolean
}

type RunState = "idle" | "running" | "success" | "failed" | "cancelled" | "stalled"

export default function RunPlaybookModal({ playbook, servers, onClose, isUserScript = false }: Props) {
  const token = useAuthStore((s) => s.token)
  const [selectedIds, setSelectedIds] = useState<string[]>(servers[0] ? [servers[0].id] : [])
  // Which servers already have THIS playbook/script running — so the picker shows
  // "Installing now" and we never start a duplicate install (Update 19 #2).
  const { data: allActive = [] } = useQuery({
    queryKey: ["all-active-runs"],
    queryFn: getAllActiveRuns,
    refetchInterval: 5000,
  })
  const busyServerIds = new Set(
    allActive
      .filter((r) => (isUserScript ? r.user_script_id === playbook.id : r.playbook_id === playbook.id))
      .map((r) => r.server_id),
  )
  // Single-run targets the first selected server that isn't already busy.
  const serverId = (selectedIds.find((id) => !busyServerIds.has(id)) ?? selectedIds[0]) ?? ""
  const selectableCount = selectedIds.filter((id) => !busyServerIds.has(id)).length
  const [batchRuns, setBatchRuns] = useState<FleetRun[] | null>(null)
  const [batchSkipped, setBatchSkipped] = useState<FleetSkip[]>([])
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
  const [elapsed, setElapsed] = useState(0)

  const wsRef = useRef<WebSocket | null>(null)
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const startRef = useRef<number>(0)
  // Tracks whether the run reached a terminal state, so a normal socket close
  // doesn't get mislabelled as a failure.
  const finishedRef = useRef(false)
  const runIdRef = useRef<string | null>(null)
  const runStateRef = useRef<RunState>("idle")
  const attemptsRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const rejoinedRef = useRef(false)
  const outputEndRef = useRef<HTMLDivElement>(null)

  const estimate = playbook.est_runtime_sec ?? 60
  const selectedServer = servers.find((s) => s.id === serverId)
  const resolvedAccess = resolveAccess(playbook.access_info, vars, selectedServer?.host)

  // ETA progress: time-based estimate (we can't know a script's true % done).
  // Climbs toward the estimate but caps at 95% until the run actually completes.
  const progress =
    runState === "success" || runState === "failed" || runState === "cancelled" || runState === "stalled"
      ? 100
      : runState === "running"
        ? Math.min(95, (elapsed / estimate) * 100)
        : 0

  useEffect(() => {
    outputEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [outputLines])

  useEffect(() => {
    runStateRef.current = runState
  }, [runState])

  const stopTick = useCallback(() => {
    if (tickRef.current) {
      clearInterval(tickRef.current)
      tickRef.current = null
    }
  }, [])

  useEffect(() => {
    return () => {
      stopTick()
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
    }
  }, [stopTick])

  const connect = useCallback(
    async (mode: "run" | "attach") => {
      const q = await wsAuthQuery()
      const ws = new WebSocket(`${WS_BASE}/ws/playbook-run/${serverId}?${q}`)
      wsRef.current = ws

      ws.onopen = () => {
        if (mode === "run") {
          ws.send(
            JSON.stringify({
              type: "run",
              ...(isUserScript ? { user_script_id: playbook.id } : { playbook_id: playbook.id }),
              variables: vars,
            })
          )
        } else {
          ws.send(JSON.stringify({ type: "attach", run_id: runIdRef.current }))
        }
      }

      ws.onmessage = (e: MessageEvent<string>) => {
        const msg = JSON.parse(e.data) as { type: string; [k: string]: unknown }
        if (msg.type === "started") {
          runIdRef.current = msg.run_id as string
          setRunId(msg.run_id as string)
          startRef.current = Date.now()
          if (mode === "attach") {
            // Reconnected — the server replays the run from the start; show fresh.
            setOutputLines(["⟳ Reconnected — resuming output…"])
          } else {
            setOutputLines((prev) => [
              ...prev,
              `▶ Installation started — streaming live output (est. ~${fmt(estimate)})`,
              "",
            ])
          }
        } else if (msg.type === "output") {
          setOutputLines((prev) => [...prev, (msg.data as string).replace(/\n$/, "")])
        } else if (msg.type === "complete") {
          finishedRef.current = true
          if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
          stopTick()
          const st = msg.status as string
          setRunState(
            st === "success" ? "success"
              : st === "cancelled" ? "cancelled"
                : st === "stalled" ? "stalled"
                  : "failed"
          )
          ws.close()
        } else if (msg.type === "error") {
          finishedRef.current = true
          if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
          stopTick()
          setOutputLines((prev) => [...prev, `ERROR: ${msg.message as string}`])
          setRunState("failed")
          ws.close()
        }
      }

      // onerror is always followed by onclose — let onclose decide reconnect/fail.
      ws.onerror = () => {}

      ws.onclose = () => {
        if (finishedRef.current) return
        // Unexpected drop mid-run: transparently reconnect and re-attach by run_id
        // so a Wi-Fi/LAN blip doesn't lose a long install (the worker runs on).
        if (
          runStateRef.current === "running" &&
          runIdRef.current &&
          attemptsRef.current < MAX_RECONNECTS
        ) {
          attemptsRef.current += 1
          setOutputLines((prev) => [
            ...prev,
            `⟳ Connection lost — reconnecting (${attemptsRef.current}/${MAX_RECONNECTS})…`,
          ])
          reconnectTimerRef.current = setTimeout(() => {
            void connect("attach")
          }, 1500)
        } else {
          stopTick()
          setRunState((s) => (s === "running" ? "failed" : s))
        }
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [serverId, isUserScript, playbook, vars, estimate, stopTick]
  )

  function toggleServer(id: string) {
    if (busyServerIds.has(id)) return // can't queue a duplicate on a busy server
    // Fleet install is for official playbooks; user scripts stay single-server.
    if (isUserScript) {
      setSelectedIds([id])
      return
    }
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  const handleRun = useCallback(async () => {
    const targets = selectedIds.filter((id) => !busyServerIds.has(id))
    if (targets.length === 0 || !token) return
    const missingRequired = (playbook.variables ?? []).filter(
      (v) => v.required && !vars[v.name]?.trim()
    )
    if (missingRequired.length > 0) {
      alert(`Required: ${missingRequired.map((v) => v.label).join(", ")}`)
      return
    }

    // Fleet install — 2+ servers each run as an independent background install.
    if (!isUserScript && targets.length >= 2) {
      if (targets.length > 10 && !confirm(`Run "${playbook.title}" on ${targets.length} servers at once?`)) {
        return
      }
      try {
        const { runs, skipped } = await runMulti(playbook.id, targets, vars)
        setBatchRuns(runs)
        setBatchSkipped(skipped)
      } catch {
        alert("Couldn't start the fleet install — make sure the background worker is running.")
      }
      return
    }

    finishedRef.current = false
    attemptsRef.current = 0
    runIdRef.current = null
    setRunState("running")
    setRunId(null)
    setElapsed(0)
    startRef.current = Date.now()
    // Immediate confirmation — the log window appears at once with this line.
    setOutputLines([`▶ Connecting to ${selectedServer?.name ?? "server"}…`])

    // Tick elapsed time every second to drive the ETA bar.
    stopTick()
    tickRef.current = setInterval(() => {
      setElapsed((Date.now() - startRef.current) / 1000)
    }, 1000)

    await connect("run")
  }, [selectedIds, busyServerIds, isUserScript, token, playbook, vars, selectedServer, stopTick, connect])

  const handleCancel = useCallback(async () => {
    const rid = runIdRef.current
    if (!rid) return
    setOutputLines((prev) => [...prev, "⏹ Cancelling…"])
    try {
      await cancelPlaybookRun(rid)
    } catch {
      setOutputLines((prev) => [...prev, "ERROR: could not cancel the run"])
    }
  }, [])

  // Rejoin an install already running on this server for this playbook — so closing
  // and reopening the window resumes the live run instead of showing a fresh screen
  // (and prevents starting a duplicate). Update 17, Phase 1.
  useEffect(() => {
    if (!serverId || runStateRef.current !== "idle" || rejoinedRef.current) return
    let cancelled = false
    getActiveRuns(serverId)
      .then((runs) => {
        if (cancelled || rejoinedRef.current) return
        const match = runs.find((r) =>
          isUserScript ? r.user_script_id === playbook.id : r.playbook_id === playbook.id
        )
        if (!match) return
        rejoinedRef.current = true
        finishedRef.current = false
        attemptsRef.current = 0
        runIdRef.current = match.id
        setRunId(match.id)
        setRunState("running")
        setOutputLines(["⟳ Rejoining the install already running on this server…"])
        startRef.current = match.started_at ? new Date(match.started_at).getTime() : Date.now()
        stopTick()
        tickRef.current = setInterval(() => {
          setElapsed((Date.now() - startRef.current) / 1000)
        }, 1000)
        void connect("attach")
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverId, isUserScript, playbook.id])

  const canRun =
    runState === "idle" || runState === "success" || runState === "failed" ||
    runState === "cancelled" || runState === "stalled"
  const showConsole = runState !== "idle"

  // The most meaningful error line for the failure banner — scripts/preflight use
  // ">>> ERROR: <reason>". Skip the generic exit-code line.
  const failureReason = (() => {
    if (runState !== "failed") return null
    for (let i = outputLines.length - 1; i >= 0; i--) {
      const m = outputLines[i].trim().match(/^>{0,3}\s*ERROR:\s*(.+)$/i)
      if (m && !/command exited with status/i.test(m[1])) return m[1]
    }
    return null
  })()

  if (batchRuns) {
    return (
      <BatchRunModal
        runs={batchRuns}
        skipped={batchSkipped}
        playbookTitle={playbook.title}
        onClose={onClose}
      />
    )
  }

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
          {/* Server selector — multi-select for fleet installs (playbooks only) */}
          <div>
            <label className="block text-sm font-medium text-foreground mb-1.5">
              {isUserScript ? "Target Server" : "Target Server(s)"}
            </label>
            {servers.length === 0 ? (
              <p className="rounded-lg border border-border bg-background px-3 py-2 text-sm text-muted-foreground">
                No servers available
              </p>
            ) : (
              <div className="max-h-44 space-y-1 overflow-y-auto rounded-lg border border-border p-1.5">
                {servers.map((s) => {
                  const busy = busyServerIds.has(s.id)
                  const checked = selectedIds.includes(s.id) && !busy
                  return (
                    <label
                      key={s.id}
                      title={busy ? `${playbook.title} is already running on ${s.name}` : undefined}
                      className={`flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm transition-colors ${busy ? "cursor-not-allowed opacity-70" : "cursor-pointer"} ${checked ? "bg-primary/10" : busy ? "" : "hover:bg-accent"} ${!canRun ? "pointer-events-none opacity-50" : ""}`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={!canRun || busy}
                        onChange={() => toggleServer(s.id)}
                        className="h-4 w-4 rounded border-border accent-primary"
                      />
                      <span className="truncate font-medium text-foreground">{s.name}</span>
                      <span className="truncate text-xs text-muted-foreground">{s.host}</span>
                      {busy && (
                        <span className="ml-auto flex shrink-0 items-center gap-1 rounded-md bg-amber-500/10 px-1.5 py-0.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">
                          <Loader2 size={11} className="animate-spin" />
                          Installing now
                        </span>
                      )}
                    </label>
                  )
                })}
              </div>
            )}
            {!isUserScript && servers.length > 1 && (
              <p className="mt-1.5 text-xs text-muted-foreground">
                {selectableCount > 1
                  ? `${selectableCount} servers selected — the same install runs on each in the background.`
                  : "Tip: tick more than one server to install across your fleet at once."}
              </p>
            )}
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

          {/* Progress bar + ETA */}
          {showConsole && (
            <div>
              <div className="flex items-center justify-between mb-1.5 text-xs">
                <span className="font-medium text-foreground">
                  {runState === "running" && "Installing…"}
                  {runState === "success" && "Completed"}
                  {runState === "failed" && "Failed"}
                  {runState === "cancelled" && "Cancelled"}
                  {runState === "stalled" && "Stopped responding"}
                </span>
                <span className="text-muted-foreground tabular-nums">
                  {runState === "running"
                    ? `Elapsed ${fmt(elapsed)} · ETA ~${fmt(estimate - elapsed)}`
                    : `Took ${fmt(elapsed)}`}
                </span>
              </div>
              <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-700 ease-out ${
                    runState === "failed"
                      ? "bg-red-500"
                      : runState === "cancelled"
                        ? "bg-amber-500"
                        : runState === "stalled"
                          ? "bg-orange-500"
                          : runState === "success"
                            ? "bg-green-500"
                            : "bg-primary"
                  }`}
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {/* Live console */}
          {showConsole && (
            <div className="rounded-lg border border-border overflow-hidden">
              {/* Console title bar */}
              <div className="flex items-center gap-2 px-3 py-2 bg-muted/60 border-b border-border">
                <div className="flex gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
                  <span className="h-2.5 w-2.5 rounded-full bg-yellow-400" />
                  <span className="h-2.5 w-2.5 rounded-full bg-green-400" />
                </div>
                <TerminalSquare className="h-3.5 w-3.5 text-muted-foreground ml-1" />
                <span className="text-xs text-muted-foreground font-mono truncate">
                  {selectedServer?.name ?? "server"}
                  {selectedServer?.host ? ` · ${selectedServer.host}` : ""}
                </span>
                {runId && (
                  <span className="text-[10px] text-muted-foreground/70 ml-auto font-mono">
                    run {runId.slice(0, 8)}
                  </span>
                )}
              </div>
              {/* Console body */}
              <div className="bg-black/80 font-mono text-xs text-green-400 p-3 h-72 overflow-y-auto space-y-0.5">
                {outputLines.map((line, i) => (
                  <div key={i} className="leading-relaxed whitespace-pre-wrap break-all">
                    {line || " "}
                  </div>
                ))}
                {runState === "running" && (
                  <div className="flex items-center gap-1.5 text-muted-foreground mt-1">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    <span className="animate-pulse">running…</span>
                  </div>
                )}
                <div ref={outputEndRef} />
              </div>
            </div>
          )}

          {/* Status banners */}
          {runState === "success" &&
          resolvedAccess &&
          (resolvedAccess.url || resolvedAccess.username || resolvedAccess.note) ? (
            <AccessCard access={resolvedAccess} />
          ) : runState === "success" ? (
            <div className="flex items-center gap-2 rounded-lg border border-green-500/20 bg-green-500/10 px-4 py-3 text-sm text-green-400">
              <CheckCircle2 className="h-4 w-4" />
              Playbook completed successfully
            </div>
          ) : null}
          {runState === "failed" && (
            <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm">
              <div className="flex items-start gap-2 text-red-400">
                <XCircle className="h-4 w-4 mt-0.5 shrink-0" />
                <span>{failureReason ?? "Playbook failed — check the output above."}</span>
              </div>
              {failureRemedy(failureReason) && (
                <p className="mt-2 pl-6 text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">What to do:</span> {failureRemedy(failureReason)}
                </p>
              )}
            </div>
          )}
          {runState === "cancelled" && (
            <div className="flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-400">
              <Ban className="h-4 w-4" />
              Run cancelled
            </div>
          )}
          {runState === "stalled" && (
            <div className="flex items-start gap-2 rounded-lg border border-orange-500/20 bg-orange-500/10 px-4 py-3 text-sm text-orange-400">
              <Clock className="h-4 w-4 mt-0.5 shrink-0" />
              <span>
                Stopped responding — it likely paused to ask a question we couldn't answer.
                Nothing was broken. Try again, or open the Terminal to run it by hand.
              </span>
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
          {runState === "running" ? (
            <button
              onClick={handleCancel}
              className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium bg-red-500/90 text-white hover:bg-red-500 transition-colors"
            >
              <Square className="h-4 w-4" />
              Stop
            </button>
          ) : (
            <button
              onClick={handleRun}
              disabled={selectableCount === 0}
              className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50"
            >
              <Play className="h-4 w-4" />
              {selectableCount >= 2
                ? `Run on ${selectableCount} servers`
                : runState === "idle" ? "Run Playbook" : "Run Again"}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

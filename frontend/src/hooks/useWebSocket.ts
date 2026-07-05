import { useEffect, useRef, useCallback, useState } from "react"
import { wsAuthQuery } from "@/api/auth"

export type WSStatus = "connecting" | "open" | "reconnecting" | "closed" | "error"

interface Options {
  onMessage: (data: unknown) => void
  /** Called on every successful open. `reconnected` is true when the socket had been
   *  open before and dropped — so the caller can re-attach live work (e.g. a mission). */
  onOpen?: (info: { reconnected: boolean }) => void
  onClose?: () => void
}

/**
 * WebSocket base URL.
 * - If VITE_WS_URL is set (non-empty), use it (e.g. production wss://domain).
 * - Otherwise derive it from the current page origin, so the app works on
 *   localhost, a LAN IP, or any host without rebuilding. The Vite dev server
 *   (and the prod nginx) proxy /ws/* to the backend.
 */
function resolveWsBase(): string {
  const configured = import.meta.env.VITE_WS_URL as string | undefined
  if (configured) return configured
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    return `${proto}//${window.location.host}`
  }
  return "ws://localhost:8000"
}

const WS_BASE = resolveWsBase()
const MAX_BACKOFF_MS = 15_000

/**
 * A resilient WebSocket. A long-lived socket WILL drop — a backend restart/redeploy, an
 * idle proxy timeout, a laptop sleep/wake, a Wi-Fi blip. This hook AUTO-RECONNECTS with
 * capped exponential backoff (surfacing a calm "reconnecting" status) instead of leaving
 * the user on a dead connection that needs a manual page refresh. The conversation lives
 * in the store and missions are durable + detached, so a reconnect restores everything.
 */
export function useWebSocket(path: string, options: Options) {
  const wsRef = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<WSStatus>("connecting")

  // Always call the LATEST callbacks (avoids stale closures and needless reconnects
  // when a caller's handler identity changes between renders).
  const cbRef = useRef(options)
  cbRef.current = options

  useEffect(() => {
    let cancelled = false
    let attempts = 0
    let everOpen = false
    let timer: ReturnType<typeof setTimeout> | null = null

    function scheduleReconnect() {
      if (cancelled) return
      setStatus(everOpen ? "reconnecting" : "connecting")
      const delay = Math.min(MAX_BACKOFF_MS, 500 * 2 ** attempts) + Math.random() * 400
      attempts += 1
      timer = setTimeout(connect, delay)
    }

    async function connect() {
      if (cancelled) return
      setStatus(everOpen ? "reconnecting" : "connecting")
      // A fresh single-use ticket per connection (so the JWT never rides in the URL).
      // If the backend is down, this throws — retry with backoff rather than giving up.
      let q: string
      try {
        q = await wsAuthQuery()
      } catch {
        scheduleReconnect()
        return
      }
      if (cancelled) return

      const ws = new WebSocket(`${WS_BASE}${path}?${q}`)
      wsRef.current = ws

      ws.onopen = () => {
        const reconnected = everOpen
        everOpen = true
        attempts = 0
        setStatus("open")
        cbRef.current.onOpen?.({ reconnected })
      }
      ws.onmessage = (event) => {
        try {
          cbRef.current.onMessage(JSON.parse(event.data as string))
        } catch {
          cbRef.current.onMessage(event.data)
        }
      }
      ws.onclose = () => {
        cbRef.current.onClose?.()
        scheduleReconnect()
      }
      ws.onerror = () => {
        // Some browsers fire onerror without onclose — close to force the reconnect path.
        try {
          ws.close()
        } catch {
          /* noop */
        }
      }
    }

    connect()

    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
      const ws = wsRef.current
      wsRef.current = null
      if (ws) {
        ws.onclose = null // intentional close (unmount / path change) — don't reconnect
        ws.close()
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path])

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  const sendRaw = useCallback((data: string | ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data)
    }
  }, [])

  return { send, sendRaw, status, ws: wsRef }
}

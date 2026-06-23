import { useEffect, useRef, useCallback, useState } from "react"
import { useAuthStore } from "@/store/authStore"

export type WSStatus = "connecting" | "open" | "closed" | "error"

interface Options {
  onMessage: (data: unknown) => void
  onOpen?: () => void
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

export function useWebSocket(path: string, options: Options) {
  const { onMessage, onOpen, onClose } = options
  const token = useAuthStore.getState().token
  const wsRef = useRef<WebSocket | null>(null)
  const [status, setStatus] = useState<WSStatus>("connecting")

  useEffect(() => {
    const url = `${WS_BASE}${path}?token=${token ?? ""}`
    const ws = new WebSocket(url)
    wsRef.current = ws
    setStatus("connecting")

    ws.onopen = () => {
      setStatus("open")
      onOpen?.()
    }

    ws.onmessage = (event) => {
      try {
        onMessage(JSON.parse(event.data as string))
      } catch {
        onMessage(event.data)
      }
    }

    ws.onclose = () => {
      setStatus("closed")
      onClose?.()
    }

    ws.onerror = () => {
      setStatus("error")
    }

    return () => {
      ws.close()
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

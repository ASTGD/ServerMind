import { useEffect, useRef, useCallback, useState } from "react"
import { useAuthStore } from "@/store/authStore"

export type WSStatus = "connecting" | "open" | "closed" | "error"

interface Options {
  onMessage: (data: unknown) => void
  onOpen?: () => void
  onClose?: () => void
}

const WS_BASE = (import.meta.env.VITE_WS_URL ?? "ws://localhost:8000") as string

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

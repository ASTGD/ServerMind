import { useEffect, useRef, forwardRef, useImperativeHandle } from "react"
import { Terminal } from "xterm"
import { FitAddon } from "@xterm/addon-fit"
import { WebLinksAddon } from "@xterm/addon-web-links"
import { wsAuthQuery } from "@/api/auth"

import "xterm/css/xterm.css"

type ConnStatus = "connecting" | "connected" | "disconnected" | "error"

interface Props {
  serverId: string
  /** Stable session id — reconnects re-attach to the same server-side shell. */
  sid: string
  onStatusChange?: (status: ConnStatus) => void
  /** Throttled activity signal (user input or output) — powers the idle timeout. */
  onActivity?: () => void
}

export interface XTerminalHandle {
  /** The last `maxLines` of terminal text (scrollback + viewport) — for "Hand to Ally". */
  getRecentOutput: (maxLines?: number) => string
  /** Re-fit to the container — call when the terminal becomes visible/resized. */
  fit: () => void
}

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

const XTerminal = forwardRef<XTerminalHandle, Props>(function XTerminal({ serverId, sid, onStatusChange, onActivity }, ref) {
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<Terminal | null>(null)
  const fitRef = useRef<FitAddon | null>(null)

  useImperativeHandle(
    ref,
    () => ({
      getRecentOutput(maxLines = 40) {
        const term = termRef.current
        if (!term) return ""
        const buf = term.buffer.active
        const total = buf.length
        const lines: string[] = []
        for (let i = Math.max(0, total - maxLines); i < total; i++) {
          lines.push(buf.getLine(i)?.translateToString(true) ?? "")
        }
        return lines.join("\n").replace(/^\s+|\s+$/g, "")
      },
      fit() {
        try { fitRef.current?.fit() } catch { /* container not visible yet */ }
      },
    }),
    [],
  )

  useEffect(() => {
    if (!containerRef.current) return

    const terminal = new Terminal({
      theme: {
        background: "#0d0d0d",
        foreground: "#d4d4d4",
        cursor: "#d4d4d4",
        selectionBackground: "#3d3d3d",
        black: "#1e1e1e",
        brightBlack: "#6b6b6b",
        red: "#f44747",
        brightRed: "#f44747",
        green: "#4ec9b0",
        brightGreen: "#4ec9b0",
        yellow: "#d7ba7d",
        brightYellow: "#d7ba7d",
        blue: "#569cd6",
        brightBlue: "#569cd6",
        magenta: "#c586c0",
        brightMagenta: "#c586c0",
        cyan: "#9cdcfe",
        brightCyan: "#9cdcfe",
        white: "#d4d4d4",
        brightWhite: "#ffffff",
      },
      fontFamily: '"Cascadia Code", "JetBrains Mono", "Fira Code", monospace',
      fontSize: 14,
      lineHeight: 1.4,
      cursorBlink: true,
      scrollback: 5000,
    })

    const fitAddon = new FitAddon()
    fitRef.current = fitAddon
    const linksAddon = new WebLinksAddon()
    terminal.loadAddon(fitAddon)
    terminal.loadAddon(linksAddon)
    terminal.open(containerRef.current)
    fitAddon.fit()
    termRef.current = terminal

    let lastReport = 0
    const reportActivity = () => {
      const now = Date.now()
      if (now - lastReport > 10_000) {
        lastReport = now
        onActivity?.()
      }
    }

    // WebSocket — reconnects on an unexpected drop and re-attaches to the same
    // server-side shell (same sid), which replays its buffer (a "reset" control frame
    // clears the screen first, then the scrollback is streamed back).
    let ws: WebSocket | null = null
    let disposed = false
    let attempts = 0
    let reconnectTimer: number | undefined
    const MAX_RECONNECT = 5

    function connect() {
      if (disposed) return
      onStatusChange?.("connecting")
      void (async () => {
        const q = await wsAuthQuery()
        if (disposed) return
        const sock = new WebSocket(`${WS_BASE}/ws/terminal/${serverId}?${q}&sid=${encodeURIComponent(sid)}`)
        sock.binaryType = "arraybuffer"
        ws = sock

        sock.onopen = () => {
          attempts = 0
          onStatusChange?.("connected")
          sock.send(JSON.stringify({ type: "resize", cols: terminal.cols, rows: terminal.rows }))
        }
        sock.onmessage = (e) => {
          reportActivity()
          if (typeof e.data === "string") {
            try {
              const m = JSON.parse(e.data)
              if (m.type === "reset") { terminal.reset(); return }
              if (m.type === "error") { terminal.write(`\r\n\x1b[1;31m${m.message}\x1b[0m\r\n`); return }
            } catch { /* plain text — write as-is */ }
            terminal.write(e.data)
            return
          }
          terminal.write(new Uint8Array(e.data as ArrayBuffer))
        }
        sock.onclose = () => {
          if (disposed || ws !== sock) return
          if (attempts < MAX_RECONNECT) {
            attempts += 1
            onStatusChange?.("connecting")
            reconnectTimer = window.setTimeout(connect, Math.min(1000 * 2 ** (attempts - 1), 8000))
          } else {
            onStatusChange?.("disconnected")
            terminal.write("\r\n\x1b[1;33m⚠ disconnected — reopen the tab to reconnect\x1b[0m\r\n")
          }
        }
        sock.onerror = () => { /* onclose drives reconnect */ }
      })()
    }
    connect()

    // Keyboard input → SSH
    terminal.onData((data) => {
      reportActivity()
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data }))
      }
    })

    // Resize → SSH PTY
    terminal.onResize(({ cols, rows }) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols, rows }))
      }
    })

    // Handle container resize
    const observer = new ResizeObserver(() => {
      try { fitAddon.fit() } catch { /* ignore */ }
    })
    observer.observe(containerRef.current)

    return () => {
      disposed = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      observer.disconnect()
      // Tell the backend to end the shell now (tab closed / logout) — not a network drop.
      try { ws?.send(JSON.stringify({ type: "close" })) } catch { /* ignore */ }
      ws?.close()
      terminal.dispose()
      termRef.current = null
    }
  }, [serverId, sid])

  return <div ref={containerRef} className="h-full w-full" />
})

export default XTerminal

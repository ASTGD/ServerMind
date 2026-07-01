import { useEffect, useRef, forwardRef, useImperativeHandle } from "react"
import { Terminal } from "xterm"
import { FitAddon } from "@xterm/addon-fit"
import { WebLinksAddon } from "@xterm/addon-web-links"
import { wsAuthQuery } from "@/api/auth"

import "xterm/css/xterm.css"

type ConnStatus = "connecting" | "connected" | "disconnected" | "error"

interface Props {
  serverId: string
  onStatusChange?: (status: ConnStatus) => void
}

export interface XTerminalHandle {
  /** The last `maxLines` of terminal text (scrollback + viewport) — for "Hand to AI". */
  getRecentOutput: (maxLines?: number) => string
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

const XTerminal = forwardRef<XTerminalHandle, Props>(function XTerminal({ serverId, onStatusChange }, ref) {
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<Terminal | null>(null)

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
    const linksAddon = new WebLinksAddon()
    terminal.loadAddon(fitAddon)
    terminal.loadAddon(linksAddon)
    terminal.open(containerRef.current)
    fitAddon.fit()
    termRef.current = terminal

    // WebSocket connection — fetch a single-use ticket first so the JWT stays
    // out of the URL (falls back to the token if unavailable).
    let ws: WebSocket | null = null
    let disposed = false
    onStatusChange?.("connecting")
    void (async () => {
      const q = await wsAuthQuery()
      if (disposed) return
      ws = new WebSocket(`${WS_BASE}/ws/terminal/${serverId}?${q}`)
      ws.binaryType = "arraybuffer"

      ws.onopen = () => {
        onStatusChange?.("connected")
        ws?.send(JSON.stringify({ type: "resize", cols: terminal.cols, rows: terminal.rows }))
      }
      ws.onmessage = (e) => {
        if (e.data instanceof ArrayBuffer) {
          terminal.write(new Uint8Array(e.data))
        } else {
          terminal.write(e.data as string)
        }
      }
      ws.onclose = () => {
        onStatusChange?.("disconnected")
        terminal.write("\r\n\x1b[38;5;240m─── session ended ───\x1b[0m\r\n")
      }
      ws.onerror = () => {
        onStatusChange?.("error")
        terminal.write("\r\n\x1b[1;31m✗ connection error\x1b[0m\r\n")
      }
    })()

    // Keyboard input → SSH
    terminal.onData((data) => {
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
      observer.disconnect()
      ws?.close()
      terminal.dispose()
      termRef.current = null
    }
  }, [serverId])

  return <div ref={containerRef} className="h-full w-full" />
})

export default XTerminal

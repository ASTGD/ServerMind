import { useEffect, useRef } from "react"
import { Terminal } from "xterm"
import { FitAddon } from "@xterm/addon-fit"
import { WebLinksAddon } from "@xterm/addon-web-links"
import { useAuthStore } from "@/store/authStore"

import "xterm/css/xterm.css"

interface Props {
  serverId: string
}

const WS_BASE = (import.meta.env.VITE_WS_URL ?? "ws://localhost:8000") as string

export default function XTerminal({ serverId }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const token = useAuthStore.getState().token ?? ""

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
      fontSize: 13,
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

    // WebSocket connection
    const ws = new WebSocket(`${WS_BASE}/ws/terminal/${serverId}?token=${token}`)
    ws.binaryType = "arraybuffer"

    ws.onopen = () => {
      terminal.write("\x1b[1;32m✓ Connected\x1b[0m\r\n")
      // Send initial size
      ws.send(JSON.stringify({ type: "resize", cols: terminal.cols, rows: terminal.rows }))
    }

    ws.onmessage = (e) => {
      if (e.data instanceof ArrayBuffer) {
        terminal.write(new Uint8Array(e.data))
      } else {
        terminal.write(e.data as string)
      }
    }

    ws.onclose = () => {
      terminal.write("\r\n\x1b[1;33m⚠ Connection closed\x1b[0m\r\n")
    }

    ws.onerror = () => {
      terminal.write("\r\n\x1b[1;31m✗ Connection error\x1b[0m\r\n")
    }

    // Keyboard input → SSH
    terminal.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data }))
      }
    })

    // Resize → SSH PTY
    terminal.onResize(({ cols, rows }) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols, rows }))
      }
    })

    // Handle container resize
    const observer = new ResizeObserver(() => {
      try { fitAddon.fit() } catch { /* ignore */ }
    })
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      ws.close()
      terminal.dispose()
    }
  }, [serverId])

  return (
    <div
      ref={containerRef}
      className="h-full w-full overflow-hidden rounded-lg bg-[#0d0d0d]"
    />
  )
}

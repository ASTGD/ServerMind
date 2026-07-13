import { useEffect, useRef, useState } from "react"
import Guacamole from "guacamole-common-js"
import { Loader2 } from "lucide-react"

/** WebSocket base — same derivation as useWebSocket (origin-relative so it works on
 *  localhost/LAN/prod; Vite dev + prod nginx proxy /ws/* to the backend). */
const WS_BASE = (() => {
  const configured = import.meta.env.VITE_WS_URL as string | undefined
  if (configured) return configured
  if (typeof window !== "undefined") {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    return `${proto}//${window.location.host}`
  }
  return "ws://localhost:8000"
})()

// Guacamole.Client.State: 3 = CONNECTED, 5 = DISCONNECTED.
const CONNECTED = 3
const DISCONNECTED = 5

type ViewState = "connecting" | "connected" | "closed" | "error"

/**
 * The live Remote Desktop canvas (Assets Phase E). Mounts a guacamole-common-js client
 * over our /ws/rdp tunnel (which resolves the RDP credentials server-side and bridges to
 * guacd). Renders the desktop, scales it to fit, and forwards mouse + keyboard. The session
 * token authorizes the tunnel; no credentials are ever held here.
 */
export default function RdpCanvas({ token, onError }: { token: string; onError?: (msg: string) => void }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<ViewState>("connecting")
  const [errMsg, setErrMsg] = useState<string | null>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const width = Math.max(640, Math.min(1920, Math.floor(container.clientWidth) || 1280))
    const height = Math.max(480, Math.round((width * 9) / 16))

    const tunnel = new Guacamole.WebSocketTunnel(`${WS_BASE}/ws/rdp`)
    const client = new Guacamole.Client(tunnel)
    const display = client.getDisplay()
    const displayEl = display.getElement()
    container.appendChild(displayEl)

    // Scale the remote display to fit the container width as it resizes.
    const fit = () => {
      const dw = display.getWidth()
      if (dw > 0 && container.clientWidth > 0) display.scale(container.clientWidth / dw)
    }
    display.onresize = fit

    client.onstatechange = (s: number) => {
      if (s === CONNECTED) { setState("connected"); fit() }
      else if (s === DISCONNECTED) setState((prev) => (prev === "error" ? prev : "closed"))
    }
    client.onerror = (status: Guacamole.Status) => {
      const m = status?.message || "The Remote Desktop connection failed."
      setState("error"); setErrMsg(m); onError?.(m)
    }

    // Input — mouse on the display, keyboard while the canvas is focused (tabindex on the
    // container), so we don't hijack the user's keyboard globally. applyDisplayScale=true
    // maps the on-screen (scaled) coordinates back to the remote resolution.
    const mouse = new Guacamole.Mouse(displayEl)
    mouse.onEach(["mousedown", "mousemove", "mouseup"], (event) => {
      client.sendMouseState((event as Guacamole.Mouse.Event).state, true)
    })

    const keyboard = new Guacamole.Keyboard(container)
    keyboard.onkeydown = (keysym: number) => client.sendKeyEvent(1, keysym)
    keyboard.onkeyup = (keysym: number) => client.sendKeyEvent(0, keysym)

    const onWinResize = () => fit()
    window.addEventListener("resize", onWinResize)

    client.connect(`token=${encodeURIComponent(token)}&width=${width}&height=${height}&dpi=96`)

    return () => {
      window.removeEventListener("resize", onWinResize)
      try { client.disconnect() } catch { /* already closed */ }
      if (displayEl.parentNode === container) container.removeChild(displayEl)
    }
  }, [token, onError])

  return (
    <div className="relative">
      <div
        ref={containerRef}
        tabIndex={0}
        className="flex min-h-[420px] w-full items-center justify-center overflow-hidden rounded-lg border border-border bg-black outline-none focus:ring-2 focus:ring-primary/60"
      />
      {state !== "connected" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-lg bg-black/70 text-sm text-white">
          {state === "connecting" && (<><Loader2 size={18} className="animate-spin" /> Connecting to the desktop…</>)}
          {state === "closed" && <span>Session ended.</span>}
          {state === "error" && <span className="max-w-sm px-4 text-center text-red-300">{errMsg}</span>}
        </div>
      )}
      {state === "connected" && (
        <p className="mt-2 text-center text-xs text-muted-foreground">Click the desktop to type. Session is private and expires automatically.</p>
      )}
    </div>
  )
}

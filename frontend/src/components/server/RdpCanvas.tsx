import { useEffect, useRef, useState } from "react"
import Guacamole from "guacamole-common-js"
import { Loader2, Maximize2, Minimize2 } from "lucide-react"

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
  const wrapperRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [state, setState] = useState<ViewState>("connecting")
  const [errMsg, setErrMsg] = useState<string | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)

  function toggleFullscreen() {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {})
    else wrapperRef.current?.requestFullscreen().catch(() => {})
  }

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const initialW = Math.max(1024, Math.min(1920, Math.floor(container.clientWidth) || 1280))
    const initialH = Math.round((initialW * 9) / 16)

    const tunnel = new Guacamole.WebSocketTunnel(`${WS_BASE}/ws/rdp`)
    const client = new Guacamole.Client(tunnel)
    const display = client.getDisplay()
    const displayEl = display.getElement()
    container.appendChild(displayEl)

    // Scale the (canvas) display to fit the container so it never overflows. With dynamic
    // resize below the remote already renders near the container size, so this is ~1:1.
    const fit = () => {
      const dw = display.getWidth(), dh = display.getHeight()
      const cw = container.clientWidth, ch = container.clientHeight
      if (dw <= 0 || cw <= 0) return
      const scale = ch > 0 ? Math.min(cw / dw, ch / dh) : cw / dw
      display.scale(scale)
    }
    // Ask the REMOTE to re-render at the size we're actually showing — so full-screen is a
    // crisp full-resolution desktop, not an upscaled/zoomed low-res image (needs the
    // display-update resize-method, which the tunnel sets).
    const targetSize = (): [number, number] => {
      if (document.fullscreenElement && window.screen) {
        return [Math.round(window.screen.width), Math.round(window.screen.height)]
      }
      const w = Math.max(1024, Math.min(1920, Math.floor(container.clientWidth) || 1280))
      return [w, Math.round((w * 9) / 16)]
    }
    const resize = () => {
      const [w, h] = targetSize()
      try { client.sendSize(w, h) } catch { /* not connected yet */ }
    }
    display.onresize = fit
    const onFsChange = () => { setIsFullscreen(!!document.fullscreenElement); resize() }
    document.addEventListener("fullscreenchange", onFsChange)

    client.onstatechange = (s: number) => {
      if (s === CONNECTED) { setState("connected"); resize(); fit() }
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

    let resizeTimer: number | undefined
    const onWinResize = () => { window.clearTimeout(resizeTimer); resizeTimer = window.setTimeout(resize, 250) }
    window.addEventListener("resize", onWinResize)

    client.connect(`token=${encodeURIComponent(token)}&width=${initialW}&height=${initialH}&dpi=96`)

    return () => {
      window.clearTimeout(resizeTimer)
      window.removeEventListener("resize", onWinResize)
      document.removeEventListener("fullscreenchange", onFsChange)
      try { client.disconnect() } catch { /* already closed */ }
      if (displayEl.parentNode === container) container.removeChild(displayEl)
    }
  }, [token, onError])

  return (
    <div ref={wrapperRef} className="relative bg-black">
      <div
        ref={containerRef}
        tabIndex={0}
        className={`flex w-full items-center justify-center overflow-hidden rounded-lg border border-border bg-black outline-none focus:ring-2 focus:ring-primary/60 ${isFullscreen ? "h-screen" : "min-h-[420px]"}`}
      />
      {state === "connected" && (
        <button
          onClick={toggleFullscreen}
          title={isFullscreen ? "Exit full screen" : "Full screen"}
          aria-label={isFullscreen ? "Exit full screen" : "Full screen"}
          className="absolute right-2 top-2 rounded-md bg-black/60 p-1.5 text-white/90 transition-colors hover:bg-black/80"
        >
          {isFullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
        </button>
      )}
      {state !== "connected" && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 rounded-lg bg-black/70 text-sm text-white">
          {state === "connecting" && (
            <>
              <Loader2 size={18} className="animate-spin" />
              <span>Connecting to the desktop…</span>
              <span className="text-xs text-white/60">Signing in to Windows can take a few seconds</span>
            </>
          )}
          {state === "closed" && <span>Session ended.</span>}
          {state === "error" && <span className="max-w-sm px-4 text-center text-red-300">{errMsg}</span>}
        </div>
      )}
      {state === "connected" && !isFullscreen && (
        <p className="mt-2 text-center text-xs text-muted-foreground">Click the desktop to type · use the ⤢ button for full screen. Private session.</p>
      )}
    </div>
  )
}

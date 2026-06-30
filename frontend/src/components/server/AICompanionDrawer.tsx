import { useEffect, useState } from "react"
import { X, Sparkles } from "lucide-react"
import ChatWindow from "@/components/chat/ChatWindow"
import ConnectionStatus from "@/components/server/ConnectionStatus"
import type { Server } from "@/types"

/**
 * The AI companion — a docked panel that slides in from the right of the server hub. It
 * lives in the shell so it's available on every tab; the page content reflows beside it on
 * wide screens (overlay on small ones). The chat mounts on first open and stays alive
 * across tab switches, so the conversation persists while you work.
 */
export default function AICompanionDrawer({
  server,
  open,
  onClose,
}: {
  server: Server
  open: boolean
  onClose: () => void
}) {
  // Mount the chat (and its WebSocket) lazily on first open, then keep it alive.
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    if (open) setMounted(true)
  }, [open])

  return (
    <>
      {/* Dimmed backdrop on small screens only (where the drawer overlays full-width). */}
      <div
        onClick={onClose}
        aria-hidden="true"
        className={`fixed inset-0 top-14 z-30 bg-black/30 backdrop-blur-[1px] transition-opacity duration-300 md:hidden ${
          open ? "opacity-100" : "pointer-events-none opacity-0"
        }`}
      />

      <aside
        role="complementary"
        aria-label="AI companion"
        aria-hidden={!open}
        className={`fixed bottom-0 right-0 top-14 z-40 flex w-full flex-col border-l border-border bg-card shadow-2xl transition-transform duration-300 ease-out md:w-[28rem] ${
          open ? "translate-x-0" : "pointer-events-none translate-x-full"
        }`}
      >
        <div className="flex items-center gap-2.5 border-b border-border px-4 py-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Sparkles size={17} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <p className="text-sm font-semibold text-foreground">AI companion</p>
              <ConnectionStatus status={server.status} />
            </div>
            <p className="truncate text-xs text-muted-foreground">
              {server.name} · {server.os_type ?? "Linux"}
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close AI companion"
            className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X size={18} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-hidden">
          {mounted && <ChatWindow serverId={server.id} />}
        </div>
      </aside>
    </>
  )
}

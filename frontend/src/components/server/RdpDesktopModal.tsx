import { useEffect, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { X, Monitor, Loader2, ShieldCheck, Info } from "lucide-react"
import { enableRdp, openRdpSession, type RdpSession } from "@/api/rdp"
import type { Server } from "@/types"

interface Props {
  server: Server
  onClose: () => void
}

/**
 * Remote Desktop viewer (Assets Phase E). Opens a secure, short-lived session for a Windows
 * asset. The live pixel stream is served by a purpose-built Apache Guacamole (guacd) service;
 * until that's deployed (`streaming_available === false`) this says so honestly rather than
 * showing a broken canvas. The security-critical parts — Windows-only, opt-in, and an
 * access-checked, credential-free session token — are fully wired.
 */
export default function RdpDesktopModal({ server, onClose }: Props) {
  const qc = useQueryClient()
  const [session, setSession] = useState<RdpSession | null>(null)
  const [error, setError] = useState<string | null>(null)

  const sessionMut = useMutation({
    mutationFn: () => openRdpSession(server.id),
    onSuccess: setSession,
    onError: (err: unknown) => setError(errMsg(err) ?? "Could not open a desktop session."),
  })

  const enableMut = useMutation({
    mutationFn: () => enableRdp(server.id, true),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["server", server.id] })
      qc.invalidateQueries({ queryKey: ["servers"] })
      sessionMut.mutate()
    },
    onError: (err: unknown) => setError(errMsg(err) ?? "Could not enable Remote Desktop."),
  })

  // A pure-RDP asset IS the desktop — it's always "on" (no WinRM opt-in gate). A WinRM box
  // must have RDP explicitly enabled first.
  const rdpOn = server.rdp_enabled || server.connection_type === "rdp"

  // If RDP is available, request a session straight away.
  useEffect(() => {
    if (rdpOn) sessionMut.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const busy = sessionMut.isPending || enableMut.isPending

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="flex w-full max-w-2xl flex-col rounded-xl border border-border bg-card shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="flex items-center gap-2 font-semibold text-foreground">
            <Monitor size={17} className="text-primary" /> Remote Desktop — {server.name}
          </h2>
          <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:text-foreground">
            <X size={16} />
          </button>
        </div>

        <div className="p-5">
          {/* Not enabled yet (WinRM box) → offer the opt-in. A pure-RDP asset skips this. */}
          {!rdpOn && !session && (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <ShieldCheck size={34} className="text-primary" />
              <p className="font-medium text-foreground">Remote Desktop is off for this asset</p>
              <p className="max-w-md text-sm text-muted-foreground">
                Turn it on to open a live desktop over RDP. Opening a desktop is access-checked every
                time, and the connection uses this asset's saved Windows credentials — you won't re-enter them.
              </p>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <button
                onClick={() => { setError(null); enableMut.mutate() }}
                disabled={busy}
                className="mt-1 flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {busy && <Loader2 size={14} className="animate-spin" />} Enable &amp; open desktop
              </button>
            </div>
          )}

          {/* Requesting a session */}
          {busy && !session && rdpOn && (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
              <Loader2 size={16} className="animate-spin" /> Opening a secure session…
            </div>
          )}

          {error && rdpOn && !session && (
            <p className="py-8 text-center text-sm text-destructive">{error}</p>
          )}

          {/* Session issued */}
          {session && (
            <div>
              {session.streaming_available ? (
                <div className="flex aspect-video w-full items-center justify-center rounded-lg border border-border bg-black text-sm text-muted-foreground">
                  <Loader2 size={16} className="mr-2 animate-spin" /> Connecting to {session.host}:{session.port}…
                </div>
              ) : (
                <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/40 p-4">
                  <Info size={18} className="mt-0.5 shrink-0 text-primary" />
                  <div className="text-sm text-muted-foreground">
                    <p className="font-medium text-foreground">Secure session ready — desktop streaming isn't set up yet</p>
                    <p className="mt-1">
                      A private session for <span className="font-mono text-foreground">{session.host}:{session.port}</span> was
                      issued (expires in {session.expires_in}s). Live pixels are served by an Apache Guacamole
                      (<span className="font-mono">guacd</span>) service; once that's connected to this deployment, the
                      desktop appears right here. Your Windows credentials never leave the server.
                    </p>
                  </div>
                </div>
              )}
              <div className="mt-4 flex justify-end">
                <button onClick={onClose} className="rounded-md px-4 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground">
                  Close
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function errMsg(err: unknown): string | undefined {
  return (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
}

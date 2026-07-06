import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { Cpu, AlertTriangle, TerminalSquare, MonitorPlay } from "lucide-react"
import type { Server } from "@/types"
import { categoryForServer } from "@/lib/assetCategories"
import { useTerminalStore } from "@/store/terminalStore"
import ConnectionStatus from "./ConnectionStatus"

interface Props {
  server: Server
  /** Windows assets ask the parent to open the Remote Desktop viewer (a shared modal). */
  onOpenDesktop?: (server: Server) => void
}

/** A single managed machine (Bare Metal / VPS / Windows) — one card = one box. Carries a
 *  category icon, status, OS, an optional cloud-provenance badge, and a quick connect action
 *  (SSH terminal for Linux, Open desktop for Windows). */
export default function MachineCard({ server, onOpenDesktop }: Props) {
  const [showMsg, setShowMsg] = useState(false)
  const navigate = useNavigate()
  const openSession = useTerminalStore((s) => s.openSession)
  const cat = categoryForServer(server)
  const CatIcon = cat.icon
  // Imported cloud instances carry their provider as the first tag (e.g. "aws").
  const provider = server.cloud_account_id ? server.tags?.[0] : undefined
  const otherTags = provider ? server.tags?.filter((t) => t !== provider) : server.tags

  function connect(e: React.MouseEvent) {
    e.preventDefault()
    e.stopPropagation()
    if (server.connection_type === "winrm") {
      onOpenDesktop?.(server)
    } else {
      openSession(server)
      navigate("/terminal")
    }
  }

  return (
    <Link
      to={`/servers/${server.id}`}
      className="flex flex-col rounded-lg border border-border bg-card p-4 transition-all hover:border-primary/50 hover:shadow-sm"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary" title={cat.label}>
            <CatIcon size={18} />
          </div>
          <div className="min-w-0">
            <p className="truncate font-medium text-foreground">{server.name}</p>
            <p className="truncate text-xs text-muted-foreground">{server.host}:{server.port}</p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {(server.status === "auth_failed" || server.status === "host_changed") && (
            <div className="relative">
              <button
                type="button"
                aria-label="Action needed"
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); setShowMsg((v) => !v) }}
                className="flex h-6 w-6 items-center justify-center rounded-full text-red-500 hover:bg-red-500/10"
              >
                <AlertTriangle size={15} />
              </button>
              {showMsg && (
                <div className="absolute right-0 top-7 z-20 w-60 rounded-lg border border-border bg-card p-3 text-left shadow-lg">
                  <p className="text-xs font-semibold text-foreground">
                    {server.status === "auth_failed" ? "Password may have changed" : "Server identity changed"}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {server.status === "auth_failed"
                      ? "This server is rejecting the saved login. Open it and update the credentials."
                      : "This server's SSH key no longer matches the one we trusted. Open it to review and trust the new key."}
                  </p>
                  <span className="mt-2 inline-block text-xs font-medium text-primary">Open server to fix →</span>
                </div>
              )}
            </div>
          )}
          <ConnectionStatus status={server.status} />
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
        {server.os_type && (
          <span className="flex items-center gap-1">
            <Cpu size={11} />
            {server.os_type}{server.os_version ? ` ${server.os_version}` : ""}
            {server.arch ? ` · ${server.arch}` : ""}
          </span>
        )}
        <span className="rounded bg-muted px-1.5 py-0.5 font-medium">{cat.label}</span>
        {provider && (
          <span className="rounded bg-primary/10 px-1.5 py-0.5 font-medium uppercase text-primary">{provider}</span>
        )}
      </div>

      {otherTags && otherTags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {otherTags.map((tag) => (
            <span key={tag} className="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground">{tag}</span>
          ))}
        </div>
      )}

      {/* Quick action footer */}
      <div className="mt-3 flex items-center justify-end border-t border-border pt-2.5">
        <button
          onClick={connect}
          className="flex items-center gap-1.5 text-xs font-medium text-primary hover:underline"
        >
          {server.connection_type === "winrm" ? (
            <><MonitorPlay size={13} /> Open desktop</>
          ) : (
            <><TerminalSquare size={13} /> Connect</>
          )}
        </button>
      </div>
    </Link>
  )
}

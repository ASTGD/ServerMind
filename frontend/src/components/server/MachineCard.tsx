import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"
import { Cpu, AlertTriangle, TerminalSquare, MonitorPlay, Sparkles } from "lucide-react"
import type { Server } from "@/types"
import { categoryForServer } from "@/lib/assetCategories"
import { cloudBrand } from "@/lib/assetBrands"
import BrandIcon, { osIconSlug, hasBrandIcon } from "./BrandIcon"
import AssetMetrics from "./AssetMetrics"
import { useTerminalStore } from "@/store/terminalStore"
import { useAssistantStore } from "@/store/assistantStore"
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
  const openServer = useAssistantStore((s) => s.openServer)
  const cat = categoryForServer(server)
  const CatIcon = cat.icon
  // A WinRM / Windows-category box is Windows even if OS detection never ran.
  const osSlug = osIconSlug(server.os_type) ?? (cat.id === "windows" || server.connection_type === "winrm" ? "windows" : undefined)
  const osBrand = hasBrandIcon(osSlug)
  // Imported cloud instances carry their provider as the first tag (e.g. "aws").
  const provider = server.cloud_account_id ? server.tags?.[0] : undefined
  const providerBrand = cloudBrand(provider)

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

  function askAlly(e: React.MouseEvent) {
    e.preventDefault()
    e.stopPropagation()
    openServer(server)
  }

  return (
    <Link
      to={`/servers/${server.id}`}
      className="flex aspect-square flex-col rounded-2xl border border-border bg-card p-4 transition-all hover:border-primary/50 hover:shadow-sm"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg ${osBrand ? "border border-border bg-muted/40" : cat.accent}`} title={server.os_type || cat.label}>
            {osBrand ? <BrandIcon slug={osSlug} size={26} /> : <CatIcon size={22} />}
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

      <div className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="flex flex-wrap gap-1.5 text-xs text-muted-foreground">
          {server.os_type && (
            <span className="flex items-center gap-1">
              <Cpu size={11} />
              {server.os_type}{server.os_version ? ` ${server.os_version}` : ""}
              {server.arch ? ` · ${server.arch}` : ""}
            </span>
          )}
          <span className="rounded bg-muted px-1.5 py-0.5 font-medium">{cat.label}</span>
          {provider && (
            <span className={`rounded px-1.5 py-0.5 font-medium ${providerBrand ? providerBrand.badge : "bg-primary/10 uppercase text-primary"}`}>{providerBrand?.name ?? provider}</span>
          )}
        </div>

        <div className="mt-auto pt-3">
          <AssetMetrics server={server} />
        </div>
      </div>

      {/* Launch-pad actions */}
      <div className="flex items-center gap-2 pt-3">
        <button
          onClick={connect}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-border px-2.5 py-2 text-xs font-medium text-foreground transition-colors hover:border-primary/50 hover:bg-primary/5 hover:text-primary"
        >
          {server.connection_type === "winrm" ? (
            <><MonitorPlay size={13} /> Open desktop</>
          ) : (
            <><TerminalSquare size={13} /> Connect</>
          )}
        </button>
        <button
          onClick={askAlly}
          title="Ask Ally about this server"
          aria-label="Ask Ally about this server"
          className="flex shrink-0 items-center justify-center rounded-lg border border-border px-2.5 py-2 text-primary transition-colors hover:border-primary/50 hover:bg-primary/5"
        >
          <Sparkles size={15} />
        </button>
      </div>
    </Link>
  )
}

import { Cloud, ExternalLink, Settings2 } from "lucide-react"
import type { CloudAccount } from "@/api/cloud"
import { cloudBrand } from "@/lib/assetBrands"
import BrandIcon, { providerIconSlug, hasBrandIcon } from "./BrandIcon"

interface Props {
  account: CloudAccount
  /** How many of this account's instances are already imported as assets. */
  importedCount: number
  onManage: (account: CloudAccount) => void
}

/** Each provider's web console — "Open console" launches it in a new tab. */
const CONSOLE_URL: Record<string, string> = {
  aws: "https://console.aws.amazon.com",
  digitalocean: "https://cloud.digitalocean.com",
  hetzner: "https://console.hetzner.cloud",
  gcp: "https://console.cloud.google.com",
  azure: "https://portal.azure.com",
}

/** A connected cloud account (AWS / DigitalOcean / …). It's an *account*, not a machine — the
 *  whole card is BRANDED to the provider (background/border/icon/badge/button in the provider's
 *  color); it shows how many instances you've imported, and its launch actions are Manage
 *  (discover / import / disconnect) and Open console (the provider's site, new tab). */
export default function CloudAccountCard({ account, importedCount, onManage }: Props) {
  const brand = cloudBrand(account.provider)
  const providerSlug = providerIconSlug(account.provider)
  const consoleUrl = CONSOLE_URL[account.provider]
  const cardClass = brand ? brand.card : "border-border bg-card"
  const tileClass = brand ? brand.tile : "bg-violet-500/10 text-violet-600 dark:text-violet-400"
  const badgeClass = brand ? brand.badge : "bg-violet-500/10 text-violet-600 dark:text-violet-400"
  const buttonHover = brand ? brand.button : "hover:border-violet-500/50 hover:bg-violet-500/5 hover:text-violet-600 dark:hover:text-violet-400"
  return (
    <div className={`flex aspect-square flex-col rounded-2xl border p-4 transition-all hover:shadow-sm ${cardClass}`}>
      <div className="flex items-start gap-2">
        <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg ${hasBrandIcon(providerSlug) ? "border border-border bg-background" : tileClass}`} title={brand?.name ?? "Cloud account"}>
          {hasBrandIcon(providerSlug) ? <BrandIcon slug={providerSlug} size={24} /> : <Cloud size={18} />}
        </div>
        <div className="min-w-0">
          <p className="truncate font-medium text-foreground">{account.label}</p>
          <p className="truncate text-xs text-muted-foreground">Connected</p>
        </div>
        <span className={`ml-auto rounded px-1.5 py-0.5 text-xs font-medium ${badgeClass}`}>{brand?.name ?? account.provider}</span>
      </div>

      <div className="mt-3 min-h-0 flex-1 overflow-hidden text-xs text-muted-foreground">
        {importedCount > 0 ? <>{importedCount} {importedCount === 1 ? "instance" : "instances"} imported</> : <>No instances imported yet</>}
      </div>

      <div className="flex items-center justify-between border-t border-border/60 pt-3">
        <button
          onClick={() => onManage(account)}
          className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-primary"
        >
          <Settings2 size={14} /> Manage
        </button>
        {consoleUrl && (
          <button
            onClick={() => window.open(consoleUrl, "_blank", "noopener,noreferrer")}
            title={`Open ${brand?.name ?? account.provider} console`}
            className={`flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors ${buttonHover}`}
          >
            <ExternalLink size={14} /> Console
          </button>
        )}
      </div>
    </div>
  )
}

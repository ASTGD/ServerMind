import { ExternalLink, Cloud, Settings2 } from "lucide-react"
import type { CloudAccount } from "@/api/cloud"
import { cloudBrand } from "@/lib/assetBrands"
import BrandIcon, { providerIconSlug, hasBrandIcon } from "./BrandIcon"

/** Each provider's web console. */
const CONSOLE_URL: Record<string, string> = {
  aws: "https://console.aws.amazon.com",
  digitalocean: "https://cloud.digitalocean.com",
  hetzner: "https://console.hetzner.cloud",
  gcp: "https://console.cloud.google.com",
  azure: "https://portal.azure.com",
}

interface Props {
  account: CloudAccount
  importedCount: number
  onManage: (account: CloudAccount) => void
}

/**
 * A connected cloud account, as a row.
 *
 * Deliberately shaped like an asset row but never pretends to be a machine: an account has
 * no status, no CPU and nothing to open a terminal on. What it has is a provider, a count
 * of instances we adopted from it, and two ways out — manage, or the provider's own console.
 */
export default function CloudAccountRow({ account, importedCount, onManage }: Props) {
  const brand = cloudBrand(account.provider)
  const slug = providerIconSlug(account.provider)
  const console_ = CONSOLE_URL[account.provider]

  return (
    <div className="flex items-center gap-3 border-t border-border px-3 py-2.5 transition-colors first:border-t-0 hover:bg-muted/40">
      <span className="h-2 w-2 shrink-0 rounded-full bg-violet-500" title="Connected" />

      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-muted/40">
        {hasBrandIcon(slug) ? <BrandIcon slug={slug} size={18} /> : <Cloud size={16} />}
      </div>

      <div className="min-w-0 flex-1">
        <p className="truncate text-[14px] font-medium text-foreground">{account.label}</p>
        <p className="truncate text-[11.5px] text-muted-foreground">
          {brand?.name ?? account.provider}
          {" · "}
          {importedCount > 0
            ? `${importedCount} instance${importedCount === 1 ? "" : "s"} imported`
            : "no instances imported yet"}
        </p>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <button
          type="button" onClick={() => onManage(account)}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <Settings2 size={13} /> <span className="hidden lg:inline">Manage</span>
        </button>
        {console_ && (
          <a
            href={console_} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-1 rounded-md px-2 py-1 text-[11.5px] text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <ExternalLink size={13} /> <span className="hidden lg:inline">Console</span>
          </a>
        )}
      </div>
    </div>
  )
}

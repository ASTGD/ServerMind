import { Cloud, ExternalLink, Settings2 } from "lucide-react"
import type { CloudAccount } from "@/api/cloud"

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
 *  card shows the provider + how many instances you've imported, and its launch actions are
 *  Manage (discover / import / disconnect) and Open console (the provider's site, new tab). */
export default function CloudAccountCard({ account, importedCount, onManage }: Props) {
  const consoleUrl = CONSOLE_URL[account.provider]
  return (
    <div className="flex flex-col rounded-lg border border-border bg-card p-4">
      <div className="flex items-start gap-2">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-violet-500/10 text-violet-600 dark:text-violet-400" title="Cloud account">
          <Cloud size={18} />
        </div>
        <div className="min-w-0">
          <p className="truncate font-medium text-foreground">{account.label}</p>
          <p className="truncate text-xs text-muted-foreground">Connected</p>
        </div>
        <span className="ml-auto rounded bg-violet-500/10 px-1.5 py-0.5 text-xs font-medium uppercase text-violet-600 dark:text-violet-400">{account.provider}</span>
      </div>

      <div className="mt-3 text-xs text-muted-foreground">
        {importedCount > 0 ? <>{importedCount} {importedCount === 1 ? "instance" : "instances"} imported</> : <>No instances imported yet</>}
      </div>

      <div className="mt-auto flex items-center justify-end gap-2 pt-3">
        <button
          onClick={() => onManage(account)}
          className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-primary/50 hover:bg-primary/5 hover:text-primary"
        >
          <Settings2 size={13} /> Manage
        </button>
        {consoleUrl && (
          <button
            onClick={() => window.open(consoleUrl, "_blank", "noopener,noreferrer")}
            title={`Open ${account.provider.toUpperCase()} console`}
            className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium text-foreground transition-colors hover:border-violet-500/50 hover:bg-violet-500/5 hover:text-violet-600 dark:hover:text-violet-400"
          >
            <ExternalLink size={13} /> Console
          </button>
        )}
      </div>
    </div>
  )
}

import { Cloud, ArrowUpRight } from "lucide-react"
import type { CloudAccount } from "@/api/cloud"

interface Props {
  account: CloudAccount
  /** How many of this account's instances are already imported as assets. */
  importedCount: number
  onManage: (account: CloudAccount) => void
}

/** A connected cloud account (AWS / DigitalOcean / …). Same card format as the others, but
 *  it's an *account* — it shows the provider + how many instances you've imported, and its
 *  action opens the manage view (discover / import more / disconnect). */
export default function CloudAccountCard({ account, importedCount, onManage }: Props) {
  return (
    <button
      onClick={() => onManage(account)}
      className="flex flex-col rounded-lg border border-border bg-card p-4 text-left transition-all hover:border-primary/50 hover:shadow-sm"
    >
      <div className="flex items-start gap-2">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground" title="Cloud account">
          <Cloud size={18} />
        </div>
        <div className="min-w-0">
          <p className="truncate font-medium text-foreground">{account.label}</p>
          <p className="truncate text-xs text-muted-foreground">Connected</p>
        </div>
        <span className="ml-auto rounded bg-primary/10 px-1.5 py-0.5 text-xs font-medium uppercase text-primary">{account.provider}</span>
      </div>

      <div className="mt-3 text-xs text-muted-foreground">
        {importedCount > 0 ? (
          <>{importedCount} {importedCount === 1 ? "instance" : "instances"} imported</>
        ) : (
          <>No instances imported yet</>
        )}
      </div>

      <div className="mt-3 flex items-center justify-end border-t border-border pt-2.5">
        <span className="flex items-center gap-1.5 text-xs font-medium text-primary">
          <ArrowUpRight size={13} /> Open account
        </span>
      </div>
    </button>
  )
}

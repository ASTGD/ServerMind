import { useEffect } from "react"
import { X, Sparkles, Server, Bot, Bell, HardDriveDownload, Users, LifeBuoy } from "lucide-react"

const FEATURES = [
  { icon: Server, title: "Unlimited servers & hosts", desc: "Manage unlimited Linux, Windows, and hosting accounts." },
  { icon: Bot, title: "Hosted ServerAlly AI", desc: "Use our AI with no API key — unlimited chat and scripts." },
  { icon: Bell, title: "Advanced monitoring & alerts", desc: "Custom thresholds via email, webhook, and Slack." },
  { icon: HardDriveDownload, title: "Automated backups & scheduling", desc: "Set-and-forget backups and recurring tasks." },
  { icon: Users, title: "Team access & roles", desc: "Invite your team with granular per-server permissions." },
  { icon: LifeBuoy, title: "Priority support", desc: "Fast, human help whenever you need it." },
]

/** Describes the ServerAlly Pro plan. Opened from the sidebar's "Upgrade to Pro" row.
 *  The upgrade CTA is a placeholder until the billing/checkout flow is wired up. */
export default function UpgradeModal({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [onClose])

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Upgrade to ServerAlly Pro"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg overflow-hidden rounded-2xl border border-border bg-card shadow-2xl"
      >
        {/* Gradient header */}
        <div className="relative bg-gradient-to-br from-indigo-500 to-violet-600 px-6 py-6 text-white">
          <button
            onClick={onClose}
            aria-label="Close"
            className="absolute right-4 top-4 rounded-lg p-1 text-white/80 transition-colors hover:bg-white/15 hover:text-white"
          >
            <X size={18} />
          </button>
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/15">
              <Sparkles size={20} />
            </span>
            <div>
              <h2 className="text-xl font-semibold">ServerAlly Pro</h2>
              <p className="text-sm text-white/85">Run more servers, automate more, with AI on tap.</p>
            </div>
          </div>
        </div>

        {/* Features */}
        <div className="px-6 py-5">
          <ul className="grid gap-3.5 sm:grid-cols-2">
            {FEATURES.map((f) => (
              <li key={f.title} className="flex items-start gap-2.5">
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
                  <f.icon size={15} />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-foreground">{f.title}</p>
                  <p className="text-xs leading-relaxed text-muted-foreground">{f.desc}</p>
                </div>
              </li>
            ))}
          </ul>

          {/* CTA — checkout lives in the billing system (WHMCS order page) when
              configured; without a URL the button explains how to upgrade. */}
          <div className="mt-6 flex items-center gap-3">
            {import.meta.env.VITE_UPGRADE_URL ? (
              <a
                href={import.meta.env.VITE_UPGRADE_URL as string}
                target="_blank"
                rel="noopener noreferrer"
                className="flex-1 rounded-lg bg-primary py-2.5 text-center text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
              >
                Upgrade to Pro
              </a>
            ) : (
              <button
                title="Upgrades are handled by your provider — contact support to upgrade"
                className="flex-1 cursor-default rounded-lg bg-primary py-2.5 text-sm font-medium text-primary-foreground opacity-90"
              >
                Upgrade to Pro
              </button>
            )}
            <button
              onClick={onClose}
              className="rounded-lg px-4 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              Maybe later
            </button>
          </div>
          <p className="mt-3 text-center text-xs text-muted-foreground">
            Cloud and self-hosted plans · cancel anytime
          </p>
        </div>
      </div>
    </div>
  )
}

import { useState } from "react"
import { ExternalLink, Copy, Check, Eye, EyeOff, PartyPopper } from "lucide-react"
import type { PlaybookAccessInfo } from "@/types"

/** Small button that copies text to the clipboard with brief visual feedback. */
export function CopyButton({ value, label }: { value: string; label: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      aria-label={`Copy ${label}`}
      onClick={() => {
        void navigator.clipboard?.writeText(value)
        setCopied(true)
        setTimeout(() => setCopied(false), 1500)
      }}
      className="shrink-0 text-muted-foreground hover:text-foreground transition-colors p-1"
    >
      {copied ? <Check className="h-3.5 w-3.5 text-green-500" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  )
}

/** "Service is ready" card — shows URL / username / password / note for a service. */
export function AccessCard({ access }: { access: PlaybookAccessInfo }) {
  const [showPass, setShowPass] = useState(false)
  return (
    <div className="rounded-lg border border-green-500/30 bg-green-500/5 p-4 space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
        <PartyPopper className="h-4 w-4 text-green-500" />
        {access.name ? `${access.name} is ready` : "Your service is ready"}
      </div>

      {access.url && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground w-20 shrink-0">URL</span>
          <a
            href={access.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-sm text-primary hover:underline font-mono break-all"
          >
            {access.url}
            <ExternalLink className="h-3 w-3 shrink-0" />
          </a>
          <CopyButton value={access.url} label="URL" />
        </div>
      )}

      {access.username && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground w-20 shrink-0">Username</span>
          <span className="text-sm text-foreground font-mono break-all flex-1">{access.username}</span>
          <CopyButton value={access.username} label="username" />
        </div>
      )}

      {access.password && (
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground w-20 shrink-0">Password</span>
          <span className="text-sm text-foreground font-mono break-all flex-1">
            {showPass ? access.password : "•".repeat(Math.min(12, access.password.length))}
          </span>
          <button
            type="button"
            aria-label={showPass ? "Hide password" : "Show password"}
            onClick={() => setShowPass((v) => !v)}
            className="shrink-0 text-muted-foreground hover:text-foreground transition-colors p-1"
          >
            {showPass ? <EyeOff className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
          </button>
          <CopyButton value={access.password} label="password" />
        </div>
      )}

      {access.note && (
        <p className="text-xs text-muted-foreground leading-relaxed pt-1">{access.note}</p>
      )}
    </div>
  )
}

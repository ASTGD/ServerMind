import { useState } from "react"
import { MailWarning } from "lucide-react"
import { useAuthStore } from "@/store/authStore"
import { resendVerification } from "@/api/auth"

/** A dismissable-by-verifying banner shown while the user's email is unverified. */
export default function VerifyBanner() {
  const user = useAuthStore((s) => s.user)
  const [sent, setSent] = useState(false)
  const [sending, setSending] = useState(false)

  if (!user || user.is_verified) return null

  async function resend() {
    setSending(true)
    try {
      await resendVerification()
      setSent(true)
    } catch {
      /* notification_service silently no-ops without SMTP; nothing actionable here */
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="flex items-center justify-between gap-3 border-b border-amber-500/20 bg-amber-500/10 px-6 py-2 text-sm text-amber-700 dark:text-amber-400">
      <span className="flex items-center gap-2">
        <MailWarning size={15} />
        Please verify your email to unlock adding servers and running commands.
      </span>
      <button
        onClick={resend}
        disabled={sending || sent}
        className="shrink-0 rounded-md border border-amber-500/30 px-3 py-1 text-xs font-medium hover:bg-amber-500/10 disabled:opacity-60"
      >
        {sent ? "Email sent ✓" : sending ? "Sending…" : "Resend email"}
      </button>
    </div>
  )
}

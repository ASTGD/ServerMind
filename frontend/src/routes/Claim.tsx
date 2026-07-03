import { useState } from "react"
import { Link, useNavigate, useSearchParams } from "react-router-dom"
import { Loader2, KeyRound } from "lucide-react"
import Logo from "@/components/brand/Logo"
import { claimAccount } from "@/api/auth"
import { useAuthStore } from "@/store/authStore"

/** Public page hit from a billing welcome email (WHMCS): the customer's account was
 * provisioned when they paid — here they set their first password and are signed in.
 * The link is one-time: claiming invalidates it. */
export default function Claim() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const token = params.get("token") ?? ""

  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (password.length < 8) {
      setError("Password must be at least 8 characters.")
      return
    }
    if (password !== confirm) {
      setError("Passwords don't match.")
      return
    }
    setPending(true)
    try {
      const res = await claimAccount(token, password)
      setAuth(res.user, res.access_token, res.refresh_token)
      navigate("/dashboard", { replace: true })
    } catch (err) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? "Something went wrong — please try again.")
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm space-y-6">
        <div className="flex justify-center">
          <Logo size="lg" />
        </div>
        <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
          <h1 className="flex items-center gap-2 text-lg font-semibold text-foreground">
            <KeyRound size={18} className="text-primary" />
            Welcome — set your password
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Your ServerAlly account is ready. Choose a password to finish setup and sign in.
          </p>

          {!token ? (
            <p className="mt-4 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              This link is missing its token. Please use the link from your welcome email.
            </p>
          ) : (
            <form onSubmit={handleSubmit} className="mt-5 space-y-3">
              <div>
                <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  New password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoFocus
                  minLength={8}
                  required
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
                  Confirm password
                </label>
                <input
                  type="password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  minLength={8}
                  required
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
                />
              </div>
              {error && (
                <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
              )}
              <button
                type="submit"
                disabled={pending}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
              >
                {pending && <Loader2 size={14} className="animate-spin" />}
                Set password & sign in
              </button>
            </form>
          )}
        </div>
        <p className="text-center text-xs text-muted-foreground">
          Already set your password?{" "}
          <Link to="/auth" className="text-primary hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  )
}

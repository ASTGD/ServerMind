import { useEffect, useRef, useState } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { verifyEmail } from "@/api/auth"

type Status = "verifying" | "ok" | "error"

/** Public page hit from the email link: confirms the token, shows the result. */
export default function VerifyEmail() {
  const [params] = useSearchParams()
  const [status, setStatus] = useState<Status>("verifying")
  const ran = useRef(false)

  useEffect(() => {
    if (ran.current) return // guard React 18 StrictMode double-invoke
    ran.current = true
    const token = params.get("token")
    if (!token) {
      setStatus("error")
      return
    }
    verifyEmail(token)
      .then(() => setStatus("ok"))
      .catch(() => setStatus("error"))
  }, [params])

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm rounded-xl border border-border bg-card p-6 text-center">
        {status === "verifying" && (
          <p className="text-sm text-muted-foreground">Verifying your email…</p>
        )}
        {status === "ok" && (
          <>
            <h2 className="text-lg font-semibold text-foreground">Email verified ✓</h2>
            <p className="mt-1 text-sm text-muted-foreground">Your account is now active.</p>
            <Link
              to="/dashboard"
              className="mt-4 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              Go to dashboard
            </Link>
          </>
        )}
        {status === "error" && (
          <>
            <h2 className="text-lg font-semibold text-foreground">Verification failed</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              This link is invalid or expired. Sign in and resend the email from the banner.
            </p>
            <Link
              to="/auth"
              className="mt-4 inline-block rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
            >
              Sign in
            </Link>
          </>
        )}
      </div>
    </div>
  )
}

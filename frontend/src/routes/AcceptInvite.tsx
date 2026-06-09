import { useEffect, useState } from "react"
import { useParams, useNavigate, Link } from "react-router-dom"
import { Loader2, CheckCircle2, XCircle, Users } from "lucide-react"
import { acceptInvite } from "@/api/team"

/** Handles an invitation link: POSTs the token, then shows the result. */
export default function AcceptInvite() {
  const { token } = useParams<{ token: string }>()
  const navigate = useNavigate()
  const [state, setState] = useState<"loading" | "ok" | "error">("loading")
  const [message, setMessage] = useState("")

  useEffect(() => {
    let cancelled = false
    async function run() {
      if (!token) {
        setState("error")
        setMessage("Invalid invitation link.")
        return
      }
      try {
        const res = await acceptInvite(token)
        if (cancelled) return
        setState("ok")
        setMessage(res.message)
      } catch (e) {
        if (cancelled) return
        setState("error")
        const err = e as { response?: { data?: { detail?: string } }; message?: string }
        setMessage(err.response?.data?.detail ?? err.message ?? "Could not accept the invitation.")
      }
    }
    void run()
    return () => { cancelled = true }
  }, [token])

  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="rounded-xl border border-border bg-card p-8 max-w-md w-full">
        <div className="flex justify-center mb-4">
          {state === "loading" && <Loader2 className="h-10 w-10 text-primary animate-spin" />}
          {state === "ok" && <CheckCircle2 className="h-10 w-10 text-emerald-400" />}
          {state === "error" && <XCircle className="h-10 w-10 text-red-400" />}
        </div>
        <h1 className="text-xl font-semibold text-foreground flex items-center justify-center gap-2">
          <Users className="h-5 w-5 text-primary" />
          Team invitation
        </h1>
        <p className="text-sm text-muted-foreground mt-2">
          {state === "loading" ? "Accepting your invitation…" : message}
        </p>
        {state === "ok" && (
          <button
            onClick={() => navigate("/servers")}
            className="mt-5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            Go to servers
          </button>
        )}
        {state === "error" && (
          <Link to="/dashboard" className="mt-5 inline-block rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted/50 transition-colors">
            Back to dashboard
          </Link>
        )}
      </div>
    </div>
  )
}

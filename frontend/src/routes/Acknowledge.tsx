import { useEffect, useRef, useState } from "react"
import { useParams } from "react-router-dom"
import { CircleCheck, CircleAlert, Loader2 } from "lucide-react"
import { acknowledgeByToken } from "@/api/escalation"
import { LogoMark } from "@/components/brand/Logo"

/**
 * The acknowledge page a page's link opens. **Unauthenticated by design** — the person
 * being woken may be reading a text on a phone that has never signed in here.
 *
 * It does exactly one thing, and says plainly what happened. It deliberately does not show
 * incident details beyond the title: whoever has the link can stop the alerts, but the link
 * is not a way into the account.
 */
export default function Acknowledge() {
  const { token = "" } = useParams()
  const [state, setState] = useState<"working" | "done" | "stale">("working")
  const [title, setTitle] = useState<string | null>(null)
  const [message, setMessage] = useState("")
  // Acknowledging is a write, and React 18 dev mode mounts effects twice — guard so one
  // click is one acknowledgement.
  const fired = useRef(false)

  useEffect(() => {
    if (fired.current || !token) return
    fired.current = true
    acknowledgeByToken(token)
      .then((res) => {
        setState(res.acknowledged ? "done" : "stale")
        setTitle(res.title ?? null)
        setMessage(res.message)
      })
      .catch(() => {
        setState("stale")
        setMessage("We couldn’t reach ServerAlly just now. Please try the link again.")
      })
  }, [token])

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm text-center">
        <div className="mb-6 flex items-center justify-center gap-2">
          <LogoMark size={20} />
          <span className="text-sm font-semibold text-foreground">ServerAlly</span>
        </div>

        {state === "working" && (
          <>
            <Loader2 className="mx-auto h-6 w-6 animate-spin text-muted-foreground" />
            <p className="mt-3 text-sm text-muted-foreground">Stopping the alerts…</p>
          </>
        )}

        {state === "done" && (
          <>
            <CircleCheck className="mx-auto h-9 w-9 text-emerald-600 dark:text-emerald-400" />
            <h1 className="mt-3 text-h2 text-foreground">Got it</h1>
            {title && <p className="mt-1 text-sm font-medium text-foreground">{title}</p>}
            <p className="mt-2 text-sm text-muted-foreground">{message}</p>
            <p className="mt-4 text-xs text-muted-foreground">
              The problem is still open — this only stopped the reminders.
            </p>
          </>
        )}

        {state === "stale" && (
          <>
            <CircleAlert className="mx-auto h-9 w-9 text-muted-foreground" />
            <h1 className="mt-3 text-h2 text-foreground">Nothing to do</h1>
            <p className="mt-2 text-sm text-muted-foreground">{message}</p>
          </>
        )}

        <a href="/incidents"
          className="mt-6 inline-block text-xs text-primary underline hover:no-underline">
          Open ServerAlly
        </a>
      </div>
    </div>
  )
}

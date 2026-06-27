import { useState, useRef, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Bell, CheckCircle2, XCircle, Clock, Ban } from "lucide-react"
import { formatDistanceToNow } from "date-fns"
import { getNotifications, markAllNotificationsRead } from "@/api/notifications"

function statusIcon(status: string | null) {
  switch (status) {
    case "success":
      return <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-green-500" />
    case "failed":
      return <XCircle size={14} className="mt-0.5 shrink-0 text-red-500" />
    case "stalled":
      return <Clock size={14} className="mt-0.5 shrink-0 text-orange-500" />
    case "cancelled":
      return <Ban size={14} className="mt-0.5 shrink-0 text-amber-500" />
    default:
      return <Bell size={14} className="mt-0.5 shrink-0 text-muted-foreground" />
  }
}

/** The in-app notification bell — polls for run-finished notifications (Update 17). */
export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()
  const navigate = useNavigate()
  const ref = useRef<HTMLDivElement>(null)

  const { data } = useQuery({
    queryKey: ["notifications"],
    queryFn: getNotifications,
    refetchInterval: 30000,
    refetchOnWindowFocus: true,
  })

  const unread = data?.unread ?? 0
  const items = data?.items ?? []

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onClick)
    return () => document.removeEventListener("mousedown", onClick)
  }, [open])

  async function toggle() {
    const next = !open
    setOpen(next)
    if (next && unread > 0) {
      await markAllNotificationsRead()
      qc.invalidateQueries({ queryKey: ["notifications"] })
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={toggle}
        title="Notifications"
        className="relative flex items-center justify-center rounded-md p-2 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
      >
        <Bell size={16} />
        {unread > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-11 z-30 w-80 rounded-lg border border-border bg-card shadow-xl">
          <div className="border-b border-border px-4 py-2.5 text-sm font-medium text-foreground">
            Notifications
          </div>
          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-muted-foreground">
                No notifications yet
              </div>
            ) : (
              items.map((n) => (
                <button
                  key={n.id}
                  onClick={() => {
                    setOpen(false)
                    if (n.server_id) navigate(`/servers/${n.server_id}`)
                  }}
                  className={`flex w-full items-start gap-2.5 border-b border-border px-4 py-3 text-left hover:bg-accent/50 ${n.read ? "" : "bg-primary/5"}`}
                >
                  {statusIcon(n.status)}
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">{n.title}</p>
                    {n.body && <p className="truncate text-xs text-muted-foreground">{n.body}</p>}
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}
                    </p>
                  </div>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

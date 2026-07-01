import { useState, useRef, useEffect } from "react"
import { useNavigate, Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Settings, LogOut, ChevronDown } from "lucide-react"
import { useAuthStore } from "@/store/authStore"
import { logout } from "@/api/auth"

/** Two-letter avatar initials from the user's name (or email as a fallback). */
function initials(name: string | null, email: string): string {
  const src = (name ?? email).trim()
  const parts = src.split(/\s+/).filter(Boolean)
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase()
  return src.slice(0, 2).toUpperCase()
}

function Avatar({ url, fallback, size }: { url: string | null; fallback: string; size: number }) {
  if (url) {
    return <img src={url} alt="" className="rounded-full object-cover" style={{ height: size, width: size }} />
  }
  return (
    <span
      className="flex items-center justify-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 font-semibold text-white"
      style={{ height: size, width: size, fontSize: size * 0.4 }}
    >
      {fallback}
    </span>
  )
}

/** The account menu — avatar chip that opens a dropdown (account details, settings, log out). */
export default function UserMenu() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { user, clearAuth } = useAuthStore()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener("mousedown", onClick)
    return () => document.removeEventListener("mousedown", onClick)
  }, [open])

  if (!user) return null

  async function handleLogout() {
    await logout()
    clearAuth()
    navigate("/auth", { replace: true })
  }

  const fallback = initials(user.name, user.email)

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 rounded-full py-1 pl-1 pr-2 transition-colors hover:bg-accent"
      >
        <Avatar url={user.avatar_url} fallback={fallback} size={28} />
        <span className="hidden max-w-[10rem] truncate text-sm font-medium text-foreground sm:block">
          {user.name ?? user.email}
        </span>
        <ChevronDown
          size={14}
          className={`text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {open && (
        <div className="absolute right-0 top-12 z-30 w-60 overflow-hidden rounded-xl border border-border bg-card shadow-xl">
          {/* Account header */}
          <div className="flex items-center gap-3 border-b border-border px-4 py-3">
            <Avatar url={user.avatar_url} fallback={fallback} size={36} />
            <div className="min-w-0">
              {user.name && <p className="truncate text-sm font-medium text-foreground">{user.name}</p>}
              <p className="truncate text-xs text-muted-foreground">{user.email}</p>
            </div>
          </div>

          {/* Actions */}
          <div className="p-1">
            <Link
              to="/settings"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-foreground transition-colors hover:bg-accent"
            >
              <Settings size={15} className="text-muted-foreground" />
              {t("nav.settings", "Settings")}
            </Link>
          </div>

          <div className="border-t border-border p-1">
            <button
              onClick={handleLogout}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-red-500 transition-colors hover:bg-red-500/10"
            >
              <LogOut size={15} />
              {t("auth.logout")}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

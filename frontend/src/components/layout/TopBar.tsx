import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { LogOut } from "lucide-react"
import { useAuthStore } from "@/store/authStore"
import { logout } from "@/api/auth"

export default function TopBar() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { user, clearAuth } = useAuthStore()

  async function handleLogout() {
    await logout()
    clearAuth()
    navigate("/auth", { replace: true })
  }

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-card px-6">
      <div />
      <div className="flex items-center gap-4">
        {user && (
          <span className="text-sm text-muted-foreground">{user.name ?? user.email}</span>
        )}
        <button
          onClick={handleLogout}
          title={t("auth.logout")}
          className="flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          <LogOut size={14} />
          {t("auth.logout")}
        </button>
      </div>
    </header>
  )
}

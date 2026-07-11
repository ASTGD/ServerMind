import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useTranslation } from "react-i18next"
import Logo from "@/components/brand/Logo"
import { login, register } from "@/api/auth"
import { useAuthStore } from "@/store/authStore"
import i18n from "@/i18n/index"

/** Normalize a FastAPI error `detail` into one readable line — it's a plain string
 *  for our own HTTPExceptions, but an array of {msg, loc, ...} objects for pydantic's
 *  automatic 422 validation errors (e.g. a rejected email format). */
function detailToMessage(detail: unknown): string | null {
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg?: unknown }).msg) : null))
      .filter((m): m is string => !!m)
    if (msgs.length) return msgs.join("; ")
  }
  return null
}

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "bn", label: "বাংলা" },
  { code: "ar", label: "العربية" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
  { code: "hi", label: "हिन्दी" },
  { code: "pt", label: "Português" },
  { code: "tr", label: "Türkçe" },
]

export default function Auth() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)

  const [mode, setMode] = useState<"login" | "register">("login")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [name, setName] = useState("")
  const [language, setLanguage] = useState("en")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  const [totpCode, setTotpCode] = useState("")
  const [totpRequired, setTotpRequired] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const result =
        mode === "login"
          ? await login({ email, password, totp_code: totpRequired ? totpCode : undefined })
          : await register({ email, password, name, preferred_language: language })

      // Persist language choice in i18n
      i18n.changeLanguage(result.user.preferred_language)
      localStorage.setItem("lang", result.user.preferred_language)

      setAuth(result.user, result.access_token, result.refresh_token)
      navigate("/dashboard", { replace: true })
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      if (mode === "login" && detail === "TOTP code required") {
        // 2FA challenge — reveal the code field (only show an error if a code was tried).
        setTotpRequired(true)
        if (totpCode) {
          setError("Invalid authentication code.")
          setTotpCode("") // codes roll every 30s — clear the stale one for a fresh entry
        } else {
          setError("")
        }
      } else {
        setError(detailToMessage(detail) ?? (err instanceof Error ? err.message : t("common.error")))
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <div className="w-full max-w-sm space-y-6">
        {/* Logo */}
        <div className="flex justify-center">
          <Logo size="lg" />
        </div>

        {/* Card */}
        <div className="rounded-xl border border-border bg-card p-6 shadow-sm">
          <h2 className="mb-1 text-lg font-semibold text-foreground">
            {mode === "login" ? t("auth.login") : t("auth.register")}
          </h2>
          <p className="mb-5 text-sm text-muted-foreground">{t("app.tagline")}</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === "register" && (
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">
                  {t("auth.name")}
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Jane Smith"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </div>
            )}

            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                {t("auth.email")}
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                placeholder="you@example.com"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">
                {t("auth.password")}
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="••••••••"
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            {mode === "login" && totpRequired && (
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">
                  Authentication code
                </label>
                <input
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  autoFocus
                  value={totpCode}
                  onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
                  placeholder="123456"
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring font-mono tracking-widest"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Enter the 6-digit code from your authenticator app.
                </p>
              </div>
            )}

            {mode === "register" && (
              <div>
                <label className="mb-1 block text-sm font-medium text-foreground">
                  {t("auth.language")}
                </label>
                <select
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  {LANGUAGES.map((l) => (
                    <option key={l.code} value={l.code}>
                      {l.label}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {error && (
              <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {loading ? t("common.loading") : mode === "login" ? t("auth.login") : t("auth.register")}
            </button>
          </form>
        </div>

        {/* Toggle */}
        <p className="text-center text-sm text-muted-foreground">
          {mode === "login" ? (
            <>
              Don&apos;t have an account?{" "}
              <button
                onClick={() => {
                  setMode("register")
                  setTotpRequired(false)
                  setTotpCode("")
                  setError("")
                }}
                className="font-medium text-foreground underline-offset-2 hover:underline"
              >
                {t("auth.register")}
              </button>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <button
                onClick={() => {
                  setMode("login")
                  setTotpRequired(false)
                  setTotpCode("")
                  setError("")
                }}
                className="font-medium text-foreground underline-offset-2 hover:underline"
              >
                {t("auth.login")}
              </button>
            </>
          )}
        </p>
      </div>
    </div>
  )
}

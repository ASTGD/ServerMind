import { useState, type ReactNode } from "react"
import { useMutation } from "@tanstack/react-query"
import { User as UserIcon, Globe, Lock, BadgeCheck, ShieldCheck, Check, Loader2 } from "lucide-react"
import { QRCodeSVG } from "qrcode.react"
import {
  updateProfile, updateLanguage, changePassword,
  setup2fa, verify2fa, disable2fa, type TotpSetupResponse,
} from "@/api/auth"
import { useAuthStore } from "@/store/authStore"
import i18n from "@/i18n"
import type { User } from "@/types"

const LANGUAGES = [
  { code: "en", label: "English" },
  { code: "bn", label: "বাংলা (Bengali)" },
  { code: "ar", label: "العربية (Arabic)" },
  { code: "es", label: "Español" },
  { code: "fr", label: "Français" },
  { code: "hi", label: "हिन्दी (Hindi)" },
  { code: "pt", label: "Português" },
  { code: "tr", label: "Türkçe" },
]

function errMsg(e: unknown): string {
  const ax = e as { response?: { data?: { detail?: string } } }
  return ax?.response?.data?.detail ?? "Something went wrong. Please try again."
}

/** A titled settings card. */
function Section({
  icon: Icon,
  title,
  description,
  children,
}: {
  icon: typeof UserIcon
  title: string
  description: string
  children: ReactNode
}) {
  return (
    <section className="rounded-xl border border-border bg-card p-6">
      <div className="flex items-start gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted text-foreground/70">
          <Icon size={18} />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-foreground">{title}</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
          <div className="mt-5">{children}</div>
        </div>
      </div>
    </section>
  )
}

const inputCls =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40 disabled:opacity-60"
const labelCls = "block text-xs font-medium text-muted-foreground mb-1.5"
const btnCls =
  "flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"

export default function Settings() {
  const user = useAuthStore((s) => s.user)
  const token = useAuthStore((s) => s.token)
  const setAuth = useAuthStore((s) => s.setAuth)

  const [name, setName] = useState(user?.name ?? "")
  const [profileMsg, setProfileMsg] = useState("")

  const [curPw, setCurPw] = useState("")
  const [newPw, setNewPw] = useState("")
  const [confirmPw, setConfirmPw] = useState("")
  const [pwMsg, setPwMsg] = useState("")
  const [pwErr, setPwErr] = useState("")

  const [langMsg, setLangMsg] = useState("")

  const [twoFAStep, setTwoFAStep] = useState<"idle" | "enrolling">("idle")
  const [setupData, setSetupData] = useState<TotpSetupResponse | null>(null)
  const [totpCode, setTotpCode] = useState("")
  const [showDisable, setShowDisable] = useState(false)
  const [disableCode, setDisableCode] = useState("")
  const [twoFAMsg, setTwoFAMsg] = useState("")
  const [twoFAErr, setTwoFAErr] = useState("")

  const syncUser = (u: User) => {
    if (token) setAuth(u, token)
  }

  const profileMut = useMutation({
    mutationFn: () => updateProfile({ name: name.trim() }),
    onSuccess: (u) => {
      syncUser(u)
      setProfileMsg("Saved")
      setTimeout(() => setProfileMsg(""), 2500)
    },
  })

  const langMut = useMutation({
    mutationFn: (code: string) => updateLanguage(code),
    onSuccess: (u) => {
      syncUser(u)
      void i18n.changeLanguage(u.preferred_language)
      localStorage.setItem("lang", u.preferred_language)
      setLangMsg("Language updated")
      setTimeout(() => setLangMsg(""), 2500)
    },
  })

  const pwMut = useMutation({
    mutationFn: () => changePassword(curPw, newPw),
    onSuccess: () => {
      setCurPw("")
      setNewPw("")
      setConfirmPw("")
      setPwErr("")
      setPwMsg("Password changed")
      setTimeout(() => setPwMsg(""), 3000)
    },
    onError: (e) => {
      setPwMsg("")
      setPwErr(errMsg(e))
    },
  })

  const setupMut = useMutation({
    mutationFn: () => setup2fa(),
    onSuccess: (d) => {
      setSetupData(d)
      setTwoFAStep("enrolling")
      setTwoFAErr("")
    },
    onError: (e) => setTwoFAErr(errMsg(e)),
  })

  const verifyMut = useMutation({
    mutationFn: () => verify2fa(totpCode.trim()),
    onSuccess: (u) => {
      syncUser(u)
      setTwoFAStep("idle")
      setSetupData(null)
      setTotpCode("")
      setTwoFAErr("")
      setTwoFAMsg("Two-factor authentication enabled")
      setTimeout(() => setTwoFAMsg(""), 3000)
    },
    onError: (e) => setTwoFAErr(errMsg(e)),
  })

  const disableMut = useMutation({
    mutationFn: () => disable2fa(disableCode.trim()),
    onSuccess: (u) => {
      syncUser(u)
      setShowDisable(false)
      setDisableCode("")
      setTwoFAErr("")
      setTwoFAMsg("Two-factor authentication disabled")
      setTimeout(() => setTwoFAMsg(""), 3000)
    },
    onError: (e) => setTwoFAErr(errMsg(e)),
  })

  if (!user) return null

  const nameChanged = name.trim() !== (user.name ?? "")

  const submitPassword = () => {
    setPwErr("")
    setPwMsg("")
    if (newPw.length < 8) {
      setPwErr("New password must be at least 8 characters.")
      return
    }
    if (newPw !== confirmPw) {
      setPwErr("New passwords don't match.")
      return
    }
    pwMut.mutate()
  }

  const profileSection = (
    <Section icon={UserIcon} title="Profile" description="Your name and account email.">
      <div className="space-y-4">
        <div>
          <label className={labelCls}>Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name"
            className={inputCls}
          />
        </div>
        <div>
          <label className={labelCls}>Email</label>
          <div className="flex items-center gap-2">
            <input value={user.email} disabled className={inputCls} />
            {user.is_verified && (
              <span className="flex shrink-0 items-center gap-1 rounded-full border border-green-500/20 bg-green-500/10 px-2 py-1 text-xs font-medium text-green-600">
                <BadgeCheck size={13} /> Verified
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">Email can't be changed here.</p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => profileMut.mutate()}
            disabled={!nameChanged || profileMut.isPending}
            className={btnCls}
          >
            {profileMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Save changes
          </button>
          {profileMsg && (
            <span className="flex items-center gap-1 text-sm text-green-600">
              <Check size={15} /> {profileMsg}
            </span>
          )}
        </div>
      </div>
    </Section>
  )

  const languageSection = (
    <Section icon={Globe} title="Language" description="Used for AI responses and the interface.">
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={user.preferred_language}
          onChange={(e) => langMut.mutate(e.target.value)}
          disabled={langMut.isPending}
          className={`${inputCls} max-w-xs`}
        >
          {LANGUAGES.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>
        {langMut.isPending && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        {langMsg && (
          <span className="flex items-center gap-1 text-sm text-green-600">
            <Check size={15} /> {langMsg}
          </span>
        )}
      </div>
    </Section>
  )

  const passwordSection = (
    <Section icon={Lock} title="Password" description="Change your account password.">
      <div className="space-y-4">
        <div>
          <label className={labelCls}>Current password</label>
          <input
            type="password"
            value={curPw}
            onChange={(e) => setCurPw(e.target.value)}
            autoComplete="current-password"
            className={inputCls}
          />
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className={labelCls}>New password</label>
            <input
              type="password"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              autoComplete="new-password"
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>Confirm new password</label>
            <input
              type="password"
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              autoComplete="new-password"
              className={inputCls}
            />
          </div>
        </div>
        {pwErr && <p className="text-sm text-red-500">{pwErr}</p>}
        <div className="flex items-center gap-3">
          <button
            onClick={submitPassword}
            disabled={!curPw || !newPw || !confirmPw || pwMut.isPending}
            className={btnCls}
          >
            {pwMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Update password
          </button>
          {pwMsg && (
            <span className="flex items-center gap-1 text-sm text-green-600">
              <Check size={15} /> {pwMsg}
            </span>
          )}
        </div>
      </div>
    </Section>
  )

  const accountSection = (
    <Section icon={BadgeCheck} title="Account" description="Account details.">
      <dl className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <dt className="text-xs text-muted-foreground">Member since</dt>
          <dd className="mt-0.5 text-foreground">
            {new Date(user.created_at).toLocaleDateString(undefined, {
              year: "numeric",
              month: "long",
              day: "numeric",
            })}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Status</dt>
          <dd className="mt-0.5 flex items-center gap-2">
            <span className="rounded-full border border-green-500/20 bg-green-500/10 px-2 py-0.5 text-xs font-medium text-green-600">
              {user.is_active ? "Active" : "Disabled"}
            </span>
          </dd>
        </div>
      </dl>
    </Section>
  )

  const twoFactorSection = (
    <Section
      icon={ShieldCheck}
      title="Two-factor authentication"
      description="Require a one-time code from an authenticator app at login."
    >
      {user.totp_enabled ? (
        <div className="space-y-3">
          <span className="inline-flex items-center gap-1 rounded-full border border-green-500/20 bg-green-500/10 px-2 py-0.5 text-xs font-medium text-green-600">
            <Check size={13} /> Enabled
          </span>
          {!showDisable ? (
            <div>
              <button
                onClick={() => {
                  setShowDisable(true)
                  setTwoFAErr("")
                  setTwoFAMsg("")
                }}
                className="block rounded-md border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-500/20"
              >
                Disable 2FA
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              <div>
                <label className={labelCls}>Enter a current code to disable</label>
                <input
                  value={disableCode}
                  onChange={(e) => setDisableCode(e.target.value.replace(/\D/g, ""))}
                  inputMode="numeric"
                  maxLength={6}
                  autoComplete="one-time-code"
                  placeholder="123456"
                  className={`${inputCls} max-w-[12rem] font-mono tracking-widest`}
                />
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => disableMut.mutate()}
                  disabled={disableCode.trim().length !== 6 || disableMut.isPending}
                  className="flex items-center gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-500/20 disabled:opacity-50"
                >
                  {disableMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Confirm disable
                </button>
                <button
                  onClick={() => {
                    setShowDisable(false)
                    setDisableCode("")
                    setTwoFAErr("")
                  }}
                  className="px-3 py-2 text-sm text-muted-foreground hover:text-foreground"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      ) : twoFAStep === "enrolling" && setupData ? (
        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Scan with an authenticator app (Google Authenticator, 1Password, Authy…), then enter the 6-digit code.
          </p>
          <div className="inline-block rounded-lg bg-white p-3">
            <QRCodeSVG value={setupData.otpauth_uri} size={160} />
          </div>
          <div>
            <p className="mb-1 text-xs text-muted-foreground">Can't scan? Enter this key manually:</p>
            <code className="block select-all break-all rounded bg-muted px-2 py-1 font-mono text-xs text-foreground">
              {setupData.secret}
            </code>
          </div>
          <div>
            <label className={labelCls}>6-digit code</label>
            <input
              value={totpCode}
              onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
              inputMode="numeric"
              maxLength={6}
              autoComplete="one-time-code"
              placeholder="123456"
              className={`${inputCls} max-w-[12rem] font-mono tracking-widest`}
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => verifyMut.mutate()}
              disabled={totpCode.trim().length !== 6 || verifyMut.isPending}
              className={btnCls}
            >
              {verifyMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Verify &amp; enable
            </button>
            <button
              onClick={() => {
                setTwoFAStep("idle")
                setSetupData(null)
                setTotpCode("")
                setTwoFAErr("")
              }}
              className="px-3 py-2 text-sm text-muted-foreground hover:text-foreground"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => setupMut.mutate()}
          disabled={setupMut.isPending}
          className={btnCls}
        >
          {setupMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
          Enable 2FA
        </button>
      )}

      {twoFAErr && <p className="mt-3 text-sm text-red-500">{twoFAErr}</p>}
      {twoFAMsg && (
        <p className="mt-3 flex items-center gap-1 text-sm text-green-600">
          <Check size={15} /> {twoFAMsg}
        </p>
      )}
    </Section>
  )

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Settings</h1>
        <p className="mt-0.5 text-sm text-muted-foreground">Manage your account and preferences.</p>
      </div>

      <div className="grid items-start gap-6 lg:grid-cols-2">
        <div className="space-y-6">
          {profileSection}
          {accountSection}
        </div>
        <div className="space-y-6">
          {languageSection}
          {passwordSection}
          {twoFactorSection}
        </div>
      </div>
    </div>
  )
}

import { useState, useRef, useEffect, type ReactNode } from "react"
import { useMutation, useQuery } from "@tanstack/react-query"
import { User as UserIcon, Globe, Lock, BadgeCheck, ShieldCheck, History, Check, Loader2, Sparkles } from "lucide-react"
import { QRCodeSVG } from "qrcode.react"
import { listAudit } from "@/api/audit"
import {
  updateProfile, updateLanguage, changePassword,
  setup2fa, verify2fa, disable2fa, regenerateRecoveryCodes, type TotpSetupResponse,
} from "@/api/auth"
import { getAiSettings, updateAiSettings, testAiSettings, type AiProvider, type AiSettings } from "@/api/settings"
import { getMyUsage } from "@/api/usage"
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

const ACTION_LABELS: Record<string, string> = {
  "auth.login": "Signed in",
  "auth.logout": "Signed out",
  "auth.register": "Account created",
  "auth.password_change": "Password changed",
  "auth.2fa_enabled": "Two-factor enabled",
  "auth.2fa_disabled": "Two-factor disabled",
  "auth.2fa_recovery_regenerated": "Recovery codes regenerated",
  "server.create": "Server added",
  "server.delete": "Server removed",
  "team.invite": "Team member invited",
  "team.role_change": "Team role changed",
  "team.remove": "Team member removed",
}

function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return "just now"
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d}d ago`
  return new Date(iso).toLocaleDateString()
}

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
  const [recoveryCodes, setRecoveryCodes] = useState<string[] | null>(null)
  const [showRegen, setShowRegen] = useState(false)
  const [regenCode, setRegenCode] = useState("")

  // AI provider config (Update 20.1)
  const [aiProvider, setAiProvider] = useState<AiProvider>("anthropic")
  const [aiKey, setAiKey] = useState("")
  const [aiModel, setAiModel] = useState("")
  const [aiBaseUrl, setAiBaseUrl] = useState("")
  const [aiMsg, setAiMsg] = useState("")
  const [aiHasKey, setAiHasKey] = useState(false)
  const [aiTest, setAiTest] = useState<{ ok: boolean; text: string } | null>(null)
  const aiSeeded = useRef(false)
  const aiQuery = useQuery({ queryKey: ["ai-settings"], queryFn: getAiSettings })
  const { data: usage } = useQuery({ queryKey: ["my-usage"], queryFn: getMyUsage })
  useEffect(() => {
    const d = aiQuery.data
    if (d && !aiSeeded.current) {
      aiSeeded.current = true
      setAiProvider(d.provider)
      setAiModel(d.model)
      setAiBaseUrl(d.base_url)
      setAiHasKey(d.has_key)
    }
  }, [aiQuery.data])
  const aiMut = useMutation({
    mutationFn: () =>
      updateAiSettings({ provider: aiProvider, api_key: aiKey || undefined, model: aiModel, base_url: aiBaseUrl }),
    onSuccess: (data: AiSettings) => {
      setAiHasKey(data.has_key)
      setAiKey("")
      setAiMsg("Saved")
      setAiTest(null)
      setTimeout(() => setAiMsg(""), 2000)
    },
  })
  const aiTestMut = useMutation({
    mutationFn: testAiSettings,
    onSuccess: (r) => setAiTest({ ok: r.ok, text: r.ok ? r.reply || "OK" : r.error || "failed" }),
  })

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
    onSuccess: (res) => {
      syncUser(res.user)
      setTwoFAStep("idle")
      setSetupData(null)
      setTotpCode("")
      setTwoFAErr("")
      setRecoveryCodes(res.recovery_codes)
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

  const regenMut = useMutation({
    mutationFn: () => regenerateRecoveryCodes(regenCode.trim()),
    onSuccess: (codes) => {
      setShowRegen(false)
      setRegenCode("")
      setTwoFAErr("")
      setRecoveryCodes(codes)
      setTwoFAMsg("New recovery codes generated")
      setTimeout(() => setTwoFAMsg(""), 3000)
    },
    onError: (e) => setTwoFAErr(errMsg(e)),
  })

  const { data: audit = [] } = useQuery({
    queryKey: ["audit"],
    queryFn: () => listAudit(25),
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

  const usageSection = (
    <Section
      icon={Sparkles}
      title="Ally usage"
      description="Your AI actions this month — one action is one request to Ally."
    >
      {usage ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-foreground">
              <span className="font-semibold">{usage.used}</span> of {usage.limit} actions used
            </span>
            <span className="rounded-full border border-indigo-500/20 bg-indigo-500/10 px-2 py-0.5 text-xs font-medium capitalize text-indigo-600 dark:text-indigo-400">
              {usage.plan} plan
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className={`h-full rounded-full transition-all ${
                usage.used / usage.limit >= 0.9
                  ? "bg-red-500"
                  : usage.used / usage.limit >= 0.7
                    ? "bg-amber-500"
                    : "bg-gradient-to-r from-indigo-500 to-violet-500"
              }`}
              style={{ width: `${Math.min(100, (usage.used / Math.max(1, usage.limit)) * 100)}%` }}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            Your allowance resets on {usage.resets_at}.
            {!usage.enforced && " (Usage is informational on this install — no limit is enforced.)"}
          </p>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">Loading usage…</p>
      )}
    </Section>
  )

  const twoFactorSection = (
    <Section
      icon={ShieldCheck}
      title="Two-factor authentication"
      description="Require a one-time code from an authenticator app at login."
    >
      {recoveryCodes ? (
        <div className="space-y-3">
          <p className="text-sm font-medium text-foreground">Save your recovery codes</p>
          <p className="text-xs text-muted-foreground">
            Each code works once. Store them somewhere safe — they're the only way back in if you lose your authenticator.
          </p>
          <div className="grid grid-cols-2 gap-2 rounded-lg border border-border bg-muted/40 p-3 font-mono text-sm">
            {recoveryCodes.map((c) => (
              <span key={c} className="select-all">
                {c}
              </span>
            ))}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                void navigator.clipboard?.writeText(recoveryCodes.join("\n"))
                setTwoFAMsg("Copied")
                setTimeout(() => setTwoFAMsg(""), 2000)
              }}
              className={btnCls}
            >
              Copy codes
            </button>
            <button
              onClick={() => setRecoveryCodes(null)}
              className="px-3 py-2 text-sm text-muted-foreground hover:text-foreground"
            >
              I've saved them
            </button>
          </div>
        </div>
      ) : user.totp_enabled ? (
        <div className="space-y-3">
          <span className="inline-flex items-center gap-1 rounded-full border border-green-500/20 bg-green-500/10 px-2 py-0.5 text-xs font-medium text-green-600">
            <Check size={13} /> Enabled
          </span>
          {showRegen ? (
            <div className="space-y-3">
              <div>
                <label className={labelCls}>Enter a current code to regenerate</label>
                <input
                  value={regenCode}
                  onChange={(e) => setRegenCode(e.target.value.replace(/\D/g, ""))}
                  inputMode="numeric"
                  maxLength={6}
                  autoComplete="one-time-code"
                  placeholder="123456"
                  className={`${inputCls} max-w-[12rem] font-mono tracking-widest`}
                />
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => regenMut.mutate()}
                  disabled={regenCode.trim().length !== 6 || regenMut.isPending}
                  className={btnCls}
                >
                  {regenMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                  Generate new codes
                </button>
                <button
                  onClick={() => {
                    setShowRegen(false)
                    setRegenCode("")
                    setTwoFAErr("")
                  }}
                  className="px-3 py-2 text-sm text-muted-foreground hover:text-foreground"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : showDisable ? (
            <div className="space-y-3">
              <div>
                <label className={labelCls}>Enter a code or recovery code to disable</label>
                <input
                  value={disableCode}
                  onChange={(e) => setDisableCode(e.target.value)}
                  maxLength={14}
                  autoComplete="one-time-code"
                  placeholder="123456 or recovery code"
                  className={`${inputCls} max-w-[16rem] font-mono`}
                />
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => disableMut.mutate()}
                  disabled={disableCode.trim().length < 6 || disableMut.isPending}
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
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={() => {
                  setShowRegen(true)
                  setShowDisable(false)
                  setTwoFAErr("")
                  setTwoFAMsg("")
                }}
                className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-muted/50"
              >
                Regenerate recovery codes
              </button>
              <button
                onClick={() => {
                  setShowDisable(true)
                  setShowRegen(false)
                  setTwoFAErr("")
                  setTwoFAMsg("")
                }}
                className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-500/20"
              >
                Disable 2FA
              </button>
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

  const auditSection = (
    <Section
      icon={History}
      title="Recent security activity"
      description="Sign-ins and account changes on your account."
    >
      {audit.length === 0 ? (
        <p className="text-sm text-muted-foreground">No recent activity.</p>
      ) : (
        <ul className="divide-y divide-border text-sm">
          {audit.map((e) => (
            <li key={e.id} className="flex items-center justify-between gap-3 py-2">
              <span className="text-foreground">{ACTION_LABELS[e.action] ?? e.action}</span>
              <span className="flex items-center gap-3 text-xs text-muted-foreground">
                {e.ip && <span className="font-mono">{e.ip}</span>}
                <span className="tabular-nums">{timeAgo(e.created_at)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  )

  const AI_PROVIDERS: { value: AiProvider; label: string; placeholder: string }[] = [
    { value: "servermind", label: "ServerAlly AI (subscription — no key needed)", placeholder: "" },
    { value: "anthropic", label: "Anthropic (Claude)", placeholder: "claude-sonnet-4-20250514" },
    { value: "openai", label: "OpenAI (GPT)", placeholder: "gpt-4o" },
    { value: "gemini", label: "Google (Gemini)", placeholder: "gemini-1.5-pro" },
    { value: "openai_compatible", label: "OpenAI-compatible (custom)", placeholder: "model name" },
  ]
  const aiPlaceholder = AI_PROVIDERS.find((p) => p.value === aiProvider)?.placeholder ?? ""
  const isServermind = aiProvider === "servermind"

  // Bring-your-own-AI-key is demoted for the hosted "ServerAlly AI" (Ally) model — cloud
  // users get AI with their plan, no key to configure. Flip to true for the self-hosted
  // edition, where the operator configures their own provider.
  const SHOW_AI_PROVIDER_SETTINGS = false

  const aiSection = (
    <Section
      icon={Sparkles}
      title="AI provider"
      description="Powers chat and script generation — bring your own key from any provider."
    >
      <div className="space-y-4">
        <div>
          <label className={labelCls}>Provider</label>
          <select
            value={aiProvider}
            onChange={(e) => {
              setAiProvider(e.target.value as AiProvider)
              setAiTest(null)
            }}
            className={inputCls}
          >
            {AI_PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={labelCls}>
            {isServermind ? "Subscription token" : "API key"}{" "}
            {aiHasKey && (
              <span className="font-normal text-green-600">
                · {isServermind ? "a token is saved" : "a key is saved"}
              </span>
            )}
          </label>
          <input
            type="password"
            value={aiKey}
            onChange={(e) => setAiKey(e.target.value)}
            autoComplete="new-password"
            placeholder={
              aiHasKey
                ? "•••••••• (leave blank to keep)"
                : isServermind
                  ? "Paste your ServerAlly AI token"
                  : "Paste your API key"
            }
            className={inputCls}
          />
          <p className="mt-1 text-xs text-muted-foreground">
            {isServermind
              ? "From your ServerAlly AI subscription — no AI key of your own needed. Stored encrypted."
              : "Encrypted (AES-256-GCM) before storage — never shown again."}
          </p>
        </div>
        {!isServermind && (
          <div>
            <label className={labelCls}>
              Model <span className="font-normal text-muted-foreground/70">(optional)</span>
            </label>
            <input
              value={aiModel}
              onChange={(e) => setAiModel(e.target.value)}
              placeholder={aiPlaceholder}
              className={inputCls}
            />
          </div>
        )}
        {aiProvider === "openai_compatible" && (
          <div>
            <label className={labelCls}>Base URL</label>
            <input
              value={aiBaseUrl}
              onChange={(e) => setAiBaseUrl(e.target.value)}
              placeholder="https://your-endpoint/v1"
              className={inputCls}
            />
          </div>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button onClick={() => aiMut.mutate()} disabled={aiMut.isPending} className={btnCls}>
            {aiMut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Save
          </button>
          <button
            onClick={() => aiTestMut.mutate()}
            disabled={aiTestMut.isPending || !aiHasKey}
            title={!aiHasKey ? "Save a key first" : "Send a tiny test prompt"}
            className="flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted/50 disabled:opacity-50"
          >
            {aiTestMut.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            Test
          </button>
          {aiMsg && (
            <span className="flex items-center gap-1 text-sm text-green-600">
              <Check size={15} /> {aiMsg}
            </span>
          )}
        </div>
        {aiTest && (
          <p className={`text-sm ${aiTest.ok ? "text-green-600" : "text-red-500"}`}>
            {aiTest.ok ? `Working — replied "${aiTest.text}"` : `Failed: ${aiTest.text}`}
          </p>
        )}
      </div>
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
          {usageSection}
          {SHOW_AI_PROVIDER_SETTINGS && aiSection}
        </div>
        <div className="space-y-6">
          {languageSection}
          {passwordSection}
          {twoFactorSection}
        </div>
      </div>

      {auditSection}
    </div>
  )
}

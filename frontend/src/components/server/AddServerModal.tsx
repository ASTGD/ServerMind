import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { X, Eye, EyeOff, Loader2 } from "lucide-react"
import { createServer, type ServerCreateBody } from "@/api/servers"
import { ASSET_CATEGORIES, type AssetCategory } from "@/lib/assetCategories"
import { useTranslation } from "react-i18next"

interface Props {
  onClose: () => void
}

const DEFAULT_FORM: ServerCreateBody = {
  name: "",
  host: "",
  port: 22,
  username: "root",
  auth_type: "password",
  connection_type: "ssh",
  panel_type: null,
  category: "vps",
  credential: "",
  tags: null,
  notes: null,
}

export default function AddServerModal({ onClose }: Props) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [form, setForm] = useState<ServerCreateBody>(DEFAULT_FORM)
  const [showCred, setShowCred] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: createServer,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["servers"] })
      onClose()
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ?? t("common.error"))
    },
  })

  function set<K extends keyof ServerCreateBody>(key: K, value: ServerCreateBody[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const HOSTING_PORTS: Record<string, number> = { cyberpanel: 8090, cpanel: 2083, plesk: 8443 }

  function setConnectionType(value: ServerCreateBody["connection_type"]) {
    setForm((prev) => {
      const next = { ...prev, connection_type: value }
      // Sensible defaults per connection type.
      if (value === "winrm") {
        next.auth_type = "password" // WinRM uses NTLM, not SSH keys
        if (prev.port === 22) next.port = 5985
        if (prev.username === "root") next.username = "Administrator"
      } else if (value === "hosting") {
        next.auth_type = "password"
        next.panel_type = next.panel_type ?? "cyberpanel"
        next.port = HOSTING_PORTS[next.panel_type ?? "cyberpanel"] ?? 8090
        if (prev.username === "root") next.username = "admin"
      } else if (value === "ssh") {
        next.panel_type = null
        const nonSshPorts = [5985, 5986, ...Object.values(HOSTING_PORTS)]
        if (nonSshPorts.includes(prev.port)) next.port = 22
      }
      return next
    })
  }

  function setPanelType(panel: string) {
    setForm((prev) => ({ ...prev, panel_type: panel, port: HOSTING_PORTS[panel] ?? prev.port }))
  }

  /** Category-first: picking a tile records the category AND cascades the right transport
   *  defaults (Bare Metal + VPS both → ssh; the category just labels which it is). */
  function pickCategory(cat: AssetCategory) {
    if (!cat.available) return
    setForm((prev) => ({ ...prev, category: cat.id }))
    if (cat.connectionType) setConnectionType(cat.connectionType)
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    mutation.mutate(form)
  }

  const isHosting = form.connection_type === "hosting"
  const credLabel = isHosting
    ? (form.panel_type === "cpanel" ? "API Token" : "Panel Password")
    : form.auth_type === "key" ? "Private Key (PEM)" : "Password"
  const credPlaceholder = isHosting
    ? (form.panel_type === "cpanel" ? "cPanel API token" : "Control panel admin password")
    : form.auth_type === "key" ? "-----BEGIN OPENSSH PRIVATE KEY-----\n..." : "Server password"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-lg rounded-xl border border-border bg-card shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="font-semibold text-foreground">{t("servers.add")}</h2>
          <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:text-foreground">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 p-5">
          {/* Category — "what is this?" comes first (the Assets model) */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-muted-foreground">
              What are you adding?
            </label>
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
              {ASSET_CATEGORIES.map((cat) => {
                const active = form.category === cat.id
                const Icon = cat.icon
                return (
                  <button
                    key={cat.id}
                    type="button"
                    disabled={!cat.available}
                    onClick={() => pickCategory(cat)}
                    title={cat.available ? cat.blurb : "Coming soon"}
                    className={`flex flex-col items-center gap-1 rounded-lg border px-1.5 py-2.5 text-center transition ${
                      active
                        ? "border-primary bg-primary/10 text-primary"
                        : cat.available
                        ? "border-border text-foreground hover:border-primary/50"
                        : "cursor-not-allowed border-border/60 text-muted-foreground opacity-50"
                    }`}
                  >
                    <Icon size={18} />
                    <span className="text-[11px] font-medium leading-tight">{cat.label}</span>
                    {!cat.available && <span className="text-[9px] leading-none">Soon</span>}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Name */}
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Display Name
            </label>
            <input
              required
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              placeholder="My Production Server"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
          </div>

          {/* Panel type (Hosting) or Auth type (SSH) — WinRM has neither */}
          {isHosting ? (
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Panel Type</label>
              <select
                value={form.panel_type ?? "cyberpanel"}
                onChange={(e) => setPanelType(e.target.value)}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
              >
                <option value="cyberpanel">CyberPanel</option>
                <option value="cpanel">cPanel</option>
                <option value="plesk">Plesk</option>
              </select>
            </div>
          ) : form.connection_type === "ssh" ? (
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Auth Type</label>
              <select
                value={form.auth_type}
                onChange={(e) => set("auth_type", e.target.value as "password" | "key")}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
              >
                <option value="password">Password</option>
                <option value="key">SSH Key</option>
              </select>
            </div>
          ) : null}

          {/* Host + Port */}
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Host / IP
              </label>
              <input
                required
                value={form.host}
                onChange={(e) => set("host", e.target.value)}
                placeholder="192.168.1.1 or example.com"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Port
              </label>
              <input
                required
                type="number"
                min={1}
                max={65535}
                value={form.port}
                onChange={(e) => set("port", parseInt(e.target.value, 10))}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
              />
            </div>
          </div>

          {/* Username */}
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Username
            </label>
            <input
              required
              value={form.username}
              onChange={(e) => set("username", e.target.value)}
              placeholder="root"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
          </div>

          {/* Credential */}
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              {credLabel}
            </label>
            <div className="relative">
              {form.auth_type === "key" ? (
                <textarea
                  required
                  value={form.credential}
                  onChange={(e) => set("credential", e.target.value)}
                  placeholder={credPlaceholder}
                  rows={4}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none resize-none"
                />
              ) : (
                <input
                  required
                  type={showCred ? "text" : "password"}
                  value={form.credential}
                  onChange={(e) => set("credential", e.target.value)}
                  placeholder={credPlaceholder}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 pr-10 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
                />
              )}
              {form.auth_type === "password" && (
                <button
                  type="button"
                  onClick={() => setShowCred((v) => !v)}
                  className="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground"
                >
                  {showCred ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              )}
            </div>
          </div>

          {/* Notes */}
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">
              Notes (optional)
            </label>
            <input
              value={form.notes ?? ""}
              onChange={(e) => set("notes", e.target.value || null)}
              placeholder="Production web server, EU region..."
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
          </div>

          {error && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md px-4 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
            >
              {t("common.cancel")}
            </button>
            <button
              type="submit"
              disabled={mutation.isPending}
              className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {mutation.isPending && <Loader2 size={14} className="animate-spin" />}
              Add Asset
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

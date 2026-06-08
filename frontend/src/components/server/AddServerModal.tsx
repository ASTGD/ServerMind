import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { X, Eye, EyeOff, Loader2 } from "lucide-react"
import { createServer, type ServerCreateBody } from "@/api/servers"
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

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    mutation.mutate(form)
  }

  const isSSH = form.connection_type === "ssh"
  const credLabel = form.auth_type === "key" ? "Private Key (PEM)" : "Password"
  const credPlaceholder = form.auth_type === "key" ? "-----BEGIN OPENSSH PRIVATE KEY-----\n..." : "Server password"

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
          {/* Name + Connection type */}
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
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

            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Connection Type
              </label>
              <select
                value={form.connection_type}
                onChange={(e) => set("connection_type", e.target.value as ServerCreateBody["connection_type"])}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
              >
                <option value="ssh">SSH (Linux/Unix)</option>
                <option value="winrm">WinRM (Windows)</option>
                <option value="hosting">Hosting Panel</option>
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">
                Auth Type
              </label>
              <select
                value={form.auth_type}
                onChange={(e) => set("auth_type", e.target.value as "password" | "key")}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:border-primary focus:outline-none"
              >
                <option value="password">Password</option>
                <option value="key">SSH Key</option>
              </select>
            </div>
          </div>

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
              Add Server
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

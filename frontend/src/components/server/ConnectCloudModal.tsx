import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { X, Eye, EyeOff, Loader2, Cloud, ShieldCheck, CheckCircle2, RefreshCw } from "lucide-react"
import {
  connectCloudAccount,
  listCloudInstances,
  importCloudInstances,
  type CloudAccount,
  type CloudInstance,
  type ImportResult,
} from "@/api/cloud"

interface Props {
  onClose: () => void
}

type Step = "connect" | "discover"

/**
 * Cloud Account flow (Assets Phase C): connect a provider account by API key → discover its
 * instances → import the chosen ones as assets. The provider API only LISTS machines — it
 * never hands over a login — so import needs one SSH username + key/password the user supplies,
 * applied to the whole batch (editable per-asset afterwards). AWS first; more providers later.
 */
export default function ConnectCloudModal({ onClose }: Props) {
  const qc = useQueryClient()
  const [step, setStep] = useState<Step>("connect")
  const [account, setAccount] = useState<CloudAccount | null>(null)

  // ── Connect form ──────────────────────────────────────────────────────────
  const [label, setLabel] = useState("")
  const [accessKeyId, setAccessKeyId] = useState("")
  const [secretKey, setSecretKey] = useState("")
  const [region, setRegion] = useState("")
  const [showSecret, setShowSecret] = useState(false)
  const [connectError, setConnectError] = useState<string | null>(null)

  const connectMut = useMutation({
    mutationFn: () =>
      connectCloudAccount({
        provider: "aws",
        label: label.trim() || "AWS account",
        credential: { access_key_id: accessKeyId.trim(), secret_access_key: secretKey, region: region.trim() },
      }),
    onSuccess: (acc) => {
      setAccount(acc)
      setStep("discover")
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setConnectError(msg ?? "Could not connect. Check the key and try again.")
    },
  })

  // ── Discover ──────────────────────────────────────────────────────────────
  const instancesQ = useQuery<CloudInstance[]>({
    queryKey: ["cloud-instances", account?.id],
    queryFn: () => listCloudInstances(account!.id),
    enabled: step === "discover" && !!account,
  })
  const instances = instancesQ.data ?? []
  const importable = instances.filter((i) => !i.already_imported)

  const [selected, setSelected] = useState<Set<string>>(new Set())
  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }
  const allSelected = importable.length > 0 && importable.every((i) => selected.has(i.instance_id))
  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(importable.map((i) => i.instance_id)))
  }

  // ── Import ────────────────────────────────────────────────────────────────
  const [username, setUsername] = useState("ec2-user")
  const [authType, setAuthType] = useState<"password" | "key">("key")
  const [credential, setCredential] = useState("")
  const [usePrivateIp, setUsePrivateIp] = useState(false)
  const [showCred, setShowCred] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [importError, setImportError] = useState<string | null>(null)

  const importMut = useMutation({
    mutationFn: () =>
      importCloudInstances(account!.id, {
        instance_ids: [...selected],
        username: username.trim(),
        auth_type: authType,
        credential,
        use_private_ip: usePrivateIp,
      }),
    onSuccess: (res) => {
      setResult(res)
      qc.invalidateQueries({ queryKey: ["servers"] })
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setImportError(msg ?? "Import failed. Please try again.")
    },
  })

  const inputCls =
    "w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
  const labelCls = "mb-1 block text-xs font-medium text-muted-foreground"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-xl border border-border bg-card shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="flex items-center gap-2 font-semibold text-foreground">
            <Cloud size={17} className="text-primary" />
            {step === "connect" ? "Connect a cloud account" : `Import from ${account?.label}`}
          </h2>
          <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:text-foreground">
            <X size={16} />
          </button>
        </div>

        {/* ── STEP 1: Connect ─────────────────────────────────────────────── */}
        {step === "connect" && (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              setConnectError(null)
              connectMut.mutate()
            }}
            className="space-y-4 overflow-y-auto p-5"
          >
            <div>
              <label className={labelCls}>Provider</label>
              <div className="inline-flex items-center gap-2 rounded-md border border-primary bg-primary/10 px-3 py-2 text-sm font-medium text-primary">
                <Cloud size={15} /> Amazon Web Services (EC2)
              </div>
              <p className="mt-1 text-xs text-muted-foreground">Google Cloud, Azure, Hetzner &amp; DigitalOcean coming next.</p>
            </div>

            <div>
              <label className={labelCls}>Account name</label>
              <input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="My AWS account" className={inputCls} />
            </div>

            <div>
              <label className={labelCls}>Access Key ID</label>
              <input
                required
                value={accessKeyId}
                onChange={(e) => setAccessKeyId(e.target.value)}
                placeholder="AKIA..."
                autoComplete="off"
                className={`${inputCls} font-mono`}
              />
            </div>

            <div>
              <label className={labelCls}>Secret Access Key</label>
              <div className="relative">
                <input
                  required
                  type={showSecret ? "text" : "password"}
                  value={secretKey}
                  onChange={(e) => setSecretKey(e.target.value)}
                  placeholder="Your AWS secret access key"
                  autoComplete="off"
                  className={`${inputCls} pr-10 font-mono`}
                />
                <button
                  type="button"
                  onClick={() => setShowSecret((v) => !v)}
                  className="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground"
                >
                  {showSecret ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <div>
              <label className={labelCls}>Region (optional)</label>
              <input value={region} onChange={(e) => setRegion(e.target.value)} placeholder="us-east-1 — leave blank to scan all regions" className={inputCls} />
            </div>

            <div className="flex items-start gap-2 rounded-md border border-border bg-muted/40 px-3 py-2.5 text-xs text-muted-foreground">
              <ShieldCheck size={15} className="mt-0.5 shrink-0 text-primary" />
              <span>
                Use a <strong className="text-foreground">read-only</strong> IAM key. It only needs
                <code className="mx-1 rounded bg-background px-1">sts:GetCallerIdentity</code> and
                <code className="mx-1 rounded bg-background px-1">ec2:DescribeInstances</code>. We store it encrypted (AES-256-GCM) and only use it to list your instances.
              </span>
            </div>

            {connectError && (
              <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{connectError}</p>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <button type="button" onClick={onClose} className="rounded-md px-4 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground">
                Cancel
              </button>
              <button
                type="submit"
                disabled={connectMut.isPending}
                className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {connectMut.isPending && <Loader2 size={14} className="animate-spin" />}
                Connect &amp; discover
              </button>
            </div>
          </form>
        )}

        {/* ── STEP 2: Discover + import ───────────────────────────────────── */}
        {step === "discover" && (
          <div className="flex min-h-0 flex-1 flex-col">
            {result ? (
              <div className="flex flex-col items-center gap-3 p-8 text-center">
                <CheckCircle2 size={40} className="text-green-500" />
                <p className="text-lg font-semibold text-foreground">
                  Imported {result.imported} {result.imported === 1 ? "asset" : "assets"}
                </p>
                {(result.skipped > 0 || result.detail) && (
                  <p className="text-sm text-muted-foreground">
                    {result.skipped > 0 && `${result.skipped} skipped`}
                    {result.detail && ` — ${result.detail}`}
                  </p>
                )}
                <button onClick={onClose} className="mt-2 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">
                  Done
                </button>
              </div>
            ) : (
              <>
                <div className="min-h-0 flex-1 overflow-y-auto px-5 pt-4">
                  {instancesQ.isLoading ? (
                    <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground">
                      <Loader2 size={16} className="animate-spin" /> Discovering instances…
                    </div>
                  ) : instancesQ.isError ? (
                    <div className="flex flex-col items-center gap-3 py-14 text-center">
                      <p className="text-sm text-destructive">
                        {(instancesQ.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
                          "Could not list instances."}
                      </p>
                      <button onClick={() => instancesQ.refetch()} className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-accent">
                        <RefreshCw size={13} /> Retry
                      </button>
                    </div>
                  ) : instances.length === 0 ? (
                    <div className="py-16 text-center text-sm text-muted-foreground">
                      No instances found in this account.
                    </div>
                  ) : (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-border text-left text-xs text-muted-foreground">
                          <th className="w-8 pb-2">
                            <input type="checkbox" checked={allSelected} onChange={toggleAll} disabled={importable.length === 0} aria-label="Select all" />
                          </th>
                          <th className="pb-2 font-medium">Name</th>
                          <th className="pb-2 font-medium">OS</th>
                          <th className="pb-2 font-medium">State</th>
                          <th className="pb-2 font-medium">Public IP</th>
                          <th className="pb-2 font-medium">Region</th>
                        </tr>
                      </thead>
                      <tbody>
                        {instances.map((i) => (
                          <tr
                            key={i.instance_id}
                            className={`border-b border-border/60 ${i.already_imported ? "opacity-50" : "cursor-pointer hover:bg-accent/50"}`}
                            onClick={() => !i.already_imported && toggle(i.instance_id)}
                          >
                            <td className="py-2">
                              <input
                                type="checkbox"
                                checked={selected.has(i.instance_id)}
                                disabled={i.already_imported}
                                onChange={() => toggle(i.instance_id)}
                                onClick={(e) => e.stopPropagation()}
                                aria-label={`Select ${i.name}`}
                              />
                            </td>
                            <td className="py-2">
                              <span className="font-medium text-foreground">{i.name}</span>
                              {i.already_imported && (
                                <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">Imported</span>
                              )}
                              <div className="font-mono text-[10px] text-muted-foreground">{i.instance_id}</div>
                            </td>
                            <td className="py-2 capitalize text-muted-foreground">{i.os}</td>
                            <td className="py-2">
                              <span className={i.state === "running" ? "text-green-500" : "text-muted-foreground"}>{i.state}</span>
                            </td>
                            <td className="py-2 font-mono text-xs text-muted-foreground">{i.public_ip ?? "—"}</td>
                            <td className="py-2 text-xs text-muted-foreground">{i.region ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>

                {/* Batch credential — applied to every imported asset */}
                {importable.length > 0 && (
                  <div className="border-t border-border bg-muted/30 p-5">
                    <p className="mb-3 text-xs text-muted-foreground">
                      AWS doesn't share instance logins, so set the SSH login for the{" "}
                      <strong className="text-foreground">{selected.size}</strong> selected — you can adjust each asset later.
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className={labelCls}>Username</label>
                        <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="ec2-user / ubuntu / root" className={inputCls} />
                      </div>
                      <div>
                        <label className={labelCls}>Auth type</label>
                        <select value={authType} onChange={(e) => setAuthType(e.target.value as "password" | "key")} className={inputCls}>
                          <option value="key">SSH Key</option>
                          <option value="password">Password</option>
                        </select>
                      </div>
                    </div>
                    <div className="mt-3">
                      <label className={labelCls}>{authType === "key" ? "Private Key (PEM)" : "Password"}</label>
                      <div className="relative">
                        {authType === "key" ? (
                          <textarea
                            value={credential}
                            onChange={(e) => setCredential(e.target.value)}
                            placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;..."
                            rows={3}
                            className={`${inputCls} resize-none font-mono text-xs`}
                          />
                        ) : (
                          <input
                            type={showCred ? "text" : "password"}
                            value={credential}
                            onChange={(e) => setCredential(e.target.value)}
                            placeholder="SSH password"
                            autoComplete="off"
                            className={`${inputCls} pr-10`}
                          />
                        )}
                        {authType === "password" && (
                          <button type="button" onClick={() => setShowCred((v) => !v)} className="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground">
                            {showCred ? <EyeOff size={15} /> : <Eye size={15} />}
                          </button>
                        )}
                      </div>
                    </div>
                    <label className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                      <input type="checkbox" checked={usePrivateIp} onChange={(e) => setUsePrivateIp(e.target.checked)} />
                      Connect over the private IP (use inside a VPN / same VPC)
                    </label>

                    {importError && <p className="mt-3 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">{importError}</p>}

                    <div className="mt-4 flex justify-end gap-2">
                      <button onClick={onClose} className="rounded-md px-4 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground">
                        Cancel
                      </button>
                      <button
                        onClick={() => {
                          setImportError(null)
                          importMut.mutate()
                        }}
                        disabled={importMut.isPending || selected.size === 0 || !credential.trim() || !username.trim()}
                        className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                      >
                        {importMut.isPending && <Loader2 size={14} className="animate-spin" />}
                        Import {selected.size > 0 ? selected.size : ""} selected
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

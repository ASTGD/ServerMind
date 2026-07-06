import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { X, Loader2, RefreshCw, CheckCircle2, Cloud, Eye, EyeOff, Trash2 } from "lucide-react"
import {
  listCloudInstances,
  importCloudInstances,
  deleteCloudAccount,
  type CloudAccount,
  type CloudInstance,
  type ImportResult,
} from "@/api/cloud"

interface Props {
  account: CloudAccount
  onClose: () => void
}

/** Manage a connected cloud account (Assets Phase 1 rail): re-discover its instances, import
 *  the ones you don't have yet, or disconnect. Reuses the same import flow as the connect
 *  modal — the account already exists, so we skip straight to discover. */
export default function CloudAccountModal({ account, onClose }: Props) {
  const qc = useQueryClient()
  const instancesQ = useQuery<CloudInstance[]>({
    queryKey: ["cloud-instances", account.id],
    queryFn: () => listCloudInstances(account.id),
  })
  const instances = instancesQ.data ?? []
  const importable = instances.filter((i) => !i.already_imported)

  const [selected, setSelected] = useState<Set<string>>(new Set())
  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })

  const [username, setUsername] = useState(account.provider === "aws" ? "ec2-user" : "root")
  const [authType, setAuthType] = useState<"password" | "key">("key")
  const [credential, setCredential] = useState("")
  const [showCred, setShowCred] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const importMut = useMutation({
    mutationFn: () =>
      importCloudInstances(account.id, {
        instance_ids: [...selected],
        username: username.trim(),
        auth_type: authType,
        credential,
        use_private_ip: false,
      }),
    onSuccess: (res) => {
      setResult(res)
      qc.invalidateQueries({ queryKey: ["servers"] })
      qc.invalidateQueries({ queryKey: ["cloud-instances", account.id] })
    },
  })

  const deleteMut = useMutation({
    mutationFn: () => deleteCloudAccount(account.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cloud-accounts"] })
      qc.invalidateQueries({ queryKey: ["servers"] })
      onClose()
    },
  })

  const inputCls =
    "w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-xl border border-border bg-card shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="flex items-center gap-2 font-semibold text-foreground">
            <Cloud size={17} className="text-primary" /> {account.label}
            <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium uppercase text-muted-foreground">{account.provider}</span>
          </h2>
          <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:text-foreground">
            <X size={16} />
          </button>
        </div>

        {result ? (
          <div className="flex flex-col items-center gap-3 p-8 text-center">
            <CheckCircle2 size={40} className="text-green-500" />
            <p className="text-lg font-semibold text-foreground">Imported {result.imported} {result.imported === 1 ? "asset" : "assets"}</p>
            {result.skipped > 0 && <p className="text-sm text-muted-foreground">{result.skipped} skipped{result.detail ? ` — ${result.detail}` : ""}</p>}
            <button onClick={onClose} className="mt-2 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90">Done</button>
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 overflow-y-auto px-5 pt-4">
              {instancesQ.isLoading ? (
                <div className="flex items-center justify-center gap-2 py-16 text-sm text-muted-foreground"><Loader2 size={16} className="animate-spin" /> Loading instances…</div>
              ) : instancesQ.isError ? (
                <div className="flex flex-col items-center gap-3 py-14 text-center">
                  <p className="text-sm text-destructive">
                    {(instancesQ.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Could not list instances."}
                  </p>
                  <button onClick={() => instancesQ.refetch()} className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-foreground hover:bg-accent"><RefreshCw size={13} /> Retry</button>
                </div>
              ) : instances.length === 0 ? (
                <div className="py-16 text-center text-sm text-muted-foreground">No instances found in this account.</div>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="w-8 pb-2"></th>
                      <th className="pb-2 font-medium">Name</th>
                      <th className="pb-2 font-medium">OS</th>
                      <th className="pb-2 font-medium">State</th>
                      <th className="pb-2 font-medium">Public IP</th>
                    </tr>
                  </thead>
                  <tbody>
                    {instances.map((i) => (
                      <tr key={i.instance_id} className={`border-b border-border/60 ${i.already_imported ? "opacity-50" : "cursor-pointer hover:bg-accent/50"}`} onClick={() => !i.already_imported && toggle(i.instance_id)}>
                        <td className="py-2"><input type="checkbox" checked={selected.has(i.instance_id)} disabled={i.already_imported} onChange={() => toggle(i.instance_id)} onClick={(e) => e.stopPropagation()} aria-label={`Select ${i.name}`} /></td>
                        <td className="py-2"><span className="font-medium text-foreground">{i.name}</span>{i.already_imported && <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">Imported</span>}</td>
                        <td className="py-2 capitalize text-muted-foreground">{i.os}</td>
                        <td className="py-2"><span className={["running", "active"].includes(i.state) ? "text-green-500" : "text-muted-foreground"}>{i.state}</span></td>
                        <td className="py-2 font-mono text-xs text-muted-foreground">{i.public_ip ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            {importable.length > 0 && (
              <div className="border-t border-border bg-muted/30 p-5">
                <p className="mb-3 text-xs text-muted-foreground">Set the SSH login for the <strong className="text-foreground">{selected.size}</strong> selected — you can adjust each asset later.</p>
                <div className="grid grid-cols-2 gap-3">
                  <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="ec2-user / ubuntu / root" className={inputCls} />
                  <select value={authType} onChange={(e) => setAuthType(e.target.value as "password" | "key")} className={inputCls}>
                    <option value="key">SSH Key</option>
                    <option value="password">Password</option>
                  </select>
                </div>
                <div className="relative mt-3">
                  {authType === "key" ? (
                    <textarea value={credential} onChange={(e) => setCredential(e.target.value)} placeholder="-----BEGIN OPENSSH PRIVATE KEY-----&#10;..." rows={3} className={`${inputCls} resize-none font-mono text-xs`} />
                  ) : (
                    <input type={showCred ? "text" : "password"} value={credential} onChange={(e) => setCredential(e.target.value)} placeholder="SSH password" autoComplete="off" className={`${inputCls} pr-10`} />
                  )}
                  {authType === "password" && (
                    <button type="button" onClick={() => setShowCred((v) => !v)} className="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground">{showCred ? <EyeOff size={15} /> : <Eye size={15} />}</button>
                  )}
                </div>
                <div className="mt-4 flex items-center justify-between">
                  <button onClick={() => (confirmDelete ? deleteMut.mutate() : setConfirmDelete(true))} className="flex items-center gap-1.5 text-sm text-destructive hover:underline">
                    <Trash2 size={14} /> {confirmDelete ? "Click again to disconnect" : "Disconnect"}
                  </button>
                  <button onClick={() => importMut.mutate()} disabled={importMut.isPending || selected.size === 0 || !credential.trim() || !username.trim()} className="flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                    {importMut.isPending && <Loader2 size={14} className="animate-spin" />} Import {selected.size > 0 ? selected.size : ""} selected
                  </button>
                </div>
              </div>
            )}
            {importable.length === 0 && !instancesQ.isLoading && (
              <div className="flex items-center justify-between border-t border-border p-5">
                <button onClick={() => (confirmDelete ? deleteMut.mutate() : setConfirmDelete(true))} className="flex items-center gap-1.5 text-sm text-destructive hover:underline">
                  <Trash2 size={14} /> {confirmDelete ? "Click again to disconnect" : "Disconnect account"}
                </button>
                <button onClick={onClose} className="rounded-md px-4 py-2 text-sm text-muted-foreground hover:bg-accent">Close</button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

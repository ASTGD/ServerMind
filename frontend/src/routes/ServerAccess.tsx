import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useOutletContext } from "react-router-dom"
import {
  ShieldCheck, ShieldOff, Loader2, Plus, Trash2, KeyRound, Lock, Info, X,
} from "lucide-react"
import {
  getFirewall, addFirewallRule, removeFirewallRule, toggleFirewall,
  getSshKeys, addSshKey, removeSshKey,
  type FirewallRule, type SshKey,
} from "@/api/access"
import type { Server } from "@/types"
import { Button, EmptyState } from "@/components/ui"
import { cn } from "@/lib/utils"

const detail = (e: unknown) =>
  (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail

const inputCls =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none " +
  "focus:border-primary"

/** A refusal from the lockout guard. Explained, not shown as a failure. */
function Refusal({ text, onClose }: { text: string; onClose: () => void }) {
  return (
    <div className="mt-3 flex items-start gap-2 rounded-lg border-l-2 border-amber-500
                    bg-amber-500/10 px-3 py-2">
      <Lock size={14} className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
      <p className="flex-1 text-[12.5px] text-amber-900 dark:text-amber-200">{text}</p>
      <button onClick={onClose} className="text-amber-700 dark:text-amber-300">
        <X size={13} />
      </button>
    </div>
  )
}

function FirewallPanel({ serverId }: { serverId: string }) {
  const qc = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState({ action: "allow", port: "", protocol: "tcp",
                                     source: "", comment: "" })
  const [refused, setRefused] = useState("")
  const [confirmOff, setConfirmOff] = useState(false)

  const q = useQuery({ queryKey: ["firewall", serverId], queryFn: () => getFirewall(serverId) })
  const set = (data: unknown) => qc.setQueryData(["firewall", serverId], data)
  const onErr = (e: unknown) => setRefused(detail(e) || "That did not work.")

  const add = useMutation({
    mutationFn: () => addFirewallRule(serverId, form),
    onSuccess: (d) => { set(d); setAdding(false); setRefused("")
                        setForm({ action: "allow", port: "", protocol: "tcp",
                                  source: "", comment: "" }) },
    onError: onErr,
  })
  const remove = useMutation({
    mutationFn: (r: FirewallRule) => removeFirewallRule(serverId, r),
    onSuccess: (d) => { set(d); setRefused("") }, onError: onErr,
  })
  const toggle = useMutation({
    mutationFn: (on: boolean) => toggleFirewall(serverId, on),
    onSuccess: (d) => { set(d); setRefused(""); setConfirmOff(false) }, onError: onErr,
  })

  if (q.isLoading) {
    return <div className="flex justify-center py-10">
      <Loader2 className="animate-spin text-muted-foreground" /></div>
  }
  if (q.isError) {
    return <p className="text-[13px] text-muted-foreground">
      Could not read the firewall on this server. {detail(q.error)}</p>
  }
  const fwState = q.data!
  const busy = add.isPending || remove.isPending || toggle.isPending

  return (
    <section className="rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-h3 text-foreground">
            {fwState.active
              ? <ShieldCheck size={16} className="text-emerald-600 dark:text-emerald-400" />
              : <ShieldOff size={16} className="text-amber-600 dark:text-amber-400" />}
            Firewall
          </h2>
          <p className="mt-1 text-[12.5px] text-muted-foreground">
            {fwState.active
              ? `On, using ${fwState.manager}. Only what is listed below can reach this server.`
              : "Off. Everything a program listens on is reachable from the internet."}
          </p>
        </div>
        {fwState.manageable && (
          <div className="flex gap-2">
            {fwState.active
              ? <Button size="sm" variant="outline" disabled={busy}
                  onClick={() => confirmOff ? toggle.mutate(false) : setConfirmOff(true)}>
                  {confirmOff ? "Turn it off — sure?" : "Turn off"}
                </Button>
              : <Button size="sm" disabled={busy} onClick={() => toggle.mutate(true)}>
                  Turn on
                </Button>}
            {!adding && <Button size="sm" onClick={() => setAdding(true)}>
              <Plus size={13} />Open a port</Button>}
          </div>
        )}
      </div>

      {fwState.note && (
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-muted/50 px-3 py-2
                      text-[12px] text-muted-foreground">
          <Info size={13} className="mt-0.5 shrink-0" />{fwState.note}
        </p>
      )}
      {refused && <Refusal text={refused} onClose={() => setRefused("")} />}

      {adding && (
        <div className="mt-3 rounded-lg border border-border p-3">
          <div className="grid gap-2 sm:grid-cols-[110px_1fr_100px_1fr_auto]">
            <select value={form.action} className={inputCls}
              onChange={(e) => setForm({ ...form, action: e.target.value })}>
              <option value="allow">Open</option>
              <option value="deny">Block</option>
            </select>
            <input value={form.port} placeholder="port, e.g. 443" className={inputCls}
              onChange={(e) => setForm({ ...form, port: e.target.value })} />
            <select value={form.protocol} className={inputCls}
              onChange={(e) => setForm({ ...form, protocol: e.target.value })}>
              <option value="tcp">TCP</option>
              <option value="udp">UDP</option>
            </select>
            <input value={form.source} placeholder="from anywhere, or 10.0.0.0/24"
              className={inputCls}
              onChange={(e) => setForm({ ...form, source: e.target.value })} />
            <div className="flex gap-2">
              <Button size="sm" disabled={!form.port || busy} onClick={() => add.mutate()}>
                {add.isPending && <Loader2 size={13} className="animate-spin" />}Add
              </Button>
              <Button size="sm" variant="ghost"
                onClick={() => { setAdding(false); setRefused("") }}>Cancel</Button>
            </div>
          </div>
        </div>
      )}

      {!fwState.rules.length
        ? <p className="mt-4 text-[13px] text-muted-foreground">No rules to show.</p>
        : <ul className="mt-4 divide-y divide-border">
            {fwState.rules.map((r, i) => (
              <li key={`${r.index ?? "x"}-${r.port}-${r.protocol}-${r.source}-${i}`}
                  className="flex items-center gap-3 py-2">
                <span className={cn("h-2 w-2 shrink-0 rounded-full",
                  r.action === "allow" ? "bg-emerald-500" : "bg-red-500")} />
                <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">
                  {r.describes}
                </span>
                <span className="shrink-0 font-mono text-[11.5px] text-muted-foreground">
                  {/* A named service can have no port we know of; "/tcp" on its own
                      says nothing and looks like a rendering fault. */}
                  {r.port ? `${r.port}/${r.protocol}` : ""}
                </span>
                {r.protected
                  // Disabled rather than absent: a missing button looks like a bug,
                  // and the reason is the thing worth showing.
                  ? <span title={`This keeps SSH open on port ${fwState.ssh_port}.`}
                      className="flex shrink-0 items-center gap-1 text-[11.5px]
                                 text-muted-foreground">
                      <Lock size={12} />protected
                    </span>
                  : fwState.manageable && (
                      <button disabled={busy} onClick={() => remove.mutate(r)}
                        className="shrink-0 text-muted-foreground hover:text-red-500
                                   disabled:opacity-40">
                        <Trash2 size={14} />
                      </button>)}
              </li>
            ))}
          </ul>}

      {fwState.our_ip && (
        <p className="mt-3 text-[11.5px] text-muted-foreground">
          ServerAlly reaches this server from {fwState.our_ip}, on port {fwState.ssh_port}.
          A change that would close that is refused.
        </p>
      )}
    </section>
  )
}

function KeysPanel({ serverId }: { serverId: string }) {
  const qc = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [key, setKey] = useState("")
  const [label, setLabel] = useState("")
  const [refused, setRefused] = useState("")
  const [confirm, setConfirm] = useState<string | null>(null)

  const q = useQuery({ queryKey: ["ssh-keys", serverId],
                       queryFn: () => getSshKeys(serverId) })
  const set = (d: unknown) => qc.setQueryData(["ssh-keys", serverId], d)
  const onErr = (e: unknown) => setRefused(detail(e) || "That did not work.")

  const add = useMutation({
    mutationFn: () => addSshKey(serverId, key, label),
    onSuccess: (d) => { set(d); setAdding(false); setKey(""); setLabel(""); setRefused("") },
    onError: onErr,
  })
  const remove = useMutation({
    mutationFn: (fp: string) => removeSshKey(serverId, fp),
    onSuccess: (d) => { set(d); setRefused(""); setConfirm(null) }, onError: onErr,
  })

  if (q.isLoading) {
    return <div className="flex justify-center py-10">
      <Loader2 className="animate-spin text-muted-foreground" /></div>
  }
  if (q.isError) {
    return <p className="text-[13px] text-muted-foreground">
      Could not read the keys on this server. {detail(q.error)}</p>
  }
  const data = q.data!
  const busy = add.isPending || remove.isPending

  return (
    <section className="rounded-xl border border-border bg-card p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-h3 text-foreground">
            <KeyRound size={16} className="text-primary" />
            Who can sign in
          </h2>
          <p className="mt-1 text-[12.5px] text-muted-foreground">
            Keys that can sign in as <strong>{data.user}</strong>. Anyone holding the
            matching private key has full access to this server as that user.
          </p>
        </div>
        {!adding && <Button size="sm" onClick={() => setAdding(true)}>
          <Plus size={13} />Add a key</Button>}
      </div>

      {data.note && (
        <p className="mt-3 flex items-start gap-2 rounded-lg bg-amber-500/10 px-3 py-2
                      text-[12px] text-amber-900 dark:text-amber-200">
          <Info size={13} className="mt-0.5 shrink-0" />{data.note}
        </p>
      )}
      {refused && <Refusal text={refused} onClose={() => setRefused("")} />}

      {adding && (
        <div className="mt-3 space-y-2 rounded-lg border border-border p-3">
          <textarea value={key} onChange={(e) => setKey(e.target.value)} rows={3}
            placeholder="ssh-ed25519 AAAAC3Nza… name@computer"
            className={cn(inputCls, "font-mono text-[12px]")} />
          <p className="text-[12px] text-muted-foreground">
            This is the <strong>public</strong> half — usually the file ending in
            <code className="mx-1 font-mono">.pub</code>. Never paste a private key
            anywhere.
          </p>
          <div className="flex flex-wrap gap-2">
            <input value={label} onChange={(e) => setLabel(e.target.value)}
              placeholder="Whose key is this? (optional)"
              className={cn(inputCls, "sm:w-72")} />
            <Button size="sm" disabled={!key.trim() || busy} onClick={() => add.mutate()}>
              {add.isPending && <Loader2 size={13} className="animate-spin" />}Add key
            </Button>
            <Button size="sm" variant="ghost"
              onClick={() => { setAdding(false); setRefused("") }}>Cancel</Button>
          </div>
        </div>
      )}

      {!data.keys.length
        ? <EmptyState
            icon={KeyRound} className="mt-4 py-10"
            title="No keys on this server"
            description={data.auth_type === "password"
              ? "Sign-in is by password. Adding a key is safer — a password can be guessed."
              : "Nothing can sign in with a key as this user."} />
        : <ul className="mt-4 divide-y divide-border">
            {data.keys.map((k: SshKey) => (
              <li key={k.fingerprint} className="flex items-center gap-3 py-2">
                <KeyRound size={14} className="shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] text-foreground">
                    {k.label}
                    {k.is_ours && (
                      <span className="ml-2 rounded bg-primary/10 px-1.5 py-0.5
                                       text-[11px] text-primary">ServerAlly uses this</span>
                    )}
                    {k.options && (
                      <span className="ml-2 rounded bg-muted px-1.5 py-0.5 font-mono
                                       text-[10.5px] text-muted-foreground"
                            title={k.options}>restricted</span>
                    )}
                  </p>
                  <p className="truncate font-mono text-[11px] text-muted-foreground">
                    {k.fingerprint}
                  </p>
                </div>
                {k.protected
                  ? <span className="flex shrink-0 items-center gap-1 text-[11.5px]
                                     text-muted-foreground">
                      <Lock size={12} />protected
                    </span>
                  : <button disabled={busy}
                      onClick={() => confirm === k.fingerprint
                        ? remove.mutate(k.fingerprint) : setConfirm(k.fingerprint)}
                      className={cn("shrink-0 text-[12px] disabled:opacity-40",
                        confirm === k.fingerprint
                          ? "text-red-600 dark:text-red-400"
                          : "text-muted-foreground hover:text-red-500")}>
                      {confirm === k.fingerprint
                        ? "Remove — sure?" : <Trash2 size={14} />}
                    </button>}
              </li>
            ))}
          </ul>}
    </section>
  )
}

export default function ServerAccess() {
  const { server } = useOutletContext<{ server: Server }>()
  if (server.connection_type !== "ssh") {
    return <p className="text-[13px] text-muted-foreground">
      This works on servers ServerAlly connects to over SSH.</p>
  }
  return (
    <div className="space-y-4">
      <FirewallPanel serverId={server.id} />
      <KeysPanel serverId={server.id} />
    </div>
  )
}

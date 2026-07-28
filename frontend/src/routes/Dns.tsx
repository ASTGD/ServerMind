import { useEffect, useMemo, useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Globe2, Loader2, Plus, Trash2, Lock, TriangleAlert, CircleCheck, Link2Off, X,
} from "lucide-react"
import {
  listDnsAccounts, connectDns, disconnectDns, listZones, listRecords,
  createRecord, updateRecord, deleteRecord, checkRecord,
  type DnsRecord, type RecordInput,
} from "@/api/dns"
import { Button, EmptyState } from "@/components/ui"
import { cn } from "@/lib/utils"

const TYPES = ["A", "AAAA", "CNAME", "TXT", "MX", "SRV", "CAA"]

function ConnectForm({ onDone }: { onDone: () => void }) {
  const [label, setLabel] = useState("")
  const [token, setToken] = useState("")
  const connect = useMutation({
    mutationFn: () => connectDns({ provider: "cloudflare", label, api_token: token }),
    onSuccess: onDone,
  })
  const err = (connect.error as { response?: { data?: { detail?: string } } })
    ?.response?.data?.detail

  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <h2 className="text-h3 text-foreground">Connect Cloudflare</h2>
      <p className="mt-1 text-[12.5px] text-muted-foreground">
        Create an API token in Cloudflare with <strong>Zone:Read</strong> and{" "}
        <strong>DNS:Edit</strong>. We check it works before saving it, and it is
        encrypted — it is never shown again.
      </p>
      <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_2fr_auto]">
        <input value={label} onChange={(e) => setLabel(e.target.value)}
          placeholder="My Cloudflare"
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary" />
        <input value={token} onChange={(e) => setToken(e.target.value)}
          type="password" placeholder="API token"
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary" />
        <Button disabled={!label || token.length < 8 || connect.isPending}
          onClick={() => connect.mutate()}>
          {connect.isPending ? <Loader2 size={14} className="animate-spin" /> : null}
          Connect
        </Button>
      </div>
      {err && <p className="mt-2 text-[12.5px] text-red-600 dark:text-red-400">{err}</p>}
    </div>
  )
}

function RecordForm({
  zone, initial, onSave, onCancel, saving,
}: {
  zone: string
  initial?: DnsRecord
  onSave: (r: RecordInput) => void
  onCancel: () => void
  saving: boolean
}) {
  const [type, setType] = useState(initial?.type ?? "A")
  const [name, setName] = useState(initial?.name ?? "")
  const [content, setContent] = useState(initial?.content ?? "")
  const [ttl, setTtl] = useState(initial?.ttl ?? 300)
  const [priority, setPriority] = useState<number | null>(initial?.priority ?? null)
  const [check, setCheck] = useState<{ ok: boolean; error: string | null; warning: string | null } | null>(null)

  // Validate as they type. For DNS the objection has to arrive BEFORE the save —
  // afterwards the site is already down and the TTL keeps it down.
  useEffect(() => {
    if (!content.trim()) { setCheck(null); return }
    const t = setTimeout(() => {
      checkRecord({ type, name, content, zone, ttl, priority })
        .then(setCheck).catch(() => setCheck(null))
    }, 300)
    return () => clearTimeout(t)
  }, [type, name, content, zone, ttl, priority])

  return (
    <div className="rounded-xl border border-primary/40 bg-primary/[0.03] p-3">
      <div className="grid gap-2 sm:grid-cols-[110px_1fr_2fr_90px_auto]">
        <select value={type} onChange={(e) => setType(e.target.value)}
          className="rounded-lg border border-border bg-background px-2 py-2 text-sm outline-none focus:border-primary">
          {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <input value={name} onChange={(e) => setName(e.target.value)}
          placeholder="@ or www"
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary" />
        <input value={content} onChange={(e) => setContent(e.target.value)}
          placeholder={type === "A" ? "203.0.113.10" : type === "CNAME" ? "target.example.com" : "value"}
          className="rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary" />
        <input value={ttl} onChange={(e) => setTtl(Number(e.target.value) || 300)}
          type="number" placeholder="TTL"
          className="rounded-lg border border-border bg-background px-2 py-2 text-sm outline-none focus:border-primary" />
        <div className="flex gap-1">
          <Button size="sm" disabled={saving || check?.ok === false}
            onClick={() => onSave({ type, name, content, ttl, priority })}>
            {saving ? <Loader2 size={13} className="animate-spin" /> : null} Save
          </Button>
          <Button size="sm" variant="ghost" onClick={onCancel}><X size={13} /></Button>
        </div>
      </div>

      {type === "MX" && (
        <input value={priority ?? ""} onChange={(e) => setPriority(Number(e.target.value) || null)}
          type="number" placeholder="Priority (10 is usual)"
          className="mt-2 w-48 rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary" />
      )}

      {check?.error && (
        <p className="mt-2 flex items-start gap-1.5 text-[12.5px] text-red-600 dark:text-red-400">
          <TriangleAlert size={13} className="mt-0.5 shrink-0" /> {check.error}
        </p>
      )}
      {check?.ok && check.warning && (
        <p className="mt-2 flex items-start gap-1.5 text-[12.5px] text-amber-700 dark:text-amber-400">
          <TriangleAlert size={13} className="mt-0.5 shrink-0" /> {check.warning}
        </p>
      )}
      {check?.ok && !check.warning && (
        <p className="mt-2 flex items-center gap-1.5 text-[12.5px] text-emerald-600 dark:text-emerald-400">
          <CircleCheck size={13} /> Looks right.
        </p>
      )}
    </div>
  )
}

/**
 * DNS — read and change the records that decide where a domain points.
 *
 * The most dangerous screen in the product: a wrong A record takes a site offline
 * worldwide in seconds and the TTL keeps it down. So every value is checked as it is
 * typed, and the records that could hand the domain away (NS, SOA) are shown but never
 * editable here.
 */
export default function Dns() {
  const qc = useQueryClient()
  const [accountId, setAccountId] = useState<string>("")
  const [zoneId, setZoneId] = useState<string>("")
  const [adding, setAdding] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)

  const accounts = useQuery({ queryKey: ["dns-accounts"], queryFn: listDnsAccounts })
  const acct = accounts.data?.accounts?.find((a) => a.id === accountId)
    ?? accounts.data?.accounts?.[0]

  useEffect(() => {
    if (!accountId && acct) setAccountId(acct.id)
  }, [acct, accountId])

  const zones = useQuery({
    queryKey: ["dns-zones", acct?.id],
    queryFn: () => listZones(acct!.id),
    enabled: !!acct,
  })
  const zone = zones.data?.zones?.find((z) => z.id === zoneId) ?? zones.data?.zones?.[0]

  useEffect(() => {
    if (!zoneId && zone) setZoneId(zone.id)
  }, [zone, zoneId])

  const records = useQuery({
    queryKey: ["dns-records", acct?.id, zone?.id],
    queryFn: () => listRecords(acct!.id, zone!.id, zone!.name),
    enabled: !!acct && !!zone,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ["dns-records", acct?.id, zone?.id] })
  const add = useMutation({
    mutationFn: (r: RecordInput) => createRecord(acct!.id, zone!.id, zone!.name, r),
    onSuccess: () => { setAdding(false); invalidate() },
  })
  const edit = useMutation({
    mutationFn: ({ id, r }: { id: string; r: RecordInput }) =>
      updateRecord(acct!.id, zone!.id, zone!.name, id, r),
    onSuccess: () => { setEditing(null); invalidate() },
  })
  const del = useMutation({
    mutationFn: (id: string) => deleteRecord(acct!.id, zone!.id, zone!.name, id),
    onSuccess: invalidate,
  })

  const grouped = useMemo(() => {
    const rs = records.data?.records ?? []
    return [...rs].sort((a, b) =>
      a.type === b.type ? a.name.localeCompare(b.name) : a.type.localeCompare(b.type))
  }, [records.data])

  if (accounts.isLoading) return <p className="text-sm text-muted-foreground">Loading…</p>

  return (
    <div>
      <header className="mb-4">
        <h1 className="flex items-center gap-2 text-h1 text-foreground">
          <Globe2 className="h-5 w-5 text-primary" /> DNS
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Point your domains where you want them, without leaving ServerAlly.
        </p>
      </header>

      {!acct ? (
        <ConnectForm onDone={() => qc.invalidateQueries({ queryKey: ["dns-accounts"] })} />
      ) : (
        <>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <select value={acct.id} onChange={(e) => { setAccountId(e.target.value); setZoneId("") }}
              className="rounded-lg border border-border bg-background px-2 py-1.5 text-sm outline-none focus:border-primary">
              {accounts.data!.accounts.map((a) => (
                <option key={a.id} value={a.id}>{a.label}</option>
              ))}
            </select>
            {zones.data && zones.data.zones.length > 0 && (
              <select value={zone?.id ?? ""} onChange={(e) => setZoneId(e.target.value)}
                className="rounded-lg border border-border bg-background px-2 py-1.5 text-sm outline-none focus:border-primary">
                {zones.data.zones.map((z) => <option key={z.id} value={z.id}>{z.name}</option>)}
              </select>
            )}
            <div className="ml-auto flex gap-1.5">
              <Button size="sm" onClick={() => setAdding(true)} disabled={!zone}>
                <Plus size={14} /> Add record
              </Button>
              <Button size="sm" variant="ghost"
                onClick={() => disconnectDns(acct.id).then(() =>
                  qc.invalidateQueries({ queryKey: ["dns-accounts"] }))}>
                <Link2Off size={13} /> Disconnect
              </Button>
            </div>
          </div>

          {zones.isError && (
            <p className="mb-3 text-[13px] text-red-600 dark:text-red-400">
              Couldn&rsquo;t read your zones — check the token still has access.
            </p>
          )}
          {zones.data?.zones.length === 0 && (
            <EmptyState icon={Globe2} title="No domains in this account"
              description="Add a domain to Cloudflare first, then it will appear here." />
          )}

          {adding && zone && (
            <div className="mb-3">
              <RecordForm zone={zone.name} saving={add.isPending}
                onSave={(r) => add.mutate(r)} onCancel={() => setAdding(false)} />
              {(add.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail && (
                <p className="mt-1 text-[12.5px] text-red-600 dark:text-red-400">
                  {(add.error as { response?: { data?: { detail?: string } } }).response!.data!.detail}
                </p>
              )}
            </div>
          )}

          {records.isLoading ? (
            <p className="py-6 text-center text-sm text-muted-foreground">Loading records…</p>
          ) : (
            <ul className="space-y-1.5">
              {grouped.map((r) => (
                <li key={r.id}>
                  {editing === r.id && zone ? (
                    <RecordForm zone={zone.name} initial={r} saving={edit.isPending}
                      onSave={(body) => edit.mutate({ id: r.id, r: body })}
                      onCancel={() => setEditing(null)} />
                  ) : (
                    <div className={cn(
                      "flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card px-3 py-2",
                      !r.editable && "opacity-70",
                    )}>
                      <span className="w-14 shrink-0 text-[11px] font-semibold text-primary">
                        {r.type}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-[13.5px] text-foreground">
                        {r.name}
                      </span>
                      <span className="min-w-0 flex-[2] truncate font-mono text-[12.5px] text-muted-foreground">
                        {r.content}
                      </span>
                      <span className="w-14 shrink-0 text-right text-[11.5px] text-muted-foreground">
                        {r.ttl === 1 ? "auto" : r.ttl}
                      </span>
                      {r.editable ? (
                        <div className="flex shrink-0 gap-1">
                          <Button size="sm" variant="ghost" onClick={() => setEditing(r.id)}>
                            Edit
                          </Button>
                          <Button size="sm" variant="ghost" disabled={del.isPending}
                            onClick={() => del.mutate(r.id)}>
                            <Trash2 size={13} />
                          </Button>
                        </div>
                      ) : (
                        /* Shown, not editable. An owner needs to SEE their nameservers;
                           changing them here is how a domain leaves your control. */
                        <span className="flex shrink-0 items-center gap-1 text-[11px] text-muted-foreground"
                          title="Managed by your DNS provider">
                          <Lock size={11} /> provider
                        </span>
                      )}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  )
}

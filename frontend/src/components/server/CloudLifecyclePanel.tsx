import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  Loader2, Plus, Power, RotateCw, Trash2, TriangleAlert, Gauge, X,
} from "lucide-react"
import {
  getCloudCatalogue, createCloudInstance, cloudPower, previewCloudResize,
  cloudResize, destroyCloudInstance, listCloudInstances,
  type CloudAccount, type CloudInstance, type CloudSize, type ResizePlan,
} from "@/api/cloud"
import { Button } from "@/components/ui"
import { cn } from "@/lib/utils"

const detail = (e: unknown) =>
  (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail

const inputCls =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none " +
  "focus:border-primary"

const money = (s: CloudSize) =>
  s.price_monthly == null ? "" : `${s.price_monthly.toFixed(2)} ${s.currency}/mo`

/** Create a new server. The price is on screen before the button, because this is the
 *  one action in ServerAlly that starts charging the customer money. */
function CreateForm({ account, onDone }: { account: CloudAccount; onDone: () => void }) {
  const qc = useQueryClient()
  const cat = useQuery({ queryKey: ["cloud-catalogue", account.id],
                         queryFn: () => getCloudCatalogue(account.id) })
  const [f, setF] = useState({ name: "", region: "", size: "", image: "" })
  const [keys, setKeys] = useState<string[]>([])

  const create = useMutation({
    mutationFn: () => createCloudInstance(account.id, { ...f, ssh_keys: keys }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cloud-instances", account.id] })
      onDone()
    },
  })

  if (cat.isLoading) {
    return <div className="flex justify-center py-8">
      <Loader2 className="animate-spin text-muted-foreground" /></div>
  }
  if (cat.data && !cat.data.supported) {
    return <p className="rounded-lg bg-muted/50 px-3 py-2 text-[12.5px] text-muted-foreground">
      {cat.data.message}</p>
  }
  const c = cat.data
  if (!c) {
    return <p className="text-[12.5px] text-red-600 dark:text-red-400">
      Could not read what this account can build. {detail(cat.error)}</p>
  }

  const chosen = c.sizes.find((s) => s.slug === f.size)
  const ready = f.name && f.region && f.size && f.image

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="text-[12.5px] font-medium text-foreground">Name</span>
          <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })}
            placeholder="web-1" className={cn(inputCls, "mt-1")} />
        </label>
        <label className="block">
          <span className="text-[12.5px] font-medium text-foreground">Location</span>
          <select value={f.region} onChange={(e) => setF({ ...f, region: e.target.value })}
            className={cn(inputCls, "mt-1")}>
            <option value="">Choose…</option>
            {c.regions.filter((r) => r.available).map((r) => (
              <option key={r.slug} value={r.slug}>{r.label}</option>
            ))}
          </select>
        </label>
        <label className="block">
          <span className="text-[12.5px] font-medium text-foreground">Operating system</span>
          <select value={f.image} onChange={(e) => setF({ ...f, image: e.target.value })}
            className={cn(inputCls, "mt-1")}>
            <option value="">Choose…</option>
            {c.images.map((i) => <option key={i.slug} value={i.slug}>{i.label}</option>)}
          </select>
        </label>
        <label className="block">
          <span className="text-[12.5px] font-medium text-foreground">Size</span>
          <select value={f.size} onChange={(e) => setF({ ...f, size: e.target.value })}
            className={cn(inputCls, "mt-1")}>
            <option value="">Choose…</option>
            {c.sizes.filter((s) => s.available).map((s) => (
              <option key={s.slug} value={s.slug}>
                {s.label}{s.price_monthly != null ? ` — ${money(s)}` : ""}
              </option>
            ))}
          </select>
        </label>
      </div>

      {!!c.ssh_keys.length && (
        <div>
          <span className="text-[12.5px] font-medium text-foreground">
            SSH keys to allow in
          </span>
          <div className="mt-1 flex flex-wrap gap-2">
            {c.ssh_keys.map((k) => (
              <label key={k.id} className="flex items-center gap-1.5 rounded-lg border
                                           border-border px-2 py-1 text-[12.5px]">
                <input type="checkbox" checked={keys.includes(k.id)}
                  onChange={(e) => setKeys(e.target.checked
                    ? [...keys, k.id] : keys.filter((x) => x !== k.id))} />
                {k.label}
              </label>
            ))}
          </div>
          {!keys.length && (
            // Without a key the provider emails a root password instead; saying so beats
            // the customer discovering it when they cannot get in.
            <p className="mt-1 text-[12px] text-amber-700 dark:text-amber-400">
              With no key selected the provider will email a password instead. Choosing a
              key is safer.
            </p>
          )}
        </div>
      )}

      {chosen && (
        <p className="rounded-lg bg-primary/5 px-3 py-2 text-[12.5px] text-foreground">
          <strong>{chosen.label}</strong>
          {chosen.price_monthly != null && <> — about <strong>{money(chosen)}</strong>.
            Charging starts as soon as it exists and continues until it is deleted.</>}
        </p>
      )}
      {detail(create.error) && (
        <p className="text-[12.5px] text-red-600 dark:text-red-400">{detail(create.error)}</p>
      )}
      <div className="flex gap-2">
        <Button disabled={!ready || create.isPending} onClick={() => create.mutate()}>
          {create.isPending && <Loader2 size={14} className="animate-spin" />}
          Create server
        </Button>
        <Button variant="ghost" onClick={onDone}>Cancel</Button>
      </div>
    </div>
  )
}

/** Resize. The preview is fetched from the server so the wording about what is permanent
 *  comes from the same place that will enforce it. */
function ResizeBox({ account, inst, onClose }: {
  account: CloudAccount; inst: CloudInstance; onClose: () => void
}) {
  const qc = useQueryClient()
  const cat = useQuery({ queryKey: ["cloud-catalogue", account.id],
                         queryFn: () => getCloudCatalogue(account.id) })
  const [size, setSize] = useState("")
  const [growDisk, setGrowDisk] = useState(false)
  const [plan, setPlan] = useState<ResizePlan | null>(null)

  const preview = useMutation({
    mutationFn: () => previewCloudResize(account.id, inst.instance_id, size, growDisk),
    onSuccess: (r) => setPlan(r.plan),
  })
  const apply = useMutation({
    mutationFn: () => cloudResize(account.id, inst.instance_id, size, growDisk),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cloud-instances", account.id] })
      onClose()
    },
  })

  const sizes = (cat.data?.sizes ?? []).filter((s) => s.available && s.slug !== inst.instance_type)

  return (
    <div className="mt-2 rounded-lg border border-border p-3">
      <div className="flex items-center justify-between">
        <span className="text-[12.5px] font-medium text-foreground">
          Resize {inst.name}
        </span>
        <button onClick={onClose} className="text-muted-foreground"><X size={13} /></button>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select value={size} className={cn(inputCls, "sm:w-80")}
          onChange={(e) => { setSize(e.target.value); setPlan(null) }}>
          <option value="">Choose a new size…</option>
          {sizes.map((s) => (
            <option key={s.slug} value={s.slug}>
              {s.label}{s.price_monthly != null ? ` — ${money(s)}` : ""}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-[12.5px] text-foreground">
          <input type="checkbox" checked={growDisk}
            onChange={(e) => { setGrowDisk(e.target.checked); setPlan(null) }} />
          Include the bigger disk
        </label>
        <Button size="sm" variant="outline" disabled={!size || preview.isPending}
          onClick={() => preview.mutate()}>
          {preview.isPending && <Loader2 size={13} className="animate-spin" />}
          What will this do?
        </Button>
      </div>

      {(detail(preview.error) || detail(apply.error)) && (
        <p className="mt-2 text-[12.5px] text-red-600 dark:text-red-400">
          {detail(preview.error) || detail(apply.error)}
        </p>
      )}

      {plan && (
        <div className={cn("mt-2 rounded-lg px-3 py-2 text-[12.5px]",
          plan.reversible
            ? "bg-muted/50 text-foreground"
            : "border-l-2 border-red-500 bg-red-500/10 text-red-900 dark:text-red-200")}>
          {!plan.reversible && (
            <p className="mb-1 flex items-center gap-1.5 font-semibold">
              <TriangleAlert size={13} /> This cannot be undone
            </p>
          )}
          <p>{plan.warning}</p>
          {plan.price_change && <p className="mt-1">{plan.price_change}</p>}
          <div className="mt-2">
            <Button size="sm" disabled={apply.isPending}
              variant={plan.reversible ? "primary" : "danger"}
              onClick={() => apply.mutate()}>
              {apply.isPending && <Loader2 size={13} className="animate-spin" />}
              {plan.reversible ? "Resize" : "Resize permanently"}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

/** Delete. The name has to be typed, and the server checks it against what the provider
 *  reports at that moment — so a stale list cannot delete anything. */
function DestroyBox({ account, inst, onClose }: {
  account: CloudAccount; inst: CloudInstance; onClose: () => void
}) {
  const qc = useQueryClient()
  const [typed, setTyped] = useState("")
  const go = useMutation({
    mutationFn: () => destroyCloudInstance(account.id, inst.instance_id, typed),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cloud-instances", account.id] })
      qc.invalidateQueries({ queryKey: ["servers"] })
      onClose()
    },
  })
  return (
    <div className="mt-2 rounded-lg border-l-2 border-red-500 bg-red-500/5 p-3">
      <p className="text-[12.5px] font-semibold text-red-800 dark:text-red-300">
        Delete {inst.name} permanently
      </p>
      <p className="mt-1 text-[12.5px] text-muted-foreground">
        Its disk is erased. There is no backup of it anywhere unless you made one
        yourself. Type <strong className="text-foreground">{inst.name}</strong> to confirm.
      </p>
      <div className="mt-2 flex flex-wrap gap-2">
        <input value={typed} onChange={(e) => setTyped(e.target.value)}
          placeholder={inst.name} className={cn(inputCls, "sm:w-64")} />
        <Button size="sm" variant="danger"
          disabled={typed !== inst.name || go.isPending} onClick={() => go.mutate()}>
          {go.isPending && <Loader2 size={13} className="animate-spin" />}
          Delete for good
        </Button>
        <Button size="sm" variant="ghost" onClick={onClose}>Cancel</Button>
      </div>
      {detail(go.error) && (
        <p className="mt-2 text-[12.5px] text-red-600 dark:text-red-400">{detail(go.error)}</p>
      )}
    </div>
  )
}

export default function CloudLifecyclePanel({ account }: { account: CloudAccount }) {
  const qc = useQueryClient()
  const [creating, setCreating] = useState(false)
  const [open, setOpen] = useState<{ id: string; what: "resize" | "destroy" } | null>(null)
  const [note, setNote] = useState("")

  const cat = useQuery({ queryKey: ["cloud-catalogue", account.id],
                         queryFn: () => getCloudCatalogue(account.id) })
  const instances = useQuery({ queryKey: ["cloud-instances", account.id],
                               queryFn: () => listCloudInstances(account.id) })

  const power = useMutation({
    mutationFn: (v: { id: string; action: "reboot" | "power-on" | "power-off" }) =>
      cloudPower(account.id, v.id, v.action),
    onSuccess: (r) => {
      setNote(r.message)
      qc.invalidateQueries({ queryKey: ["cloud-instances", account.id] })
    },
    onError: (e) => setNote(detail(e) || "That did not work."),
  })

  if (cat.data && !cat.data.supported) {
    return (
      <p className="rounded-lg bg-muted/50 px-3 py-2 text-[12.5px] text-muted-foreground">
        {cat.data.message}
      </p>
    )
  }

  const list = instances.data ?? []

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-[12.5px] text-muted-foreground">
          Start, stop, resize or delete servers in this account.
        </p>
        {!creating && <Button size="sm" onClick={() => setCreating(true)}>
          <Plus size={13} />New server</Button>}
      </div>

      {creating && (
        <div className="rounded-lg border border-border p-3">
          <CreateForm account={account} onDone={() => setCreating(false)} />
        </div>
      )}

      {note && (
        <p className="rounded-lg bg-muted/50 px-3 py-2 text-[12.5px] text-foreground">{note}</p>
      )}

      {instances.isLoading && (
        <div className="flex justify-center py-6">
          <Loader2 className="animate-spin text-muted-foreground" /></div>
      )}

      <ul className="divide-y divide-border">
        {list.map((i) => {
          const off = ["off", "stopped"].includes(i.state)
          return (
            <li key={i.instance_id} className="py-2">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className={cn("h-2 w-2 shrink-0 rounded-full",
                  off ? "bg-slate-400" : "bg-emerald-500")} />
                <span className="text-[13px] font-medium text-foreground">{i.name}</span>
                <span className="font-mono text-[11.5px] text-muted-foreground">
                  {i.public_ip || "no address yet"}
                </span>
                <span className="text-[11.5px] text-muted-foreground">
                  {i.instance_type} · {i.region} · {i.state}
                </span>
                <div className="ml-auto flex gap-1">
                  {off
                    ? <Button size="sm" variant="ghost" disabled={power.isPending}
                        onClick={() => power.mutate({ id: i.instance_id, action: "power-on" })}>
                        <Power size={13} />Start
                      </Button>
                    : <>
                        <Button size="sm" variant="ghost" disabled={power.isPending}
                          onClick={() => power.mutate({ id: i.instance_id, action: "reboot" })}>
                          <RotateCw size={13} />Restart
                        </Button>
                        <Button size="sm" variant="ghost" disabled={power.isPending}
                          onClick={() => power.mutate({ id: i.instance_id, action: "power-off" })}>
                          <Power size={13} />Shut down
                        </Button>
                      </>}
                  <Button size="sm" variant="ghost"
                    onClick={() => setOpen(open?.id === i.instance_id && open.what === "resize"
                      ? null : { id: i.instance_id, what: "resize" })}>
                    <Gauge size={13} />Resize
                  </Button>
                  <Button size="sm" variant="ghost"
                    onClick={() => setOpen(open?.id === i.instance_id && open.what === "destroy"
                      ? null : { id: i.instance_id, what: "destroy" })}>
                    <Trash2 size={13} className="text-red-500" />
                  </Button>
                </div>
              </div>
              {open?.id === i.instance_id && open.what === "resize" && (
                <ResizeBox account={account} inst={i} onClose={() => setOpen(null)} />
              )}
              {open?.id === i.instance_id && open.what === "destroy" && (
                <DestroyBox account={account} inst={i} onClose={() => setOpen(null)} />
              )}
            </li>
          )
        })}
      </ul>
      {!instances.isLoading && !list.length && (
        <p className="py-4 text-center text-[12.5px] text-muted-foreground">
          No servers in this account yet.
        </p>
      )}
    </div>
  )
}

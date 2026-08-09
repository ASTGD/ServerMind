import { useEffect, useState } from "react"
import { Link, useNavigate, useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import Editor from "@monaco-editor/react"
import {
  AlertTriangle, Archive, Copy, FileCode2, Globe, Loader2, Lock, PauseCircle,
  RotateCcw, ShieldCheck, X, Zap,
} from "lucide-react"
import {
  addSiteAlias, cloneSite, getSiteAliases, getSiteAuth, getSiteCloneOptions,
  getSiteVhost, removeSiteAlias,
  getSiteSuspend, removeSiteAuth, saveSiteVhost, setSiteAuth, setSiteSuspend,
  getSiteCache, purgeSiteCache, resetSitePermissions, setSiteCache,
  type CloneStarted, type SiteDetail,
} from "@/api/sites"
import BlockRobots from "@/components/sites/BlockRobots"
import StagingCopy from "@/components/sites/StagingCopy"
import { Button, EmptyState } from "@/components/ui"
import { useThemeStore } from "@/store/themeStore"
import { cn } from "@/lib/utils"

/**
 * The tasks that do not belong to any one part of a site — Ploi's "Manage" screen.
 *
 * Built one item at a time, and an item that is not built is ABSENT rather than shown
 * greyed out: a permanently dead button is noise on every visit and implies the feature
 * exists and is merely switched off.
 *
 * Two of Ploi's ten are deliberately not coming. **System user** and **Tenants** are theirs
 * because they give every site its own Linux user; ours all run as the web server's user,
 * so those rows would describe a thing this product does not have. If per-site users are
 * ever added, they arrive together.
 */
export default function SiteManage() {
  const { site } = useOutletContext<{ site: SiteDetail }>()

  return (
    <div className="space-y-4">
      <Authentication site={site} />
      <BlockRobots siteId={site.id} />
      <SuspendSite site={site} />
      <PageCache site={site} />
      <FileBackups site={site} />
      <ResetPermissions site={site} />
      <DomainAliases site={site} />
      {/* Staging leads the pair: it is the safe one. A clone copies the files and leaves
          the copy's configuration naming the ORIGINAL database, so on the same server those
          credentials still work — what looks like a staging copy writes to the live site.
          Staging exists precisely to close that, so it is offered first. */}
      <StagingCopy site={site} />
      <CloneSite site={site} />
      <VhostEditor site={site} />
    </div>
  )
}

/**
 * Copy this site to a new domain — Ploi's "Clone site".
 *
 * The list of what is and is not copied is shown BEFORE the button, not after, because the
 * omissions are the whole story: the database is not copied, and the copied files still
 * name the original one. On a same-server clone those credentials still work, so what looks
 * like a staging copy writes to the live site. That sentence changes colour and wording the
 * moment the destination is picked, since it is only a warning when it is true.
 */
function CloneSite({ site }: { site: SiteDetail }) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [domain, setDomain] = useState("")
  const [serverId, setServerId] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [started, setStarted] = useState<CloneStarted | null>(null)

  const options = useQuery({
    queryKey: ["site-clone", site.id],
    queryFn: () => getSiteCloneOptions(site.id),
    enabled: open,
  })

  // Prefilled with this site's own domain, as Ploi does — the common case is moving a site
  // to another server, where the domain stays the same.
  useEffect(() => {
    if (!options.data) return
    setDomain((d) => d || options.data.domain)
    setServerId((s) => s || options.data.server_id)
  }, [options.data])

  const sameServer = serverId === options.data?.server_id
  const warning = sameServer
    ? options.data?.database_note.same
    : options.data?.database_note.other

  const run = useMutation({
    mutationFn: () => cloneSite(site.id, domain.trim(), serverId),
    onSuccess: (r) => { setStarted(r); setError(null) },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "The copy could not be started."),
  })

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <Copy size={15} className="text-muted-foreground" />
        <h3 className="text-h3 text-foreground">Clone site</h3>
      </div>
      <p className="mt-1 text-small text-muted-foreground">
        Copy this site's files to a new address — on this server or another one. Useful for
        a staging copy, or for moving a site to a bigger machine.
      </p>

      {started ? (
        <div className="mt-3 rounded-lg border-l-2 border-emerald-500 bg-emerald-500/5 px-3 py-2.5">
          <p className="text-small text-foreground">
            Copying <span className="font-medium">{started.size}</span>
            {started.files > 0 && <> across {started.files.toLocaleString()} files</> } to{" "}
            <span className="font-mono">{started.domain}</span>. It carries on in the
            background — the new site shows as <em>Setting up</em> until it is done.
          </p>
          {started.database_note && (
            <p className="mt-2 text-caption text-amber-700 dark:text-amber-400">
              {started.database_note}
            </p>
          )}
          <div className="mt-3 flex gap-2">
            <Button size="sm" variant="outline"
                    onClick={() => navigate(`/sites/${started.id}`)}>
              Open the copy
            </Button>
            <Button size="sm" variant="ghost"
                    onClick={() => { setStarted(null); setOpen(false) }}>Done</Button>
          </div>
        </div>
      ) : !open ? (
        <div className="mt-3">
          <Button variant="outline" size="sm" onClick={() => setOpen(true)}>Clone site</Button>
        </div>
      ) : (
        <div className="mt-3 space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block">
              <span className="text-caption text-muted-foreground">Domain for the copy</span>
              <input
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="staging.example.com"
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2
                           text-small text-foreground"
              />
            </label>
            <label className="block">
              <span className="text-caption text-muted-foreground">Copy it to</span>
              <select
                value={serverId}
                onChange={(e) => setServerId(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-2
                           text-small text-foreground"
              >
                {(options.data?.servers ?? []).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}{s.same ? " (this server)" : ""}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="rounded-lg border border-border bg-muted/30 px-3 py-2.5">
            <p className="text-caption font-medium text-foreground">What comes across</p>
            <p className="mt-0.5 text-caption text-muted-foreground">
              Every file in this site, and the repository it deploys from if it has one —
              with push-to-deploy left off, so the copy does not start deploying on its own.
            </p>
            <p className="mt-2 text-caption font-medium text-foreground">What does not</p>
            <p className="mt-0.5 text-caption text-muted-foreground">
              Hand-edited web-server settings, the HTTPS certificate, and the database.
            </p>
          </div>

          {warning && (
            <p className="rounded-lg border-l-2 border-amber-500 bg-amber-500/5 px-3 py-2
                          text-small text-foreground">{warning}</p>
          )}

          <div className="flex gap-2">
            <Button size="sm" onClick={() => run.mutate()}
                    disabled={run.isPending || !domain.trim() || !serverId}>
              {run.isPending && <Loader2 size={14} className="animate-spin" />}
              Start copying
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
          </div>
        </div>
      )}

      {error && (
        <p className="mt-2 rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                      text-small text-destructive">{error}</p>
      )}
    </div>
  )
}

/**
 * The web-server configuration, edited by hand — the escape hatch when nothing else on the
 * site fits.
 *
 * It is also the most dangerous edit in the product, so the page says what protects them
 * BEFORE they type: the old file is kept, the web server has to accept the new one, the
 * site has to still answer, and any failure puts the old file back. That is not reassurance
 * for its own sake — someone who knows the change is reversible will make it carefully once
 * instead of not at all.
 */
function VhostEditor({ site }: { site: SiteDetail }) {
  const qc = useQueryClient()
  // "system" is a real setting, so asking the store for the preference is not enough —
  // the editor would render light inside a dark app. Resolved the same way the app resolves
  // it, and re-read on every render so a toggle carries.
  const preference = useThemeStore((s) => s.theme)
  const dark = preference === "dark"
    || (preference === "system"
      && typeof window !== "undefined"
      && window.matchMedia("(prefers-color-scheme: dark)").matches)
  const [draft, setDraft] = useState<string | null>(null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["site-vhost", site.id],
    queryFn: () => getSiteVhost(site.id),
  })

  const save = useMutation({
    mutationFn: () => saveSiteVhost(site.id, draft ?? ""),
    onSuccess: (r) => {
      setNote({ ok: true, text: r.message })
      setDraft(null)   // reload from the server, so what is shown is what is really there
      qc.invalidateQueries({ queryKey: ["site-vhost", site.id] })
    },
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setNote({ ok: false, text: e.response?.data?.detail ?? "It could not be saved." }),
  })

  if (isLoading) {
    return <div className="h-64 animate-pulse rounded-xl border border-border bg-card" />
  }
  if (!data?.ok) {
    return (
      <EmptyState
        icon={AlertTriangle}
        title="The configuration cannot be edited here"
        description={data?.reason ?? "This site is not managed over SSH."}
      />
    )
  }

  const original = data.content ?? ""
  const value = draft ?? original
  const changed = value !== original

  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card">
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-sm font-medium text-foreground">
            <FileCode2 size={15} className="text-primary" /> Web server configuration
          </h3>
          <p className="mt-0.5 truncate font-mono text-caption text-muted-foreground"
             title={data.path}>
            {data.path}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {changed && (
            <Button variant="ghost" size="sm" onClick={() => { setDraft(null); setNote(null) }}>
              <RotateCcw size={13} /> Discard
            </Button>
          )}
          <Button size="sm" disabled={!changed || save.isPending}
                  onClick={() => { setNote(null); save.mutate() }}>
            {save.isPending
              ? <><Loader2 size={13} className="animate-spin" /> Saving…</>
              : "Save"}
          </Button>
        </div>
      </header>

      {/* Said before they type, not after it goes wrong. */}
      <p className="border-b border-border bg-muted/30 px-5 py-2.5 text-caption text-muted-foreground">
        Your current file is kept. The web server has to accept the new one and the site has
        to still answer — if either fails, the old file goes straight back and nothing on
        this server changes.
      </p>

      {note && (
        <p className={`border-b border-border px-5 py-2.5 text-small ${note.ok
          ? "bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
          : "bg-destructive/5 text-destructive"}`}>
          {note.text}
        </p>
      )}

      <Editor
        height="480px"
        defaultLanguage="ini"
        value={value}
        onChange={(v) => setDraft(v ?? "")}
        theme={dark ? "vs-dark" : "light"}
        options={{
          minimap: { enabled: false },
          fontSize: 13,
          scrollBeyondLastLine: false,
          tabSize: 4,
        }}
      />
    </section>
  )
}


/**
 * Extra domains that answer for the same site.
 *
 * Two things are said plainly on this card because a customer who is not told will report
 * both as bugs: adding the domain here makes the SERVER answer for it, but it does not
 * point that domain here, and it does not put it on the certificate.
 */
function DomainAliases({ site }: { site: SiteDetail }) {
  const qc = useQueryClient()
  const [value, setValue] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const q = useQuery({
    queryKey: ["site-aliases", site.id],
    queryFn: () => getSiteAliases(site.id),
  })

  const done = (message: string) => {
    setNote(message)
    setError(null)
    setValue("")
    qc.invalidateQueries({ queryKey: ["site-aliases", site.id] })
    // The editor below is showing the file we just changed. Left stale, it would display a
    // configuration the server no longer has — and pressing Save on it would quietly undo
    // the alias, with the screen having told the customer it was added.
    qc.invalidateQueries({ queryKey: ["site-vhost", site.id] })
  }
  const failed = (e: unknown) => {
    setNote(null)
    setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? "That domain could not be changed.")
  }

  const add = useMutation({
    mutationFn: () => addSiteAlias(site.id, value),
    onSuccess: (r) => done(r.message),
    onError: failed,
  })
  const drop = useMutation({
    mutationFn: (alias: string) => removeSiteAlias(site.id, alias),
    onSuccess: () => done("Removed. The site no longer answers for that domain."),
    onError: failed,
  })

  const aliases = q.data?.aliases ?? []
  const busy = add.isPending || drop.isPending

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <Globe size={15} className="text-muted-foreground" />
        <h3 className="text-h3 text-foreground">Domain aliases</h3>
      </div>
      <p className="mt-1 text-small text-muted-foreground">
        Extra domains that show this same site. Useful for <code>www.</code> and for a
        second domain a client owns.
      </p>

      <form
        className="mt-3 flex flex-wrap gap-2"
        onSubmit={(e) => { e.preventDefault(); if (value.trim()) add.mutate() }}
      >
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={`www.${site.domain}`}
          disabled={busy}
          className="min-w-0 flex-1 rounded-lg border border-border bg-background px-3 py-1.5
                     font-mono text-sm text-foreground"
        />
        <Button type="submit" disabled={busy || !value.trim()}>
          {add.isPending && <Loader2 size={14} className="animate-spin" />}
          Add
        </Button>
      </form>

      {error && (
        <p className="mt-2 rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                      text-small text-destructive">
          {error}
        </p>
      )}
      {note && !error && (
        <p className="mt-2 rounded-lg border-l-2 border-emerald-500 bg-emerald-500/5 px-3 py-2
                      text-small text-foreground">
          {note}
        </p>
      )}

      {q.isLoading ? (
        <div className="mt-3 h-8 animate-pulse rounded-lg bg-muted" />
      ) : aliases.length === 0 ? (
        <p className="mt-3 text-caption text-muted-foreground">
          Only <span className="font-mono">{site.domain}</span> reaches this site.
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-border rounded-lg border border-border">
          {aliases.map((alias) => (
            <li key={alias} className="flex items-center justify-between gap-3 px-3 py-2">
              <span className="truncate font-mono text-[13px] text-foreground">{alias}</span>
              <button
                type="button"
                onClick={() => drop.mutate(alias)}
                disabled={busy}
                title={`Stop answering for ${alias}`}
                className="shrink-0 rounded-md p-1 text-muted-foreground
                           hover:bg-destructive/10 hover:text-destructive"
              >
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}


/** A password that is only as good as its own strength — generated, not invented. */
function strongSecret(): string {
  const abc = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
  return Array.from(crypto.getRandomValues(new Uint32Array(16)))
    .map((n) => abc[n % abc.length]).join("")
}

/**
 * A username and password in front of the site — Ploi's "Authentication".
 *
 * The password is shown once because it has to be given to somebody, and it is never
 * stored: it is hashed on our side and only the hash reaches the server.
 */
function Authentication({ site }: { site: SiteDetail }) {
  const qc = useQueryClient()
  const [name, setName] = useState("")
  const [password, setPassword] = useState(strongSecret)
  const [path, setPath] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const q = useQuery({ queryKey: ["site-auth", site.id], queryFn: () => getSiteAuth(site.id) })

  const after = (message: string) => {
    setNote(message); setError(null); setName(""); setPassword(strongSecret())
    qc.invalidateQueries({ queryKey: ["site-auth", site.id] })
    // The editor below shows the file this just changed.
    qc.invalidateQueries({ queryKey: ["site-vhost", site.id] })
  }
  const failed = (e: unknown) => {
    setNote(null)
    setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? "That could not be saved.")
  }

  const save = useMutation({
    mutationFn: () => setSiteAuth(site.id, { name, password, path }),
    onSuccess: (r) => after(r.message), onError: failed,
  })
  const drop = useMutation({
    mutationFn: (who: string) => removeSiteAuth(site.id, who),
    onSuccess: (r) => after(r.message), onError: failed,
  })

  const users = q.data?.users ?? []
  const busy = save.isPending || drop.isPending
  const livePath = q.data?.path ?? ""

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <Lock size={15} className="text-muted-foreground" />
        <h3 className="text-h3 text-foreground">Authentication</h3>
      </div>
      <p className="mt-1 text-small text-muted-foreground">
        Ask for a username and password before the site is shown. Useful while a site is
        being built, or to keep an admin page to yourself.
      </p>

      {users.length > 0 && (
        <p className="mt-2 rounded-lg border-l-2 border-amber-500 bg-amber-500/5 px-3 py-2
                      text-small text-foreground">
          {livePath
            ? <>A password is required for <span className="font-mono">{livePath}/</span> and
              everything under it.</>
            : <>A password is required for the whole site — including anyone you send it to.</>}
        </p>
      )}

      <form
        className="mt-3 grid gap-2 sm:grid-cols-2"
        onSubmit={(e) => { e.preventDefault(); if (name.trim()) save.mutate() }}
      >
        <div>
          <label className="text-caption text-muted-foreground">Username</label>
          <input value={name} onChange={(e) => setName(e.target.value)} disabled={busy}
            placeholder="client" className="mt-1 w-full rounded-lg border border-border
            bg-background px-3 py-1.5 font-mono text-sm text-foreground" />
        </div>
        <div>
          <label className="text-caption text-muted-foreground">Password</label>
          <div className="mt-1 flex gap-2">
            <input value={password} onChange={(e) => setPassword(e.target.value)} disabled={busy}
              className="w-full rounded-lg border border-border bg-background px-3 py-1.5
              font-mono text-sm text-foreground" />
            <Button type="button" variant="outline" size="sm"
              onClick={() => setPassword(strongSecret())}>New</Button>
          </div>
        </div>
        <div className="sm:col-span-2">
          <label className="text-caption text-muted-foreground">
            Only this path (optional)
          </label>
          <input value={path} onChange={(e) => setPath(e.target.value)} disabled={busy}
            placeholder="/wp-admin — leave empty for the whole site"
            className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5
            font-mono text-sm text-foreground" />
        </div>
        <div className="sm:col-span-2 flex items-center gap-3">
          <Button type="submit" disabled={busy || !name.trim()}>
            {save.isPending && <Loader2 size={14} className="animate-spin" />}
            Save
          </Button>
          <span className="text-caption text-amber-600 dark:text-amber-400">
            Copy the password now — it is hashed on the server and cannot be shown again.
          </span>
        </div>
      </form>

      {error && (
        <p className="mt-2 rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                      text-small text-destructive">{error}</p>
      )}
      {note && !error && (
        <p className="mt-2 rounded-lg border-l-2 border-emerald-500 bg-emerald-500/5 px-3 py-2
                      text-small text-foreground">{note}</p>
      )}

      {q.isLoading ? (
        <div className="mt-3 h-8 animate-pulse rounded-lg bg-muted" />
      ) : users.length === 0 ? (
        <p className="mt-3 text-caption text-muted-foreground">
          Anyone can reach this site.
        </p>
      ) : (
        <ul className="mt-3 divide-y divide-border rounded-lg border border-border">
          {users.map((who) => (
            <li key={who} className="flex items-center justify-between gap-3 px-3 py-2">
              <span className="truncate font-mono text-[13px] text-foreground">{who}</span>
              <button type="button" onClick={() => drop.mutate(who)} disabled={busy}
                title={`Remove ${who}`}
                className="shrink-0 rounded-md p-1 text-muted-foreground
                           hover:bg-destructive/10 hover:text-destructive">
                <X size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}


/**
 * Take the site offline on purpose, behind a notice — Ploi's "Suspend site".
 *
 * The response code is not a detail. It is what search engines are told, and 200 means
 * "this IS the page now" — a client's real pages get replaced in the index by a suspension
 * notice, and that outlives the billing dispute by months. So 503 is the default and every
 * option says what it costs.
 */
function SuspendSite({ site }: { site: SiteDetail }) {
  const qc = useQueryClient()
  const [message, setMessage] = useState("")
  const [reason, setReason] = useState("")
  const [code, setCode] = useState(503)
  const [touched, setTouched] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const q = useQuery({
    queryKey: ["site-suspend", site.id],
    queryFn: () => getSiteSuspend(site.id),
  })

  // Fill the form from what the site is actually suspended WITH, so it is edited rather
  // than retyped — but never overwrite something the customer is in the middle of typing.
  if (q.data && !touched && (q.data.message !== message || q.data.reason !== reason)) {
    if (q.data.suspended) { setMessage(q.data.message); setReason(q.data.reason); setCode(q.data.code) }
    setTouched(true)
  }

  const after = (m: string) => {
    setNote(m); setError(null)
    qc.invalidateQueries({ queryKey: ["site-suspend", site.id] })
    qc.invalidateQueries({ queryKey: ["site-vhost", site.id] })
  }
  const failed = (e: unknown) => {
    setNote(null)
    setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? "That could not be changed.")
  }

  const go = useMutation({
    mutationFn: (on: boolean) => setSiteSuspend(site.id, {
      suspended: on, message, reason, code,
    }),
    onSuccess: (r) => after(r.message), onError: failed,
  })

  const on = q.data?.suspended ?? false
  const codes = q.data?.codes ?? []
  const chosen = codes.find((c) => c.value === code)

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <PauseCircle size={15} className="text-muted-foreground" />
        <h3 className="text-h3 text-foreground">Suspend site</h3>
      </div>
      <p className="mt-1 text-small text-muted-foreground">
        Show a notice instead of the site — useful when a client has not paid. Nothing is
        deleted, and putting it back is one click.
      </p>

      {on && (
        <p className="mt-2 rounded-lg border-l-2 border-amber-500 bg-amber-500/5 px-3 py-2
                      text-small text-foreground">
          <span className="font-medium">This site is suspended.</span> Visitors see your
          notice and the site answers with {q.data?.code}.
        </p>
      )}

      <div className="mt-3 space-y-2">
        <div>
          <label className="text-caption text-muted-foreground">Headline</label>
          <input value={message} onChange={(e) => { setMessage(e.target.value); setTouched(true) }}
            placeholder="Website is suspended" disabled={go.isPending}
            className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5
            text-sm text-foreground" />
        </div>
        <div>
          <label className="text-caption text-muted-foreground">
            Message to visitors (optional)
          </label>
          <textarea value={reason} onChange={(e) => { setReason(e.target.value); setTouched(true) }}
            rows={3} disabled={go.isPending}
            placeholder="Please contact us to restore this website."
            className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5
            text-sm text-foreground" />
          <p className="mt-1 text-caption text-muted-foreground">
            **bold**, *italic*, - lists and links are understood. Anything else is shown as
            written.
          </p>
        </div>
        <div>
          <label className="text-caption text-muted-foreground">What to answer with</label>
          <select value={code} onChange={(e) => { setCode(Number(e.target.value)); setTouched(true) }}
            disabled={go.isPending}
            className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5
            text-sm text-foreground">
            {codes.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
          </select>
          {chosen && (
            <p className={cn("mt-1 text-caption",
              chosen.value === 503 ? "text-muted-foreground"
                : "text-amber-600 dark:text-amber-400")}>
              {chosen.note}
            </p>
          )}
        </div>
      </div>

      {error && (
        <p className="mt-2 rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                      text-small text-destructive">{error}</p>
      )}
      {note && !error && (
        <p className="mt-2 rounded-lg border-l-2 border-emerald-500 bg-emerald-500/5 px-3 py-2
                      text-small text-foreground">{note}</p>
      )}

      <div className="mt-3 flex gap-2">
        {on ? (
          <Button onClick={() => go.mutate(false)} disabled={go.isPending}>
            {go.isPending && <Loader2 size={14} className="animate-spin" />}
            Put the site back
          </Button>
        ) : (
          <Button variant="outline" onClick={() => go.mutate(true)} disabled={go.isPending}>
            {go.isPending && <Loader2 size={14} className="animate-spin" />}
            Suspend this site
          </Button>
        )}
        {on && (
          <Button variant="ghost" onClick={() => go.mutate(true)} disabled={go.isPending}>
            Update the notice
          </Button>
        )}
      </div>
    </div>
  )
}


/**
 * Where a site's file backups actually live — Ploi's "File Backups".
 *
 * Theirs is not a form: it jumps to their central backup area filtered to the site. Ours
 * does the same, because backups genuinely belong to the server — one schedule, one
 * destination, one retention rule — and a second per-site copy of that would be a second
 * place for it to be wrong.
 */
function FileBackups({ site }: { site: SiteDetail }) {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <Archive size={15} className="text-muted-foreground" />
        <h3 className="text-h3 text-foreground">File backups</h3>
      </div>
      <p className="mt-1 text-small text-muted-foreground">
        Backups are set up per server, so one schedule and one destination cover every site
        on it. This site's files live in{" "}
        <span className="font-mono text-[12px] text-foreground">
          {site.doc_root || "an unknown folder"}
        </span>.
      </p>
      <div className="mt-3">
        <Link to={`/servers/${site.server_id}/backups`}>
          <Button variant="outline" size="sm">Open backups for this server</Button>
        </Link>
      </div>
    </div>
  )
}

/**
 * Put file ownership back — Ploi's "Reset permissions".
 *
 * It says the same three things Ploi's dialog says, because they are all true: it
 * overwrites anything customised, it takes effect at once, and there is no undo. The
 * confirmation is a second click rather than a typed name — this repairs a site, it does
 * not delete one.
 */
function ResetPermissions({ site }: { site: SiteDetail }) {
  const [asking, setAsking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const run = useMutation({
    mutationFn: () => resetSitePermissions(site.id),
    onSuccess: (r) => { setNote(r.message); setError(null); setAsking(false) },
    onError: (e: { response?: { data?: { detail?: string } } }) => {
      setNote(null); setAsking(false)
      setError(e.response?.data?.detail ?? "The permissions could not be reset.")
    },
  })

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <ShieldCheck size={15} className="text-muted-foreground" />
        <h3 className="text-h3 text-foreground">Reset permissions</h3>
      </div>
      <p className="mt-1 text-small text-muted-foreground">
        Give every file in this site back to the web server, and put folders and files back
        to their normal permissions. Fixes a site that has stopped being able to write —
        uploads failing, a cache it cannot clear, an update that will not apply.
      </p>

      {asking ? (
        <div className="mt-3 rounded-lg border-l-2 border-amber-500 bg-amber-500/5 px-3 py-2.5">
          <p className="text-small font-medium text-foreground">Before you do this</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-caption text-muted-foreground">
            <li>Any permissions you set on purpose will be overwritten.</li>
            <li>It takes effect immediately, on the live site.</li>
            <li>There is no undo — nothing records what the permissions were before.</li>
          </ul>
          <p className="mt-2 text-caption text-muted-foreground">
            Only <span className="font-mono">{site.doc_root}</span> is touched. Nothing
            above it, and no other site.
          </p>
          <div className="mt-3 flex gap-2">
            <Button size="sm" onClick={() => run.mutate()} disabled={run.isPending}>
              {run.isPending && <Loader2 size={14} className="animate-spin" />}
              Yes, reset them
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setAsking(false)}>Cancel</Button>
          </div>
        </div>
      ) : (
        <div className="mt-3">
          <Button variant="outline" size="sm" onClick={() => { setAsking(true); setNote(null) }}>
            Reset permissions
          </Button>
        </div>
      )}

      {error && (
        <p className="mt-2 rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                      text-small text-destructive">{error}</p>
      )}
      {note && !error && (
        <p className="mt-2 rounded-lg border-l-2 border-emerald-500 bg-emerald-500/5 px-3 py-2
                      text-small text-foreground">{note}</p>
      )}
    </div>
  )
}


/**
 * Cache PHP pages in nginx — Ploi's "FastCGI Cache".
 *
 * Ploi's own warning is the honest one and it is repeated here: the failure mode is "my
 * edit is not showing". So the off switch and the clear button are both one click and both
 * always visible — a cache you cannot clear is a site you cannot edit.
 */
function PageCache({ site }: { site: SiteDetail }) {
  const qc = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)

  const q = useQuery({ queryKey: ["site-cache", site.id], queryFn: () => getSiteCache(site.id) })

  const after = (m: string) => {
    setNote(m); setError(null)
    qc.invalidateQueries({ queryKey: ["site-cache", site.id] })
    qc.invalidateQueries({ queryKey: ["site-vhost", site.id] })
  }
  const failed = (e: unknown) => {
    setNote(null)
    setError((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      ?? "That could not be changed.")
  }

  const toggle = useMutation({
    mutationFn: (on: boolean) => setSiteCache(site.id, on),
    onSuccess: (r) => after(r.message), onError: failed,
  })
  const purge = useMutation({
    mutationFn: () => purgeSiteCache(site.id),
    onSuccess: (r) => after(r.message), onError: failed,
  })

  const on = q.data?.enabled ?? false
  const supported = q.data?.supported ?? false
  const busy = toggle.isPending || purge.isPending

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <div className="flex items-center gap-2">
        <Zap size={15} className="text-muted-foreground" />
        <h3 className="text-h3 text-foreground">Page cache</h3>
      </div>
      <p className="mt-1 text-small text-muted-foreground">
        Store finished pages so repeat visitors skip PHP entirely. Logged-in visitors, form
        posts, admin pages and shopping baskets are never cached — only pages that look the
        same to everyone.
      </p>

      {!supported ? (
        <p className="mt-3 text-caption text-muted-foreground">
          {q.data?.reason || "Not available for this site."}
        </p>
      ) : (
        <>
          {on && (
            <p className="mt-2 rounded-lg border-l-2 border-amber-500 bg-amber-500/5 px-3 py-2
                          text-small text-foreground">
              <span className="font-medium">Caching is on.</span> If you change the site and
              the change does not appear, clear the cache — that is almost always why.
            </p>
          )}
          <div className="mt-3 flex flex-wrap gap-2">
            {on ? (
              <Button variant="outline" size="sm" onClick={() => toggle.mutate(false)}
                disabled={busy}>
                {toggle.isPending && <Loader2 size={14} className="animate-spin" />}
                Turn caching off
              </Button>
            ) : (
              <Button size="sm" onClick={() => toggle.mutate(true)} disabled={busy}>
                {toggle.isPending && <Loader2 size={14} className="animate-spin" />}
                Turn caching on
              </Button>
            )}
            {on && (
              <Button variant="ghost" size="sm" onClick={() => purge.mutate()} disabled={busy}>
                {purge.isPending && <Loader2 size={14} className="animate-spin" />}
                Clear the cache
              </Button>
            )}
          </div>
        </>
      )}

      {error && (
        <p className="mt-2 rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2
                      text-small text-destructive">{error}</p>
      )}
      {note && !error && (
        <p className="mt-2 rounded-lg border-l-2 border-emerald-500 bg-emerald-500/5 px-3 py-2
                      text-small text-foreground">{note}</p>
      )}
    </div>
  )
}

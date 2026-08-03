import { useState } from "react"
import { useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import Editor from "@monaco-editor/react"
import {
  AlertTriangle, FileCode2, Globe, Loader2, Lock, RotateCcw, X,
} from "lucide-react"
import {
  addSiteAlias, getSiteAliases, getSiteAuth, getSiteVhost, removeSiteAlias,
  removeSiteAuth, saveSiteVhost, setSiteAuth, type SiteDetail,
} from "@/api/sites"
import { Button, EmptyState } from "@/components/ui"
import { useThemeStore } from "@/store/themeStore"

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
      <DomainAliases site={site} />
      <VhostEditor site={site} />
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

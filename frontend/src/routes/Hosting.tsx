import { useState, useEffect } from "react"
import { useParams } from "react-router-dom"
import { Button } from "@/components/ui"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Globe,
  Database as DatabaseIcon,
  Mail,
  Plus,
  ShieldCheck,
  Trash2,
  Loader2,
  AlertTriangle,
  X,
  Server as ServerIcon,
} from "lucide-react"
import {
  listWebsites,
  createWebsite,
  deleteWebsite,
  issueSsl,
  listDatabases,
  createDatabase,
  listEmail,
  createEmail,
  type Website,
  type HostingDatabase,
  type EmailAccount,
} from "@/api/hosting"

type Tab = "websites" | "databases" | "email"

const TABS: { key: Tab; label: string; Icon: typeof Globe }[] = [
  { key: "websites", label: "Websites", Icon: Globe },
  { key: "databases", label: "Databases", Icon: DatabaseIcon },
  { key: "email", label: "Email", Icon: Mail },
]

function errMsg(e: unknown): string {
  const err = e as { response?: { data?: { detail?: string } }; message?: string }
  return err.response?.data?.detail ?? err.message ?? "Request failed"
}

// ── Simple field modal ─────────────────────────────────────────────────────

function FieldModal({
  title,
  fields,
  onClose,
  onSubmit,
  isPending,
  error,
  initialValues,
}: {
  title: string
  fields: { key: string; label: string; placeholder?: string; type?: string; required?: boolean }[]
  onClose: () => void
  onSubmit: (values: Record<string, string>) => void
  isPending: boolean
  error?: string
  initialValues?: Record<string, string>
}) {
  const [values, setValues] = useState<Record<string, string>>(initialValues ?? {})
  const valid = fields.every((f) => !f.required || (values[f.key] ?? "").trim())
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-xl shadow-2xl w-full max-w-md p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-foreground">{title}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
        </div>
        {fields.map((f) => (
          <div key={f.key}>
            <label className="text-xs font-medium text-muted-foreground mb-1 block">{f.label}</label>
            <input
              type={f.type ?? "text"}
              value={values[f.key] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
              placeholder={f.placeholder}
              className="w-full rounded-lg border border-border bg-background text-sm text-foreground px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>
        ))}
        {error && (
          <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</div>
        )}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground border border-border rounded-lg hover:bg-muted/50 transition-colors">Cancel</button>
          <button onClick={() => valid && onSubmit(values)} disabled={!valid || isPending}
            className="flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors">
            {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Create
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function Hosting() {
  const { id: serverId } = useParams<{ id: string }>()
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>("websites")
  const [modal, setModal] = useState<"website" | "database" | "email" | null>(null)
  // Some panels (CyberPanel) scope databases per-website — a domain must be picked
  // or the list always reads empty even when databases exist.
  const [dbDomain, setDbDomain] = useState<string | null>(null)

  const websitesQ = useQuery({
    queryKey: ["hosting-websites", serverId],
    queryFn: () => listWebsites(serverId!),
    enabled: !!serverId && (tab === "websites" || tab === "databases"),
    retry: false,
  })
  useEffect(() => {
    if (!dbDomain && websitesQ.data && websitesQ.data.length > 0) setDbDomain(websitesQ.data[0].domain)
  }, [websitesQ.data, dbDomain])
  const databasesQ = useQuery({
    queryKey: ["hosting-databases", serverId, dbDomain],
    queryFn: () => listDatabases(serverId!, dbDomain ?? undefined),
    enabled: !!serverId && tab === "databases",
    retry: false,
  })
  const emailQ = useQuery({
    queryKey: ["hosting-email", serverId],
    queryFn: () => listEmail(serverId!),
    enabled: !!serverId && tab === "email",
    retry: false,
  })

  const refetchKey = (k: string) => qc.invalidateQueries({ queryKey: [k, serverId] })

  const createSiteMut = useMutation({
    mutationFn: (v: Record<string, string>) => createWebsite(serverId!, { domain: v.domain, email: v.email || null }),
    onSuccess: () => { setModal(null); refetchKey("hosting-websites") },
  })
  const sslMut = useMutation({
    mutationFn: (domain: string) => issueSsl(serverId!, domain),
    onSuccess: () => refetchKey("hosting-websites"),
  })
  const deleteSiteMut = useMutation({
    mutationFn: (domain: string) => deleteWebsite(serverId!, domain),
    onSuccess: () => refetchKey("hosting-websites"),
  })
  const createDbMut = useMutation({
    mutationFn: (v: Record<string, string>) => createDatabase(serverId!, {
      domain: v.domain || null, db_name: v.db_name, db_user: v.db_user || null, db_password: v.db_password || null,
    }),
    onSuccess: (_result, variables) => {
      setModal(null)
      if (variables.domain) setDbDomain(variables.domain) // view the site the new DB belongs to
      refetchKey("hosting-databases")
    },
  })
  const createEmailMut = useMutation({
    mutationFn: (v: Record<string, string>) => createEmail(serverId!, { user: v.user, domain: v.domain, password: v.password }),
    onSuccess: () => { setModal(null); refetchKey("hosting-email") },
  })

  const activeQ = tab === "websites" ? websitesQ : tab === "databases" ? databasesQ : emailQ

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-h1 text-foreground flex items-center gap-2">
            <ServerIcon className="h-6 w-6 text-primary" />
            Hosting
          </h1>
          <p className="text-sm text-muted-foreground mt-1">Manage websites, databases, and email through your control panel.</p>
        </div>
        <Button
          onClick={() => setModal(tab === "websites" ? "website" : tab === "databases" ? "database" : "email")}
          className="shrink-0"
        >
          <Plus className="h-4 w-4" />
          New {tab === "websites" ? "website" : tab === "databases" ? "database" : "email"}
        </Button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        {TABS.map(({ key, label, Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`flex items-center gap-1.5 px-3 py-2 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === key ? "border-primary text-foreground" : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {/* Loading / error */}
      {activeQ.isLoading && (
        <div className="flex items-center gap-2 py-12 text-muted-foreground text-sm"><Loader2 className="h-4 w-4 animate-spin" />Loading…</div>
      )}
      {activeQ.isError && (
        <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {errMsg(activeQ.error)}
        </div>
      )}

      {/* Websites */}
      {tab === "websites" && websitesQ.data && (
        websitesQ.data.length === 0 ? (
          <EmptyState icon={Globe} text="No websites found" />
        ) : (
          <div className="space-y-2">
            {websitesQ.data.map((w: Website) => (
              <div key={w.domain} className="rounded-xl border border-border bg-card p-4 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5 min-w-0">
                  <Globe className="h-4 w-4 text-primary shrink-0" />
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-foreground truncate">{w.domain}</div>
                    <div className="text-xs text-muted-foreground">
                      {[w.state, w.php, w.type].filter(Boolean).join(" · ") || "—"}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <button onClick={() => sslMut.mutate(w.domain)} disabled={sslMut.isPending}
                    className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-muted/50 hover:text-foreground disabled:opacity-50 transition-colors">
                    {sslMut.isPending && sslMut.variables === w.domain ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
                    Issue SSL
                  </button>
                  <button onClick={() => { if (window.confirm(`Delete website ${w.domain}? This is destructive.`)) deleteSiteMut.mutate(w.domain) }}
                    className="p-1.5 rounded text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )
      )}

      {/* Databases */}
      {tab === "databases" && (
        <div className="space-y-3">
          {websitesQ.data && websitesQ.data.length > 0 && (
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              Website
              <select
                value={dbDomain ?? ""}
                onChange={(e) => setDbDomain(e.target.value)}
                className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
              >
                {websitesQ.data.map((w: Website) => (
                  <option key={w.domain} value={w.domain}>{w.domain}</option>
                ))}
              </select>
            </label>
          )}
          {databasesQ.data && (
            databasesQ.data.length === 0 ? (
              <EmptyState icon={DatabaseIcon} text="No databases found" />
            ) : (
              <div className="space-y-2">
                {databasesQ.data.map((d: HostingDatabase, i: number) => (
                  <div key={(d.db_name ?? "") + i} className="rounded-xl border border-border bg-card p-4 flex items-center gap-2.5">
                    <DatabaseIcon className="h-4 w-4 text-violet-400 shrink-0" />
                    <span className="text-sm text-foreground font-medium">{d.db_name}</span>
                    {d.size != null && <span className="text-xs text-muted-foreground ml-auto">{d.size}</span>}
                  </div>
                ))}
              </div>
            )
          )}
        </div>
      )}

      {/* Email */}
      {tab === "email" && emailQ.data && (
        emailQ.data.length === 0 ? (
          <EmptyState icon={Mail} text="No email accounts found" />
        ) : (
          <div className="space-y-2">
            {emailQ.data.map((e: EmailAccount, i: number) => (
              <div key={(e.email ?? "") + i} className="rounded-xl border border-border bg-card p-4 flex items-center gap-2.5">
                <Mail className="h-4 w-4 text-blue-400 shrink-0" />
                <span className="text-sm text-foreground font-medium">{e.email}</span>
              </div>
            ))}
          </div>
        )
      )}

      {/* Modals */}
      {modal === "website" && (
        <FieldModal
          title="New website"
          fields={[
            { key: "domain", label: "Domain", placeholder: "example.com", required: true },
            { key: "email", label: "Admin email (optional)", placeholder: "admin@example.com" },
          ]}
          isPending={createSiteMut.isPending}
          error={createSiteMut.isError ? errMsg(createSiteMut.error) : undefined}
          onClose={() => setModal(null)}
          onSubmit={(v) => createSiteMut.mutate(v)}
        />
      )}
      {modal === "database" && (
        <FieldModal
          title="New database"
          fields={[
            { key: "domain", label: "Website/domain (CyberPanel)", placeholder: "example.com" },
            { key: "db_name", label: "Database name", placeholder: "myapp_db", required: true },
            { key: "db_user", label: "DB user", placeholder: "myapp_user" },
            { key: "db_password", label: "DB password", type: "password" },
          ]}
          initialValues={{ domain: dbDomain ?? "" }}
          isPending={createDbMut.isPending}
          error={createDbMut.isError ? errMsg(createDbMut.error) : undefined}
          onClose={() => setModal(null)}
          onSubmit={(v) => createDbMut.mutate(v)}
        />
      )}
      {modal === "email" && (
        <FieldModal
          title="New email account"
          fields={[
            { key: "user", label: "Mailbox name", placeholder: "info", required: true },
            { key: "domain", label: "Domain", placeholder: "example.com", required: true },
            { key: "password", label: "Password", type: "password", required: true },
          ]}
          isPending={createEmailMut.isPending}
          error={createEmailMut.isError ? errMsg(createEmailMut.error) : undefined}
          onClose={() => setModal(null)}
          onSubmit={(v) => createEmailMut.mutate(v)}
        />
      )}
    </div>
  )
}

function EmptyState({ icon: Icon, text }: { icon: typeof Globe; text: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center rounded-xl border border-dashed border-border">
      <Icon className="h-10 w-10 text-muted-foreground/30 mb-3" />
      <p className="text-sm text-muted-foreground">{text}</p>
    </div>
  )
}

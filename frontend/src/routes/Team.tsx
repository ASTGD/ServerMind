import { useMemo, useState } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { formatDistanceToNow } from "date-fns"
import {
  Users,
  UserPlus,
  Mail,
  Shield,
  ShieldCheck,
  Eye,
  Trash2,
  Loader2,
  X,
  Copy,
  Check,
  Server as ServerIcon,
  Clock,
  CircleSlash,
  KeyRound,
} from "lucide-react"
import {
  listTeam,
  inviteMember,
  updateMemberRole,
  removeMember,
  getMemberAccess,
  setMemberAccess,
  type TeamMember,
  type Role,
  type ServerAccessItem,
} from "@/api/team"
import { listServers } from "@/api/servers"
import { Button, EmptyState } from "@/components/ui"

// ── Role config ──────────────────────────────────────────────────────────────

const ROLE_META: Record<Role, { label: string; desc: string; Icon: typeof Shield; text: string; bg: string }> = {
  admin: { label: "Admin", desc: "Full access to all your servers + can run commands", Icon: ShieldCheck, text: "text-violet-400", bg: "bg-violet-500/10" },
  operator: { label: "Operator", desc: "Can run commands on the servers you grant", Icon: Shield, text: "text-blue-400", bg: "bg-blue-500/10" },
  viewer: { label: "Viewer", desc: "Read-only — can never run commands", Icon: Eye, text: "text-slate-400", bg: "bg-slate-500/10" },
}

function RoleBadge({ role }: { role: Role | null }) {
  if (!role) return null
  const m = ROLE_META[role]
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${m.text} ${m.bg}`}>
      <m.Icon className="h-3 w-3" />
      {m.label}
    </span>
  )
}

// ── Invite modal ───────────────────────────────────────────────────────────

function InviteModal({
  onClose,
  onInvite,
  isPending,
  error,
}: {
  onClose: () => void
  onInvite: (email: string, role: Role) => void
  isPending: boolean
  error?: string
}) {
  const [email, setEmail] = useState("")
  const [role, setRole] = useState<Role>("viewer")
  const valid = /\S+@\S+\.\S+/.test(email)
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-xl shadow-2xl w-full max-w-md p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-foreground">Invite a team member</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground mb-1 block">Email</label>
          <input
            autoFocus
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="teammate@company.com"
            className="w-full rounded-lg border border-border bg-background text-sm text-foreground px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
        </div>
        <div>
          <label className="text-xs font-medium text-muted-foreground mb-1 block">Role</label>
          <div className="space-y-2">
            {(Object.keys(ROLE_META) as Role[]).map((r) => {
              const m = ROLE_META[r]
              const active = role === r
              return (
                <button
                  key={r}
                  onClick={() => setRole(r)}
                  className={`flex w-full items-start gap-2.5 rounded-lg border px-3 py-2 text-left transition-colors ${
                    active ? "border-primary/50 bg-primary/5" : "border-border hover:bg-muted/40"
                  }`}
                >
                  <m.Icon className={`h-4 w-4 mt-0.5 ${m.text}`} />
                  <div>
                    <div className="text-sm font-medium text-foreground">{m.label}</div>
                    <div className="text-xs text-muted-foreground">{m.desc}</div>
                  </div>
                </button>
              )
            })}
          </div>
        </div>
        {error && (
          <div className="rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</div>
        )}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground border border-border rounded-lg hover:bg-muted/50 transition-colors">Cancel</button>
          <button
            onClick={() => valid && onInvite(email.trim().toLowerCase(), role)}
            disabled={!valid || isPending}
            className="flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            Send invite
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Access editor ─────────────────────────────────────────────────────────

function AccessEditor({ member, onClose }: { member: TeamMember; onClose: () => void }) {
  const qc = useQueryClient()
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers })
  const { data: access = [], isLoading } = useQuery({
    queryKey: ["member-access", member.id],
    queryFn: () => getMemberAccess(member.id),
  })

  // Local editable map: server_id -> {enabled, can_execute, can_view_logs}
  const [draft, setDraft] = useState<Record<string, { enabled: boolean; can_execute: boolean; can_view_logs: boolean }> | null>(null)

  const current = useMemo(() => {
    if (draft) return draft
    const map: Record<string, { enabled: boolean; can_execute: boolean; can_view_logs: boolean }> = {}
    for (const s of servers) {
      const a = access.find((x) => x.server_id === s.id)
      map[s.id] = {
        enabled: !!a,
        can_execute: a?.can_execute ?? false,
        can_view_logs: a?.can_view_logs ?? true,
      }
    }
    return map
  }, [draft, servers, access])

  const update = (sid: string, patch: Partial<{ enabled: boolean; can_execute: boolean; can_view_logs: boolean }>) => {
    setDraft({ ...current, [sid]: { ...current[sid], ...patch } })
  }

  const saveMut = useMutation({
    mutationFn: () => {
      const items: ServerAccessItem[] = Object.entries(current)
        .filter(([, v]) => v.enabled)
        .map(([server_id, v]) => ({ server_id, can_execute: v.can_execute, can_view_logs: v.can_view_logs }))
      return setMemberAccess(member.id, items)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["member-access", member.id] })
      onClose()
    },
  })

  const isAdmin = member.role === "admin"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-xl shadow-2xl w-full max-w-2xl p-5 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-semibold text-foreground">Server access</h3>
            <p className="text-xs text-muted-foreground">{member.invited_email}</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
        </div>

        {isAdmin ? (
          <div className="rounded-lg border border-violet-500/20 bg-violet-500/5 px-4 py-3 text-sm text-violet-300 flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 shrink-0" />
            Admins automatically have full access to all your servers — no per-server grants needed.
          </div>
        ) : isLoading ? (
          <div className="flex items-center gap-2 py-6 text-muted-foreground text-sm"><Loader2 className="h-4 w-4 animate-spin" />Loading…</div>
        ) : servers.length === 0 ? (
          <p className="text-sm text-muted-foreground py-6 text-center">You have no servers to grant access to yet.</p>
        ) : (
          <>
            <div className="space-y-2">
              {servers.map((s) => {
                const row = current[s.id]
                const isViewer = member.role === "viewer"
                return (
                  <div key={s.id} className="rounded-lg border border-border p-3">
                    <div className="flex items-center justify-between">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" checked={row?.enabled ?? false} onChange={(e) => update(s.id, { enabled: e.target.checked })} className="rounded border-border" />
                        <ServerIcon className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm text-foreground font-medium">{s.name}</span>
                        <span className="text-xs text-muted-foreground font-mono">{s.host}</span>
                      </label>
                    </div>
                    {row?.enabled && (
                      <div className="mt-2 ml-7 flex items-center gap-4 text-xs">
                        <label className="flex items-center gap-1.5 text-muted-foreground">
                          <input type="checkbox" checked={row.can_view_logs} onChange={(e) => update(s.id, { can_view_logs: e.target.checked })} className="rounded border-border" />
                          View logs
                        </label>
                        <label className={`flex items-center gap-1.5 ${isViewer ? "opacity-40" : "text-muted-foreground"}`} title={isViewer ? "Viewers can never execute" : undefined}>
                          <input type="checkbox" checked={row.can_execute && !isViewer} disabled={isViewer} onChange={(e) => update(s.id, { can_execute: e.target.checked })} className="rounded border-border" />
                          Run commands
                        </label>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
            {member.role === "viewer" && (
              <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                <CircleSlash className="h-3 w-3" />
                This member is a viewer — the "run commands" permission is enforced off regardless of this setting.
              </p>
            )}
            <div className="flex justify-end gap-2">
              <button onClick={onClose} className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground border border-border rounded-lg hover:bg-muted/50 transition-colors">Cancel</button>
              <button onClick={() => saveMut.mutate()} disabled={saveMut.isPending}
                className="flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors">
                {saveMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Save access
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

// ── Invite link banner ─────────────────────────────────────────────────────

function InviteLink({ token, onDone }: { token: string; onDone: () => void }) {
  const [copied, setCopied] = useState(false)
  const link = `${window.location.origin}/team/accept/${token}`
  return (
    <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-emerald-300">
          <KeyRound className="h-4 w-4 shrink-0" />
          Invitation created — share this link:
        </div>
        <button onClick={onDone} className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
      </div>
      <div className="mt-2 flex items-center gap-2">
        <code className="flex-1 truncate rounded bg-background border border-border px-2 py-1 text-xs text-foreground">{link}</code>
        <button
          onClick={() => { void navigator.clipboard.writeText(link); setCopied(true); window.setTimeout(() => setCopied(false), 1500) }}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors shrink-0"
        >
          {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function Team() {
  const qc = useQueryClient()
  const [showInvite, setShowInvite] = useState(false)
  const [accessFor, setAccessFor] = useState<TeamMember | null>(null)
  const [confirmRemove, setConfirmRemove] = useState<TeamMember | null>(null)
  const [newInviteToken, setNewInviteToken] = useState<string | null>(null)

  const { data: members = [], isLoading } = useQuery({ queryKey: ["team"], queryFn: listTeam })

  const inviteMut = useMutation({
    mutationFn: ({ email, role }: { email: string; role: Role }) => inviteMember(email, role),
    onSuccess: (m) => {
      setShowInvite(false)
      if (m.invite_token) setNewInviteToken(m.invite_token)
      qc.invalidateQueries({ queryKey: ["team"] })
    },
  })
  const roleMut = useMutation({
    mutationFn: ({ id, role }: { id: string; role: Role }) => updateMemberRole(id, role),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["team"] }),
  })
  const removeMut = useMutation({
    mutationFn: (id: string) => removeMember(id),
    onSuccess: () => { setConfirmRemove(null); qc.invalidateQueries({ queryKey: ["team"] }) },
  })

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-h1 text-foreground flex items-center gap-2">
            <Users className="h-6 w-6 text-primary" />
            Team
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Invite people and control which servers they can view or run commands on.
          </p>
        </div>
        <Button onClick={() => setShowInvite(true)} className="shrink-0">
          <UserPlus className="h-4 w-4" />Invite
        </Button>
      </div>

      {newInviteToken && <InviteLink token={newInviteToken} onDone={() => setNewInviteToken(null)} />}

      {isLoading && (
        <div className="flex items-center gap-2 py-12 text-muted-foreground text-sm"><Loader2 className="h-4 w-4 animate-spin" />Loading team…</div>
      )}

      {!isLoading && members.length === 0 && (
        <EmptyState
          icon={Users}
          title="No team members yet"
          description="Invite teammates and assign roles to collaborate on your servers."
          action={
            <Button onClick={() => setShowInvite(true)}>
              <UserPlus className="h-4 w-4" />Invite your first member
            </Button>
          }
        />
      )}

      <div className="space-y-2">
        {members.map((m) => (
          <div key={m.id} className="rounded-xl border border-border bg-card p-4 flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="h-9 w-9 rounded-full bg-muted flex items-center justify-center shrink-0">
                <Mail className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-foreground truncate">{m.invited_email}</span>
                  <RoleBadge role={m.role} />
                  {m.invite_accepted ? (
                    <span className="text-[11px] text-emerald-400 flex items-center gap-1"><Check className="h-3 w-3" />active</span>
                  ) : (
                    <span className="text-[11px] text-amber-400 flex items-center gap-1"><Clock className="h-3 w-3" />pending</span>
                  )}
                </div>
                <p className="text-xs text-muted-foreground mt-0.5">invited {formatDistanceToNow(new Date(m.created_at), { addSuffix: true })}</p>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <select
                value={m.role ?? "viewer"}
                onChange={(e) => roleMut.mutate({ id: m.id, role: e.target.value as Role })}
                className="rounded-lg border border-border bg-background text-xs text-foreground px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary/40"
              >
                <option value="viewer">Viewer</option>
                <option value="operator">Operator</option>
                <option value="admin">Admin</option>
              </select>
              <button onClick={() => setAccessFor(m)} disabled={m.role === "admin"} title={m.role === "admin" ? "Admins have full access" : "Manage server access"}
                className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-muted/50 hover:text-foreground disabled:opacity-40 transition-colors">
                <ServerIcon className="h-3.5 w-3.5" />Access
              </button>
              <button onClick={() => setConfirmRemove(m)} title="Remove" className="p-1.5 rounded text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors">
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {showInvite && (
        <InviteModal
          isPending={inviteMut.isPending}
          error={(inviteMut.error as Error | null)?.message}
          onClose={() => setShowInvite(false)}
          onInvite={(email, role) => inviteMut.mutate({ email, role })}
        />
      )}

      {accessFor && <AccessEditor member={accessFor} onClose={() => setAccessFor(null)} />}

      {confirmRemove && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded-xl border border-border bg-card p-6 shadow-xl">
            <h3 className="font-semibold text-foreground">Remove {confirmRemove.invited_email}?</h3>
            <p className="mt-2 text-sm text-muted-foreground">They will immediately lose all access to your servers.</p>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setConfirmRemove(null)} className="rounded-md px-4 py-2 text-sm text-muted-foreground hover:bg-accent">Cancel</button>
              <button onClick={() => removeMut.mutate(confirmRemove.id)} disabled={removeMut.isPending}
                className="flex items-center gap-2 rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50">
                {removeMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Remove
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

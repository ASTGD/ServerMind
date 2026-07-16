import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Search, ArrowLeft, Server as ServerIcon, ExternalLink, ShieldCheck } from "lucide-react"
import { getAdminUsers, getAdminUser } from "@/api/dev"
import type { AdminUser } from "@/api/dev"

const money = (n: number) => `$${n.toFixed(2)}`
const when = (s: string | null) => (s ? new Date(s).toLocaleDateString() : "—")

/** A meter as "used / limit", amber at 80%, red at the wall. The whole plan model is
 *  two numbers (PRICING-FREE-VS-PRO v2), so this is the only widget the console needs. */
function Meter({ used, limit }: { used: number; limit: number }) {
  const pct = limit > 0 ? (used / limit) * 100 : 0
  const tone =
    pct >= 100 ? "text-red-600 dark:text-red-400"
      : pct >= 80 ? "text-amber-600 dark:text-amber-400"
        : "text-foreground"
  return (
    <span className={`tabular-nums ${tone}`}>
      {used} <span className="text-muted-foreground">/ {limit}</span>
    </span>
  )
}

function PlanBadge({ plan }: { plan: string }) {
  const pro = plan === "pro"
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
        pro
          ? "bg-primary/10 text-primary"
          : "bg-muted text-muted-foreground"
      }`}
    >
      {plan}
    </span>
  )
}

function Detail({ id, onBack }: { id: string; onBack: () => void }) {
  const { data: u, isLoading } = useQuery({
    queryKey: ["admin-user", id],
    queryFn: () => getAdminUser(id),
  })

  if (isLoading) return <div className="h-40 animate-pulse rounded-lg border border-border bg-card" />
  if (!u) return <p className="text-sm text-muted-foreground">User not found.</p>

  return (
    <div className="space-y-4">
      <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft size={14} /> All users
      </button>

      {/* Identity + plan. Plan is a MIRROR — it is changed in WHMCS, never here. */}
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-foreground">{u.email}</h3>
              <PlanBadge plan={u.plan} />
              {u.is_admin && (
                <span className="flex items-center gap-1 rounded-full bg-violet-500/10 px-2 py-0.5 text-xs font-medium text-violet-600 dark:text-violet-400">
                  <ShieldCheck size={11} /> staff
                </span>
              )}
              {!u.is_active && (
                <span className="rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-medium text-red-600 dark:text-red-400">
                  deactivated
                </span>
              )}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">
              {u.name || "no name"} · joined {when(u.created_at)} · {u.preferred_language} ·
              Ally mode: {u.ally_mode} · 2FA {u.totp_enabled ? "on" : "off"}
              {!u.is_verified && " · unverified"}
            </p>
          </div>
          <div className="text-right text-sm">
            <p className="text-muted-foreground">AI cost this month</p>
            <p className="text-lg font-semibold tabular-nums text-foreground">{money(u.ai_cost_usd)}</p>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-6 border-t border-border pt-3 text-sm">
          <span className="text-muted-foreground">
            Actions <Meter used={u.actions_used} limit={u.actions_limit} />
          </span>
          <span className="text-muted-foreground">
            Servers <Meter used={u.servers_used} limit={u.servers_limit} />
          </span>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Plan is set by WHMCS — change it there, not here.
        </p>
      </div>

      {/* Their servers — identity + health only. Credentials are never sent to this UI. */}
      <Section title={`Servers (${u.servers.length})`}>
        {u.servers.length === 0 ? (
          <Empty>No servers.</Empty>
        ) : (
          u.servers.map((s) => (
            <Row key={s.id}>
              <span className="flex items-center gap-2 text-foreground">
                <ServerIcon size={13} className="text-muted-foreground" />
                {s.name}
              </span>
              <span className="text-muted-foreground">{s.host}</span>
              <span className="text-muted-foreground">{s.os_type || s.connection_type}</span>
              <span className={s.status === "online" ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"}>
                {s.status}
              </span>
            </Row>
          ))
        )}
      </Section>

      <Section title="Recent missions">
        {u.missions.length === 0 ? (
          <Empty>No missions yet.</Empty>
        ) : (
          u.missions.map((m) => (
            <Row key={m.id}>
              <span className="truncate text-foreground" title={m.goal}>{m.goal}</span>
              <span className="text-muted-foreground">{m.server_name || "—"}</span>
              <span className="text-muted-foreground">{m.status}</span>
              <span className={m.verified ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"}>
                {m.verified === null ? "—" : m.verified ? "verified" : "unverified"}
              </span>
            </Row>
          ))
        )}
      </Section>

      {/* The "what went wrong for them" list — the reason support opens this page. */}
      <Section title="Recent failures & blocks">
        {u.problems.length === 0 ? (
          <Empty>Nothing failed or was blocked. </Empty>
        ) : (
          u.problems.map((p, i) => (
            <Row key={i}>
              <span className="truncate text-foreground" title={p.request}>{p.request}</span>
              <span className={p.status === "blocked" ? "text-amber-600 dark:text-amber-400" : "text-red-600 dark:text-red-400"}>
                {p.status}
              </span>
              <span className="text-muted-foreground">{p.risk_level || "—"}</span>
              <span className="text-muted-foreground">{when(p.created_at)}</span>
            </Row>
          ))
        )}
      </Section>

      <Section title="Plan history (from billing)">
        {u.entitlements.length === 0 ? (
          <Empty>No billing events — this account was never touched by WHMCS.</Empty>
        ) : (
          u.entitlements.map((e, i) => (
            <Row key={i}>
              <span className="text-foreground">{e.plan}</span>
              <span className="text-muted-foreground">{e.action.replace("entitlement.", "")}</span>
              <span className="truncate text-muted-foreground">{e.reference || "—"}</span>
              <span className="text-muted-foreground">{when(e.created_at)}</span>
            </Row>
          ))
        )}
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card">
      <p className="border-b border-border px-4 py-2 text-xs font-medium text-muted-foreground">{title}</p>
      <div className="divide-y divide-border">{children}</div>
    </div>
  )
}
const Row = ({ children }: { children: React.ReactNode }) => (
  <div className="grid grid-cols-[1.6fr_1fr_0.8fr_0.8fr] gap-3 px-4 py-2 text-sm">{children}</div>
)
const Empty = ({ children }: { children: React.ReactNode }) => (
  <p className="px-4 py-3 text-sm text-muted-foreground">{children}</p>
)

/** Users — the operator console's support screen. Read-only by construction: there is
 *  no control here that can change a customer's account (that's 5b, each audit-logged). */
export default function AdminUsers() {
  const [q, setQ] = useState("")
  const [selected, setSelected] = useState<string | null>(null)
  const { data: users = [], isLoading } = useQuery<AdminUser[]>({
    queryKey: ["admin-users", q],
    queryFn: () => getAdminUsers(q || undefined),
  })

  if (selected) return <Detail id={selected} onBack={() => setSelected(null)} />

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search by email…"
          className="h-9 w-full rounded-md border border-border bg-background pl-9 pr-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary"
        />
      </div>

      <div className="overflow-x-auto rounded-lg border border-border bg-card">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted-foreground">
              <th className="px-4 py-2 font-medium">Email</th>
              <th className="px-4 py-2 font-medium">Plan</th>
              <th className="px-4 py-2 font-medium">Actions</th>
              <th className="px-4 py-2 font-medium">Servers</th>
              <th className="px-4 py-2 font-medium">AI cost</th>
              <th className="px-4 py-2 font-medium">Joined</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading ? (
              <tr><td colSpan={6} className="px-4 py-6 text-center text-muted-foreground">Loading…</td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan={6} className="px-4 py-6 text-center text-muted-foreground">No users match.</td></tr>
            ) : (
              users.map((u) => (
                <tr
                  key={u.id}
                  onClick={() => setSelected(u.id)}
                  className="cursor-pointer hover:bg-muted/50"
                >
                  <td className="px-4 py-2">
                    <span className="flex items-center gap-2 text-foreground">
                      {u.email}
                      {u.is_admin && <ShieldCheck size={12} className="text-violet-500" />}
                      {!u.is_active && <span className="text-xs text-red-500">deactivated</span>}
                    </span>
                  </td>
                  <td className="px-4 py-2"><PlanBadge plan={u.plan} /></td>
                  <td className="px-4 py-2"><Meter used={u.actions_used} limit={u.actions_limit} /></td>
                  <td className="px-4 py-2"><Meter used={u.servers_used} limit={u.servers_limit} /></td>
                  <td className="px-4 py-2 tabular-nums text-muted-foreground">{money(u.ai_cost_usd)}</td>
                  <td className="px-4 py-2 text-muted-foreground">{when(u.created_at)}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
        <ExternalLink size={12} />
        Billing, invoices and orders live in WHMCS. Plans shown here mirror WHMCS's decision.
      </p>
    </div>
  )
}

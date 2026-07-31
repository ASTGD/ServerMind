import { useState } from "react"
import { useOutletContext } from "react-router-dom"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { AlertTriangle, Database, Loader2, Lock, Plus, Trash2 } from "lucide-react"
import {
  createDatabase, dropDatabase, getDatabases,
  type DatabaseEngine, type DatabaseRow,
} from "@/api/databases"
import { Button, EmptyState } from "@/components/ui"
import type { Server } from "@/types"

/**
 * The databases on this server.
 *
 * A site installer creates one and it then disappears from view — the customer cannot see
 * it, add a second, or find out which user owns it. Their data lives there.
 *
 * Read fresh on every visit. A cached list drifts the moment anything else touches the
 * server, and a database shown as present when it is gone is worse than showing nothing,
 * because someone will point an application at it.
 */

/** Long, mixed, and generated here so the customer never has to invent one. */
function strongPassword(): string {
  const alphabet = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
  const bytes = new Uint32Array(24)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => alphabet[b % alphabet.length]).join("")
}

function sizeLabel(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`
  if (mb >= 1) return `${mb.toFixed(1)} MB`
  return "empty"
}

export default function ServerDatabases() {
  const { server } = useOutletContext<{ server: Server }>()
  const qc = useQueryClient()
  const [adding, setAdding] = useState<string | null>(null)
  const [removing, setRemoving] = useState<{ engine: string; db: DatabaseRow } | null>(null)
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null)

  const { data, isLoading } = useQuery({
    queryKey: ["databases", server.id],
    queryFn: () => getDatabases(server.id),
  })

  const refresh = () => qc.invalidateQueries({ queryKey: ["databases", server.id] })

  if (isLoading) {
    return (
      <div className="flex justify-center py-16 text-muted-foreground">
        <Loader2 size={20} className="animate-spin" />
      </div>
    )
  }

  const engines = data?.engines ?? []

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-h2 text-foreground">Databases</h2>
        <p className="mt-0.5 text-small text-muted-foreground">
          Where your websites and applications keep their data.
        </p>
      </div>

      {note && (
        <p
          className={`rounded-lg border-l-2 px-3 py-2 text-small ${
            note.ok
              ? "border-emerald-500 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400"
              : "border-destructive bg-destructive/5 text-destructive"
          }`}
        >
          {note.text}
        </p>
      )}

      {!data?.reachable && (
        <EmptyState
          icon={AlertTriangle}
          title="We could not look at this server"
          description="It did not answer. Check it is online, then try again."
        />
      )}

      {data?.reachable && engines.length === 0 && (
        <EmptyState
          icon={Database}
          title="No database server here yet"
          description="Nothing on this server stores data yet. Installing WordPress or Laravel sets up MySQL for you, or ask Ally to install a database server."
        />
      )}

      {engines.map((engine) => (
        <EngineCard
          key={engine.engine}
          engine={engine}
          onAdd={() => setAdding(engine.engine)}
          onRemove={(db) => setRemoving({ engine: engine.engine, db })}
        />
      ))}

      {adding && (
        <AddDialog
          serverId={server.id}
          engine={adding}
          onClose={() => setAdding(null)}
          onDone={(name) => {
            setAdding(null)
            setNote({ ok: true, text: `Database "${name}" is ready.` })
            refresh()
          }}
        />
      )}

      {removing && (
        <RemoveDialog
          serverId={server.id}
          engine={removing.engine}
          db={removing.db}
          users={engines.find((e) => e.engine === removing.engine)?.users ?? []}
          onClose={() => setRemoving(null)}
          onDone={(name) => {
            setRemoving(null)
            setNote({ ok: true, text: `Database "${name}" was deleted.` })
            refresh()
          }}
        />
      )}
    </div>
  )
}

function EngineCard({ engine, onAdd, onRemove }: {
  engine: DatabaseEngine
  onAdd: () => void
  onRemove: (db: DatabaseRow) => void
}) {
  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div>
          <p className="text-sm font-medium text-foreground">{engine.label}</p>
          <p className="text-caption text-muted-foreground">
            {engine.version ? `Version ${engine.version}` : "Installed"}
            {engine.readable && ` · ${engine.databases.length} database${
              engine.databases.length === 1 ? "" : "s"}`}
          </p>
        </div>
        {engine.readable && (
          <Button size="sm" onClick={onAdd}>
            <Plus size={14} /> New database
          </Button>
        )}
      </div>

      {/* Installed but we could not sign in. Saying "no databases" here would be a lie
          that invites someone to create one that already exists. */}
      {!engine.readable ? (
        <div className="flex items-start gap-3 px-4 py-5">
          <Lock size={16} className="mt-0.5 text-muted-foreground" />
          <div>
            <p className="text-sm text-foreground">We could not sign in to {engine.label}</p>
            <p className="mt-0.5 text-small text-muted-foreground">
              It is installed on this server, but not reachable with the usual
              administrator access, so we cannot show what is in it. Ask Ally to take a look.
            </p>
          </div>
        </div>
      ) : engine.databases.length === 0 ? (
        <p className="px-4 py-5 text-small text-muted-foreground">
          Nothing in here yet.
        </p>
      ) : (
        <table className="w-full text-small">
          <thead>
            <tr className="text-caption text-muted-foreground">
              <th className="px-4 py-2 text-left font-medium">Name</th>
              <th className="px-4 py-2 text-right font-medium">Size</th>
              <th className="px-4 py-2 text-right font-medium">Tables</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {engine.databases.map((db) => (
              <tr key={db.name} className="border-t border-border">
                <td className="px-4 py-2.5 font-mono text-foreground">{db.name}</td>
                <td className="px-4 py-2.5 text-right tabular-nums text-muted-foreground">
                  {sizeLabel(db.size_mb)}
                </td>
                <td className="px-4 py-2.5 text-right tabular-nums text-muted-foreground">
                  {db.tables ?? "—"}
                </td>
                <td className="px-4 py-2.5 text-right">
                  <button
                    onClick={() => onRemove(db)}
                    className="rounded-md p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    title={`Delete ${db.name}`}
                  >
                    <Trash2 size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {engine.readable && engine.users.length > 0 && (
        <div className="border-t border-border px-4 py-2.5">
          <p className="text-caption text-muted-foreground">
            Users: {engine.users.map((u) => u.name).join(", ")}
          </p>
        </div>
      )}
    </div>
  )
}

function AddDialog({ serverId, engine, onClose, onDone }: {
  serverId: string
  engine: string
  onClose: () => void
  onDone: (name: string) => void
}) {
  const [name, setName] = useState("")
  const [user, setUser] = useState("")
  // Generated up front so the common path is: type a name, press the button. A customer
  // asked to invent a database password picks a weak one.
  const [password, setPassword] = useState(strongPassword)
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () => createDatabase(serverId, { engine, name, user: user || name, password }),
    onSuccess: (r) => onDone(r.name),
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "The database could not be created."),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-20">
      <div className="w-full max-w-lg rounded-xl border border-border bg-card p-5 shadow-xl">
        <h3 className="text-h3 text-foreground">New database</h3>
        <p className="mt-0.5 text-small text-muted-foreground">
          A database and a user with rights to that one database only.
        </p>

        <form
          onSubmit={(e) => { e.preventDefault(); setError(null); create.mutate() }}
          className="mt-4 space-y-3"
        >
          <div>
            <label className="text-caption text-muted-foreground">Database name</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="my_shop"
              required
              autoFocus
              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground"
            />
            <p className="mt-1 text-caption text-muted-foreground">
              Letters, numbers and underscores.
            </p>
          </div>

          <div>
            <label className="text-caption text-muted-foreground">User name</label>
            <input
              value={user}
              onChange={(e) => setUser(e.target.value)}
              placeholder={name || "my_shop"}
              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground"
            />
            <p className="mt-1 text-caption text-muted-foreground">
              Leave empty to use the same name as the database.
            </p>
          </div>

          <div>
            <label className="text-caption text-muted-foreground">Password</label>
            <div className="mt-1 flex gap-2">
              {/* Shown, not hidden: it has to be copied into an application's settings,
                  and this is the only time it is ever displayed. */}
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground"
              />
              <Button type="button" variant="outline" size="sm"
                      onClick={() => setPassword(strongPassword())}>
                New
              </Button>
            </div>
            <p className="mt-1 text-caption text-amber-600 dark:text-amber-400">
              Copy this now — it is not stored anywhere and cannot be shown again.
            </p>
          </div>

          {error && (
            <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-destructive">
              {error}
            </p>
          )}

          <div className="flex items-center gap-2 pt-1">
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Create database"}
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  )
}

function RemoveDialog({ serverId, engine, db, users, onClose, onDone }: {
  serverId: string
  engine: string
  db: DatabaseRow
  users: { name: string }[]
  onClose: () => void
  onDone: (name: string) => void
}) {
  const [typed, setTyped] = useState("")
  const [dropUser, setDropUser] = useState<string>("")
  const [error, setError] = useState<string | null>(null)

  const remove = useMutation({
    mutationFn: () => dropDatabase(serverId, {
      engine, name: db.name, confirm_name: typed, drop_user: dropUser || null,
    }),
    onSuccess: (r) => onDone(r.name),
    onError: (e: { response?: { data?: { detail?: string } } }) =>
      setError(e.response?.data?.detail ?? "The database could not be deleted."),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-20">
      <div className="w-full max-w-lg rounded-xl border border-border bg-card p-5 shadow-xl">
        <h3 className="text-h3 text-foreground">Delete {db.name}</h3>

        <div className="mt-3 flex items-start gap-3 rounded-lg border-l-2 border-destructive bg-destructive/5 p-3">
          <AlertTriangle size={16} className="mt-0.5 shrink-0 text-destructive" />
          <p className="text-small text-destructive">
            Everything in this database is deleted, and there is no copy of it here. Any
            website using it will stop working. This cannot be undone.
          </p>
        </div>

        <form
          onSubmit={(e) => { e.preventDefault(); setError(null); remove.mutate() }}
          className="mt-4 space-y-3"
        >
          <div>
            <label className="text-caption text-muted-foreground">
              Type <span className="font-mono text-foreground">{db.name}</span> to confirm
            </label>
            <input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoFocus
              className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-sm text-foreground"
            />
          </div>

          {users.length > 0 && (
            <div>
              <label className="text-caption text-muted-foreground">
                Also delete a user (optional)
              </label>
              <select
                value={dropUser}
                onChange={(e) => setDropUser(e.target.value)}
                className="mt-1 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-sm text-foreground"
              >
                <option value="">Keep all users</option>
                {users.map((u) => (
                  <option key={u.name} value={u.name}>{u.name}</option>
                ))}
              </select>
            </div>
          )}

          {error && (
            <p className="rounded-lg border-l-2 border-destructive bg-destructive/5 px-3 py-2 text-small text-destructive">
              {error}
            </p>
          )}

          <div className="flex items-center gap-2 pt-1">
            <Button type="submit" variant="danger"
                    disabled={remove.isPending || typed !== db.name}>
              {remove.isPending ? "Deleting…" : "Delete this database"}
            </Button>
            <Button type="button" variant="ghost" onClick={onClose}>Cancel</Button>
          </div>
        </form>
      </div>
    </div>
  )
}

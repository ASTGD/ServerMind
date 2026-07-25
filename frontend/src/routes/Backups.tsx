import { useEffect, useMemo, useState } from "react"
import { useParams } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import DestinationManager from "@/components/backups/DestinationManager"
import { formatDistanceToNow } from "date-fns"
import {
  Database,
  FolderArchive,
  HardDriveDownload,
  Plus,
  Play,
  RotateCcw,
  Trash2,
  Pencil,
  Clock,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  X,
  CalendarClock,
  Cloud,
} from "lucide-react"
import {
  listBackups,
  createBackup,
  updateBackup,
  deleteBackup,
  runBackup,
  backupHistory,
  restoreBackup,
  listDestinations,
  type Backup,
  type BackupRun,
  type BackupType,
  type BackupCreateBody,
} from "@/api/backups"
import { parseSchedule } from "@/api/scheduler"
import { Button, EmptyState } from "@/components/ui"

// ── Helpers ──────────────────────────────────────────────────────────────────

function fmtBytes(n: number | null): string {
  if (n == null) return "—"
  if (n < 1024) return `${n} B`
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`
  return `${(n / 1024 ** 3).toFixed(2)} GB`
}

const TYPE_META: Record<BackupType, { label: string; Icon: typeof Database; sourceLabel: string; sourcePlaceholder: string }> = {
  files: { label: "Files", Icon: FolderArchive, sourceLabel: "Directory to back up", sourcePlaceholder: "/var/www" },
  mysql: { label: "MySQL", Icon: Database, sourceLabel: "Database name", sourcePlaceholder: "my_database" },
  postgres: { label: "PostgreSQL", Icon: Database, sourceLabel: "Database name", sourcePlaceholder: "my_database" },
}

function StatusPill({ status }: { status: string | null }) {
  if (!status) return <span className="text-xs text-muted-foreground">never run</span>
  if (status === "success")
    return <span className="inline-flex items-center gap-1 text-xs text-emerald-400"><CheckCircle2 className="h-3 w-3" />success</span>
  if (status === "running")
    return <span className="inline-flex items-center gap-1 text-xs text-blue-400"><Loader2 className="h-3 w-3 animate-spin" />running</span>
  return <span className="inline-flex items-center gap-1 text-xs text-red-400"><XCircle className="h-3 w-3" />failed</span>
}

// ── New / Edit modal ─────────────────────────────────────────────────────────

interface FormState {
  name: string
  backup_type: BackupType
  source: string
  dest_dir: string
  db_user: string
  db_password: string
  retention: number
  schedule: string
  destination_id: string
  keep_local: boolean
}

function BackupModal({
  initial,
  onClose,
  onSubmit,
  isPending,
  error,
}: {
  initial?: Backup
  onClose: () => void
  onSubmit: (body: BackupCreateBody) => void
  isPending: boolean
  error?: string
}) {
  const [form, setForm] = useState<FormState>({
    name: initial?.name ?? "",
    backup_type: initial?.backup_type ?? "files",
    source: initial?.source ?? "",
    dest_dir: initial?.dest_dir ?? "/var/backups/servermind",
    db_user: initial?.db_user ?? "",
    db_password: "",
    retention: initial?.retention ?? 7,
    schedule: initial?.human_schedule ?? "",
    destination_id: initial?.destination_id ?? "",
    keep_local: initial?.keep_local ?? true,
  })
  // Offsite destinations are user-level, so the picker shares the manager's cache.
  const { data: destinations = [] } = useQuery({
    queryKey: ["backup-destinations"],
    queryFn: listDestinations,
  })
  const [cron, setCron] = useState<string | null>(initial?.cron_expression ?? null)
  const [cronDesc, setCronDesc] = useState<string | null>(null)
  const [parsing, setParsing] = useState(false)

  const isDb = form.backup_type !== "files"
  const meta = TYPE_META[form.backup_type]

  // Debounced natural-language → cron preview
  useEffect(() => {
    const text = form.schedule.trim()
    if (!text) {
      setCron(null)
      setCronDesc(null)
      return
    }
    setParsing(true)
    const t = window.setTimeout(async () => {
      try {
        const r = await parseSchedule(text)
        setCron(r.cron_expression)
        setCronDesc(r.human_description)
      } catch {
        setCron(null)
        setCronDesc(null)
      } finally {
        setParsing(false)
      }
    }, 700)
    return () => window.clearTimeout(t)
  }, [form.schedule])

  const valid = form.name.trim() && form.source.trim()

  const submit = () => {
    if (!valid) return
    const body: BackupCreateBody = {
      name: form.name.trim(),
      backup_type: form.backup_type,
      source: form.source.trim(),
      dest_dir: form.dest_dir.trim() || "/var/backups/servermind",
      destination_id: form.destination_id || null,
      keep_local: form.keep_local,
      retention: form.retention,
      cron_expression: form.schedule.trim() ? cron : null,
      human_schedule: form.schedule.trim() || null,
    }
    if (isDb) {
      body.db_user = form.db_user.trim() || null
      if (form.db_password) body.db_password = form.db_password
    }
    onSubmit(body)
  }

  const input = "w-full rounded-lg border border-border bg-background text-sm text-foreground px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary/40"
  const label = "text-xs font-medium text-muted-foreground mb-1 block"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-card border border-border rounded-xl shadow-2xl w-full max-w-lg p-5 space-y-4 max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-foreground">{initial ? "Edit Backup" : "New Backup"}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X className="h-4 w-4" /></button>
        </div>

        <div>
          <label className={label}>Name</label>
          <input className={input} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Nightly web files" autoFocus />
        </div>

        <div>
          <label className={label}>Type</label>
          <div className="grid grid-cols-3 gap-2">
            {(Object.keys(TYPE_META) as BackupType[]).map((t) => {
              const M = TYPE_META[t]
              const active = form.backup_type === t
              return (
                <button
                  key={t}
                  onClick={() => setForm({ ...form, backup_type: t })}
                  className={`flex items-center justify-center gap-1.5 rounded-lg border px-2 py-2 text-sm transition-colors ${
                    active ? "border-primary/50 bg-primary/10 text-foreground" : "border-border text-muted-foreground hover:bg-muted/50"
                  }`}
                >
                  <M.Icon className="h-4 w-4" />
                  {M.label}
                </button>
              )
            })}
          </div>
        </div>

        <div>
          <label className={label}>{meta.sourceLabel}</label>
          <input className={`${input} font-mono`} value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} placeholder={meta.sourcePlaceholder} />
        </div>

        {isDb && (
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={label}>DB user (optional)</label>
              <input className={input} value={form.db_user} onChange={(e) => setForm({ ...form, db_user: e.target.value })} placeholder="root" />
            </div>
            <div>
              <label className={label}>DB password (optional)</label>
              <input type="password" className={input} value={form.db_password}
                onChange={(e) => setForm({ ...form, db_password: e.target.value })}
                placeholder={initial?.has_db_cred ? "•••••• (stored)" : "leave blank for local auth"} />
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={label}>Destination dir</label>
            <input className={`${input} font-mono`} value={form.dest_dir} onChange={(e) => setForm({ ...form, dest_dir: e.target.value })} />
          </div>
          <div>
            <label className={label}>Keep last (retention)</label>
            <input type="number" min={1} max={365} className={input} value={form.retention}
              onChange={(e) => setForm({ ...form, retention: Math.max(1, Number(e.target.value) || 1) })} />
          </div>
          <div className="sm:col-span-2">
            <label className={label}>Offsite copy</label>
            <select className={input} value={form.destination_id}
              onChange={(e) => setForm({ ...form, destination_id: e.target.value })}>
              <option value="">Keep on this server only</option>
              {destinations.map((d) => (
                <option key={d.id} value={d.id}>Also copy to {d.name} ({d.bucket})</option>
              ))}
            </select>
            {!destinations.length && (
              <p className="mt-1 text-[11px] text-muted-foreground">
                Add offsite storage below to send copies off the server.
              </p>
            )}
            {form.destination_id && (
              <label className="mt-2 flex items-start gap-2 text-xs text-muted-foreground">
                <input type="checkbox" className="mt-0.5" checked={!form.keep_local}
                  onChange={(e) => setForm({ ...form, keep_local: !e.target.checked })} />
                <span>
                  Delete the local copy after a successful upload — saves disk space. The local file is
                  only removed once the upload is confirmed.
                </span>
              </label>
            )}
          </div>
        </div>

        <div>
          <label className={label}>Schedule (optional, natural language)</label>
          <input className={input} value={form.schedule} onChange={(e) => setForm({ ...form, schedule: e.target.value })} placeholder="every night at 2am" />
          {form.schedule.trim() && (
            <p className="mt-1 text-xs text-muted-foreground flex items-center gap-1.5">
              {parsing ? <Loader2 className="h-3 w-3 animate-spin" /> : <CalendarClock className="h-3 w-3" />}
              {parsing ? "Parsing…" : cron ? <>cron: <code className="text-foreground">{cron}</code>{cronDesc ? ` · ${cronDesc}` : ""}</> : "Could not parse — leave blank to run manually only"}
            </p>
          )}
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-sm text-red-400">
            <AlertTriangle className="h-4 w-4 shrink-0" />{error}
          </div>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <button onClick={onClose} className="px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground border border-border rounded-lg hover:bg-muted/50 transition-colors">Cancel</button>
          <button onClick={submit} disabled={!valid || isPending}
            className="flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors">
            {isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {initial ? "Save" : "Create"}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── History panel ──────────────────────────────────────────────────────────

function HistoryPanel({ backupId }: { backupId: string }) {
  const { data: runs = [], isLoading } = useQuery({
    queryKey: ["backup-history", backupId],
    queryFn: () => backupHistory(backupId),
  })
  if (isLoading)
    return <div className="flex items-center gap-2 px-4 py-3 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" />Loading history…</div>
  if (!runs.length)
    return <div className="px-4 py-3 text-xs text-muted-foreground">No runs yet.</div>
  return (
    <div className="divide-y divide-border/40">
      {runs.map((r: BackupRun) => (
        <div key={r.id} className="flex items-center justify-between px-4 py-2 text-xs">
          <span className="flex items-center gap-2">
            <span className={`rounded px-1.5 py-0.5 text-[10px] uppercase ${r.action === "restore" ? "bg-violet-500/10 text-violet-400" : "bg-muted text-muted-foreground"}`}>{r.action}</span>
            <StatusPill status={r.status} />
            {r.offsite_status === "uploaded" && (
              <span className="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] text-emerald-600 dark:text-emerald-400">
                <Cloud className="h-2.5 w-2.5" />offsite
              </span>
            )}
            {(r.offsite_status === "failed" || r.offsite_status === "skipped") && (
              <span className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-600 dark:text-amber-400">
                <Cloud className="h-2.5 w-2.5" />offsite {r.offsite_status}
              </span>
            )}
            <span className="text-muted-foreground">{formatDistanceToNow(new Date(r.started_at), { addSuffix: true })}</span>
          </span>
          <span className="text-muted-foreground font-mono">{fmtBytes(r.size_bytes)}</span>
        </div>
      ))}
    </div>
  )
}

// ── Backup card ──────────────────────────────────────────────────────────────

function BackupCard({
  backup,
  onEdit,
  onRun,
  onRestore,
  onDelete,
  busy,
  lastRunResult,
}: {
  backup: Backup
  onEdit: () => void
  onRun: () => void
  onRestore: () => void
  onDelete: () => void
  busy: "run" | "restore" | null
  lastRunResult?: BackupRun
}) {
  const [showHistory, setShowHistory] = useState(false)
  const M = TYPE_META[backup.backup_type]
  return (
    <div className="rounded-xl border border-border bg-card">
      <div className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2.5 min-w-0">
            <M.Icon className="h-5 w-5 text-primary shrink-0 mt-0.5" />
            <div className="min-w-0">
              <h3 className="text-sm font-medium text-foreground flex items-center gap-2">
                {backup.name}
                <span className="text-[10px] uppercase rounded bg-muted px-1.5 py-0.5 text-muted-foreground">{M.label}</span>
              </h3>
              <p className="text-xs text-muted-foreground font-mono mt-0.5 truncate">{backup.source}</p>
            </div>
          </div>
          <div className="flex items-center gap-0.5 shrink-0">
            <button onClick={onEdit} title="Edit" className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"><Pencil className="h-3.5 w-3.5" /></button>
            <button onClick={onDelete} title="Delete" className="p-1.5 rounded text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"><Trash2 className="h-3.5 w-3.5" /></button>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1"><HardDriveDownload className="h-3 w-3" />keep {backup.retention}</span>
          {backup.human_schedule ? (
            <span className="flex items-center gap-1"><CalendarClock className="h-3 w-3" />{backup.human_schedule}</span>
          ) : (
            <span className="text-muted-foreground/60">manual only</span>
          )}
          <span className="flex items-center gap-1.5">
            <Clock className="h-3 w-3" />
            {backup.last_run ? formatDistanceToNow(new Date(backup.last_run), { addSuffix: true }) : "never run"}
          </span>
          <StatusPill status={backup.last_status} />
        </div>

        {/* Inline run/restore result */}
        {lastRunResult && (
          <div className={`mt-3 rounded-lg border px-3 py-2 text-xs ${
            lastRunResult.status === "success" ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-400" : "border-red-500/20 bg-red-500/5 text-red-400"
          }`}>
            <span className="font-medium capitalize">{lastRunResult.action} {lastRunResult.status}</span>
            {lastRunResult.size_bytes != null && lastRunResult.action === "backup" && ` · ${fmtBytes(lastRunResult.size_bytes)}`}
            {lastRunResult.output && <pre className="mt-1 whitespace-pre-wrap break-words text-foreground/70 max-h-24 overflow-y-auto">{lastRunResult.output}</pre>}
          </div>
        )}

        <div className="mt-3 flex items-center gap-2">
          <button onClick={onRun} disabled={busy !== null}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors">
            {busy === "run" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            {busy === "run" ? "Backing up…" : "Back up now"}
          </button>
          <button onClick={onRestore} disabled={busy !== null || !backup.last_status}
            className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted/50 hover:text-foreground disabled:opacity-40 transition-colors">
            {busy === "restore" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
            Restore latest
          </button>
          <button onClick={() => setShowHistory((v) => !v)}
            className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors ml-auto">
            {showHistory ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
            History
          </button>
        </div>
      </div>

      {showHistory && (
        <div className="border-t border-border bg-background/40 rounded-b-xl">
          <HistoryPanel backupId={backup.id} />
        </div>
      )}
    </div>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function Backups() {
  const { id: serverId } = useParams<{ id: string }>()
  const qc = useQueryClient()

  const [modal, setModal] = useState<{ open: boolean; edit?: Backup }>({ open: false })
  const [confirmDelete, setConfirmDelete] = useState<Backup | null>(null)
  const [confirmRestore, setConfirmRestore] = useState<Backup | null>(null)
  const [busyId, setBusyId] = useState<{ id: string; action: "run" | "restore" } | null>(null)
  const [results, setResults] = useState<Record<string, BackupRun>>({})

  const { data: backups = [], isLoading } = useQuery({
    queryKey: ["backups", serverId],
    queryFn: () => listBackups(serverId!),
    enabled: !!serverId,
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ["backups", serverId] })

  const createMut = useMutation({
    mutationFn: (body: BackupCreateBody) => createBackup(serverId!, body),
    onSuccess: () => { setModal({ open: false }); invalidate() },
  })
  const updateMut = useMutation({
    mutationFn: ({ id, body }: { id: string; body: BackupCreateBody }) => updateBackup(id, body),
    onSuccess: () => { setModal({ open: false }); invalidate() },
  })
  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteBackup(id),
    onSuccess: () => { setConfirmDelete(null); invalidate() },
  })
  const runMut = useMutation({
    mutationFn: (id: string) => runBackup(id),
    onSuccess: (run) => {
      setResults((r) => ({ ...r, [run.backup_id]: run }))
      qc.invalidateQueries({ queryKey: ["backup-history", run.backup_id] })
      invalidate()
    },
    onSettled: () => setBusyId(null),
  })
  const restoreMut = useMutation({
    mutationFn: (id: string) => restoreBackup(id),
    onSuccess: (run) => {
      setResults((r) => ({ ...r, [run.backup_id]: run }))
      qc.invalidateQueries({ queryKey: ["backup-history", run.backup_id] })
    },
    onSettled: () => { setBusyId(null); setConfirmRestore(null) },
  })

  const modalError = useMemo(() => {
    const e = (createMut.error ?? updateMut.error) as Error | null
    return e?.message
  }, [createMut.error, updateMut.error])

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-h1 text-foreground flex items-center gap-2">
            <HardDriveDownload className="h-6 w-6 text-primary" />
            Backups
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Schedule file and database backups with retention, run on demand, and restore.
          </p>
        </div>
        <Button onClick={() => setModal({ open: true })} className="shrink-0">
          <Plus className="h-4 w-4" />New Backup
        </Button>
      </div>

      <DestinationManager />

      {isLoading && (
        <div className="flex items-center gap-2 py-12 text-muted-foreground text-sm">
          <Loader2 className="h-4 w-4 animate-spin" />Loading backups…
        </div>
      )}

      {!isLoading && !backups.length && (
        <EmptyState
          icon={FolderArchive}
          title="No backups configured"
          description="Create a backup job to archive a directory or dump a database — manually or on a schedule."
          action={
            <Button onClick={() => setModal({ open: true })}>
              <Plus className="h-4 w-4" />New Backup
            </Button>
          }
        />
      )}

      <div className="space-y-3">
        {backups.map((b) => (
          <BackupCard
            key={b.id}
            backup={b}
            busy={busyId?.id === b.id ? busyId.action : null}
            lastRunResult={results[b.id]}
            onEdit={() => setModal({ open: true, edit: b })}
            onRun={() => { setBusyId({ id: b.id, action: "run" }); runMut.mutate(b.id) }}
            onRestore={() => setConfirmRestore(b)}
            onDelete={() => setConfirmDelete(b)}
          />
        ))}
      </div>

      {/* New / Edit modal */}
      {modal.open && (
        <BackupModal
          initial={modal.edit}
          isPending={createMut.isPending || updateMut.isPending}
          error={modalError}
          onClose={() => setModal({ open: false })}
          onSubmit={(body) =>
            modal.edit ? updateMut.mutate({ id: modal.edit.id, body }) : createMut.mutate(body)
          }
        />
      )}

      {/* Delete confirm */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded-xl border border-border bg-card p-6 shadow-xl">
            <h3 className="font-semibold text-foreground">Delete "{confirmDelete.name}"?</h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Removes the backup job and its run history. Archive files already on the server are kept.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setConfirmDelete(null)} className="rounded-md px-4 py-2 text-sm text-muted-foreground hover:bg-accent">Cancel</button>
              <button onClick={() => deleteMut.mutate(confirmDelete.id)} disabled={deleteMut.isPending}
                className="flex items-center gap-2 rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50">
                {deleteMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Delete
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Restore confirm (destructive) */}
      {confirmRestore && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-sm rounded-xl border border-orange-500/30 bg-card p-6 shadow-xl">
            <h3 className="font-semibold text-foreground flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-orange-400" />
              Restore "{confirmRestore.name}"?
            </h3>
            <p className="mt-2 text-sm text-muted-foreground">
              This restores the most recent successful backup and <span className="text-foreground font-medium">overwrites current data</span> on the server. This cannot be undone.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setConfirmRestore(null)} className="rounded-md px-4 py-2 text-sm text-muted-foreground hover:bg-accent">Cancel</button>
              <button
                onClick={() => { setBusyId({ id: confirmRestore.id, action: "restore" }); restoreMut.mutate(confirmRestore.id) }}
                disabled={restoreMut.isPending}
                className="flex items-center gap-2 rounded-md bg-orange-500 px-4 py-2 text-sm font-medium text-white hover:bg-orange-600 disabled:opacity-50">
                {restoreMut.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}Restore
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

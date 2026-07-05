import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { X, Loader2, Pencil } from "lucide-react"
import { updateServer, testConnection } from "@/api/servers"
import { ADDABLE_CATEGORIES, categoryForServer } from "@/lib/assetCategories"
import type { Server } from "@/types"

const INPUT =
  "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"

interface Props {
  server: Server
  onClose: () => void
}

/** Edit an existing server's details (name, host, port, username, tags, notes).
 * Changing host/port/username re-checks the connection; the password/key is edited
 * separately via the Credentials modal. */
export default function EditServerModal({ server, onClose }: Props) {
  const qc = useQueryClient()
  const [name, setName] = useState(server.name)
  const [host, setHost] = useState(server.host)
  const [port, setPort] = useState(String(server.port))
  const [tags, setTags] = useState((server.tags ?? []).join(", "))
  const [notes, setNotes] = useState(server.notes ?? "")
  const currentCat = categoryForServer(server)
  const [category, setCategory] = useState(currentCat.id)
  // Re-file only among categories that fit this asset's transport (+ its current one) —
  // category is a label, not a transport, so a Windows tag on an SSH box makes no sense.
  const catOptions = ADDABLE_CATEGORIES.filter(
    (c) => c.connectionType === server.connection_type || c.id === currentCat.id,
  )

  const mutation = useMutation({
    mutationFn: async () => {
      const connChanged = host.trim() !== server.host || Number(port) !== server.port
      await updateServer(server.id, {
        name: name.trim(),
        host: host.trim(),
        port: Number(port) || server.port,
        category,
        tags: tags.split(",").map((t) => t.trim()).filter(Boolean),
        notes: notes.trim() || null,
      })
      // Connection details changed → re-test so the status reflects reality.
      if (connChanged) {
        try {
          await testConnection(server.id)
        } catch {
          /* status stays "unknown" until the next check */
        }
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["server", server.id] })
      qc.invalidateQueries({ queryKey: ["servers"] })
      onClose()
    },
  })

  const canSave = !!(name.trim() && host.trim()) && !mutation.isPending

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-md flex-col rounded-2xl border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-2">
            <Pencil size={16} className="text-primary" />
            <h2 className="font-semibold text-foreground">Edit asset</h2>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4 overflow-y-auto px-6 py-5">
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Name</label>
            <input value={name} onChange={(e) => setName(e.target.value)} className={INPUT} />
          </div>
          {catOptions.length > 1 && (
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Category</label>
              <select value={category} onChange={(e) => setCategory(e.target.value as typeof category)} className={INPUT}>
                {catOptions.map((c) => (
                  <option key={c.id} value={c.id}>{c.label}</option>
                ))}
              </select>
            </div>
          )}
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label className="mb-1 block text-sm font-medium text-foreground">Host</label>
              <input value={host} onChange={(e) => setHost(e.target.value)} className={INPUT} />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-foreground">Port</label>
              <input
                value={port}
                onChange={(e) => setPort(e.target.value.replace(/[^0-9]/g, ""))}
                inputMode="numeric"
                className={INPUT}
              />
            </div>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Tags</label>
            <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="prod, web (comma-separated)" className={INPUT} />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Notes</label>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} className={INPUT} />
          </div>
          <p className="text-xs text-muted-foreground">
            Changing host or port re-checks the connection. To change the username, password or key,
            use <span className="font-medium text-foreground">Credentials</span>.
          </p>
          {mutation.isError && (
            <div className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
              Couldn't save — please try again.
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 border-t border-border px-6 py-4">
          <button
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted/50"
          >
            Cancel
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={!canSave}
            className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {mutation.isPending && <Loader2 size={14} className="animate-spin" />}
            Save changes
          </button>
        </div>
      </div>
    </div>
  )
}

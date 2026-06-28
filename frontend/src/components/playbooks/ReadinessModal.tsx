import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { X, Loader2, CheckCircle2, XCircle, ShieldCheck } from "lucide-react"
import { checkReadiness } from "@/api/playbooks"
import type { Server } from "@/types"

interface Props {
  playbookId: string
  playbookTitle: string
  servers: Server[]
  onClose: () => void
}

/** Pre-install readiness check — probe a server (no changes) and show whether it
 * meets the playbook's requirements as a green/red checklist (Update 19, Tier 2). */
export default function ReadinessModal({ playbookId, playbookTitle, servers, onClose }: Props) {
  const sshServers = servers.filter((s) => s.connection_type === "ssh")
  const [serverId, setServerId] = useState(sshServers[0]?.id ?? "")

  const mutation = useMutation({ mutationFn: () => checkReadiness(playbookId, serverId) })
  const result = mutation.data

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-md flex-col rounded-2xl border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-2">
            <ShieldCheck size={16} className="text-primary" />
            <h2 className="truncate font-semibold text-foreground">Check readiness — {playbookTitle}</h2>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4 overflow-y-auto px-6 py-5">
          <p className="text-sm text-muted-foreground">
            Confirm a server meets this playbook's requirements before installing — nothing on the
            server is changed.
          </p>
          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Server</label>
            <select
              value={serverId}
              onChange={(e) => {
                setServerId(e.target.value)
                mutation.reset()
              }}
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/40"
            >
              {sshServers.length === 0 && <option value="">No Linux servers</option>}
              {sshServers.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} · {s.host}
                </option>
              ))}
            </select>
          </div>

          {result && (
            <div className="space-y-3">
              <div
                className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium ${
                  result.ready
                    ? "border-green-500/30 bg-green-500/10 text-green-600 dark:text-green-400"
                    : "border-red-500/30 bg-red-500/10 text-red-600 dark:text-red-400"
                }`}
              >
                {result.ready ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
                {result.ready ? "Ready to install" : "Not ready — fix the items below first"}
              </div>
              <ul className="space-y-1.5">
                {result.checks.map((c, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm">
                    {c.ok ? (
                      <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-green-500" />
                    ) : (
                      <XCircle size={15} className="mt-0.5 shrink-0 text-red-500" />
                    )}
                    <span className="flex-1">
                      <span className={c.ok ? "text-foreground" : "font-medium text-foreground"}>
                        {c.label}
                      </span>
                      {c.detail && <span className="text-muted-foreground"> — {c.detail}</span>}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {mutation.isError && (
            <div className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
              Couldn't reach the server to check — make sure it's online.
            </div>
          )}
        </div>

        <div className="flex justify-end gap-3 border-t border-border px-6 py-4">
          <button
            onClick={onClose}
            className="rounded-lg border border-border px-4 py-2 text-sm text-muted-foreground hover:bg-muted/50"
          >
            Close
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={!serverId || mutation.isPending}
            className="flex items-center gap-2 rounded-lg bg-primary px-5 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {mutation.isPending && <Loader2 size={14} className="animate-spin" />}
            {result ? "Re-check" : "Check readiness"}
          </button>
        </div>
      </div>
    </div>
  )
}

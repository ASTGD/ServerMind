import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { X, KeyRound, Loader2 } from "lucide-react"
import { updateServer } from "@/api/servers"
import type { Server } from "@/types"

interface Props {
  server: Server
  onClose: () => void
}

/**
 * Update a server's login credentials (password or SSH key) in place. The new
 * secret is encrypted before storage; saving drops the old cached connection and
 * resets status so the change takes effect at once. The password field uses
 * autoComplete="new-password" so the browser can't silently re-fill an old saved
 * password.
 */
export default function UpdateCredentialsModal({ server, onClose }: Props) {
  const qc = useQueryClient()
  const [username, setUsername] = useState(server.username)
  const [authType, setAuthType] = useState<"password" | "key">(
    server.auth_type === "key" ? "key" : "password"
  )
  const [credential, setCredential] = useState("")

  const mutation = useMutation({
    mutationFn: () =>
      updateServer(server.id, { username, auth_type: authType, credential }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["server", server.id] })
      qc.invalidateQueries({ queryKey: ["servers"] })
      onClose()
    },
  })

  const canSave = credential.trim().length > 0 && !mutation.isPending

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-2">
            <KeyRound size={16} className="text-primary" />
            <h2 className="font-semibold text-foreground">Update credentials</h2>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4 px-6 py-5">
          <p className="text-xs text-muted-foreground">
            Changing the password or key takes effect immediately — the old cached
            connection is dropped and the status resets until the next test.
          </p>

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Username</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="off"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">Authentication</label>
            <div className="flex gap-2">
              {(["password", "key"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setAuthType(t)}
                  className={`flex-1 rounded-lg border px-3 py-2 text-sm transition-colors ${
                    authType === t
                      ? "border-primary bg-primary/10 text-foreground"
                      : "border-border text-muted-foreground hover:bg-accent"
                  }`}
                >
                  {t === "key" ? "SSH key" : "Password"}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-foreground">
              {authType === "key" ? "Private key" : "New password"}
            </label>
            {authType === "key" ? (
              <textarea
                value={credential}
                onChange={(e) => setCredential(e.target.value)}
                rows={5}
                placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
                autoComplete="off"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 font-mono text-xs"
              />
            ) : (
              <input
                type="password"
                value={credential}
                onChange={(e) => setCredential(e.target.value)}
                placeholder="Enter the new password"
                autoComplete="new-password"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm"
              />
            )}
            <p className="mt-1 text-xs text-muted-foreground">
              Encrypted (AES-256-GCM) before storage — never saved in plain text.
            </p>
          </div>

          {mutation.isError && (
            <div className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
              Couldn't update — please try again.
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
            Save &amp; reconnect
          </button>
        </div>
      </div>
    </div>
  )
}

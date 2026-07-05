import { useMemo, useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { X, Sparkles, ServerIcon, AlertCircle } from "lucide-react"
import type { Recipe } from "@/api/recipes"
import { composeRecipeMessage, missingRequired } from "@/api/recipes"
import { listServers } from "@/api/servers"
import { useAssistantStore } from "@/store/assistantStore"

/** Turn a variable name into a human label ("domain" → "Domain", "admin_email" → "Admin email"). */
function label(name: string): string {
  const s = name.replace(/[_-]+/g, " ").trim()
  return s.charAt(0).toUpperCase() + s.slice(1)
}

/**
 * The Recipe "smart form": collect a few variables + pick a target server, then compose
 * the goal_template into a sentence and send it into Ally exactly like the user typed it
 * (`openServer(server, message)` — the same seed path "Respond with Ally" uses). No new
 * execution path: this just writes a good chat message for you.
 */
export default function RunRecipeModal({ recipe, onClose }: { recipe: Recipe; onClose: () => void }) {
  const { data: servers = [] } = useQuery({ queryKey: ["servers"], queryFn: listServers })
  const openServer = useAssistantStore((s) => s.openServer)
  const [values, setValues] = useState<Record<string, string>>({})
  const [serverId, setServerId] = useState<string>("")

  // Missions need a shell — a Windows recipe wants WinRM, everything else wants SSH
  // (a CyberPanel box is connection_type='ssh' with a panel, so it qualifies). The
  // transport IS the OS-family gate (ssh = Linux/Unix, winrm = Windows); API-only
  // hosting connections can't run mission steps and are excluded.
  const wantWinrm = recipe.os_family === "windows"
  const eligible = useMemo(
    () => servers.filter((s) => s.connection_type === (wantWinrm ? "winrm" : "ssh")),
    [servers, wantWinrm],
  )
  const target = eligible.find((s) => s.id === serverId) ?? eligible[0]

  const missing = missingRequired(recipe, values)
  const canRun = Boolean(target) && missing.length === 0

  /** Live placeholder for an optional field: its default with {{refs}} filled from what's typed so far. */
  function placeholderFor(def: string): string {
    if (!def) return "Optional"
    return def.replace(/\{\{(\w+)\}\}/g, (_m, k: string) => (values[k] ?? "").trim() || `{{${k}}}`)
  }

  function run() {
    if (!target) return
    const message = composeRecipeMessage(recipe, values)
    openServer(target, message) // seeds + auto-sends → mission offer appears in the drawer
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="w-full max-w-md overflow-hidden rounded-2xl border border-border bg-card shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between border-b border-border p-5">
          <div className="flex items-start gap-3">
            <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Sparkles size={18} />
            </div>
            <div>
              <h2 className="text-base font-semibold text-foreground">{recipe.title}</h2>
              <p className="mt-0.5 text-xs text-muted-foreground">{recipe.summary}</p>
            </div>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4 p-5">
          {/* Target server */}
          <div>
            <label className="mb-1 block text-xs font-medium text-foreground">Run on</label>
            {eligible.length === 0 ? (
              <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-400">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <span>
                  No compatible {wantWinrm ? "Windows" : "Linux"} server yet. Add one with{" "}
                  {wantWinrm ? "WinRM" : "SSH"} access to run this recipe.
                </span>
              </div>
            ) : (
              <div className="relative">
                <ServerIcon size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <select
                  value={target?.id ?? ""}
                  onChange={(e) => setServerId(e.target.value)}
                  className="w-full rounded-lg border border-border bg-background py-2 pl-9 pr-3 text-sm text-foreground focus:border-primary focus:outline-none"
                >
                  {eligible.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.host})
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>

          {/* Variables */}
          {recipe.variables.map((v) => (
            <div key={v.name}>
              <label className="mb-1 block text-xs font-medium text-foreground">
                {label(v.name)}
                {v.required && <span className="ml-0.5 text-red-500">*</span>}
              </label>
              <input
                value={values[v.name] ?? ""}
                onChange={(e) => setValues((prev) => ({ ...prev, [v.name]: e.target.value }))}
                placeholder={placeholderFor(v.default)}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
              />
            </div>
          ))}

          <p className="text-[11px] text-muted-foreground">
            Ally will plan this as a guided mission and ask for your OK before any risky step.
          </p>
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border p-4">
          <button
            onClick={onClose}
            className="rounded-lg px-3 py-2 text-sm font-medium text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
          <button
            onClick={run}
            disabled={!canRun}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
          >
            <Sparkles size={14} /> Set up with Ally
          </button>
        </div>
      </div>
    </div>
  )
}

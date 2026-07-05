import { useEffect, useMemo, useState } from "react"
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

/** Variables that name ANOTHER server (e.g. migrate's `source`) — rendered as a server
 * picker instead of a free-text box, so the value is always a real server name. */
const SERVER_REF = new Set(["source", "from", "source_server", "from_server", "origin"])

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

  // A server-ref variable (migrate's `source`) picks a DIFFERENT server than the target.
  const hasServerRef = recipe.variables.some((v) => SERVER_REF.has(v.name))
  const otherServers = useMemo(
    () => eligible.filter((s) => s.name !== target?.name),
    [eligible, target?.name],
  )
  // Seed server-ref vars with a sensible default so the required-check + compose have a
  // value before the user opens the dropdown (and re-seed if it collides with the target).
  useEffect(() => {
    const first = otherServers[0]?.name
    if (!first) return
    setValues((prev) => {
      let changed = false
      const next = { ...prev }
      for (const v of recipe.variables) {
        if (SERVER_REF.has(v.name) && (!next[v.name] || next[v.name] === target?.name)) {
          next[v.name] = first
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [otherServers, target?.name, recipe.variables])

  const missing = missingRequired(recipe, values)
  // A migrate-style recipe needs a second server to move FROM.
  const needsSecondServer = hasServerRef && otherServers.length === 0
  const canRun = Boolean(target) && missing.length === 0 && !needsSecondServer

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
                {SERVER_REF.has(v.name) ? `${label(v.name)} server` : label(v.name)}
                {v.required && <span className="ml-0.5 text-red-500">*</span>}
              </label>
              {SERVER_REF.has(v.name) ? (
                needsSecondServer ? (
                  <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-400">
                    <AlertCircle size={14} className="mt-0.5 shrink-0" />
                    <span>You need a second server to migrate from. Add one, then try again.</span>
                  </div>
                ) : (
                  <div className="relative">
                    <ServerIcon size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                    <select
                      value={values[v.name] ?? ""}
                      onChange={(e) => setValues((prev) => ({ ...prev, [v.name]: e.target.value }))}
                      className="w-full rounded-lg border border-border bg-background py-2 pl-9 pr-3 text-sm text-foreground focus:border-primary focus:outline-none"
                    >
                      {otherServers.map((s) => (
                        <option key={s.id} value={s.name}>
                          {s.name} ({s.host})
                        </option>
                      ))}
                    </select>
                  </div>
                )
              ) : (
                <input
                  value={values[v.name] ?? ""}
                  onChange={(e) => setValues((prev) => ({ ...prev, [v.name]: e.target.value }))}
                  placeholder={placeholderFor(v.default)}
                  className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
                />
              )}
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

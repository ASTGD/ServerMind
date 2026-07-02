import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { FileCode, Save, Check, Pencil, Loader2, AlertTriangle, ExternalLink } from "lucide-react"
import { createScript } from "@/api/scripts"
import type { GenerateScriptResult } from "@/types"

/**
 * A script Ally generated, shown inside a chat answer. Actions let the user save it to
 * My Scripts or open it in the full editor. The script is text only — it is never executed
 * from here; running a saved script later goes through the normal (safety-checked) run flow.
 */
export default function ScriptCard({ script }: { script: GenerateScriptResult }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [savedId, setSavedId] = useState<string | null>(script.saved_id ?? null)

  const saveMutation = useMutation({
    mutationFn: () =>
      createScript({
        title: script.title,
        description: script.description,
        script_type: script.script_type,
        script_content: script.script,
        variables: script.variables,
        tags: ["ai-generated"],
      }),
    onSuccess: (saved) => {
      setSavedId(saved.id)
      qc.invalidateQueries({ queryKey: ["scripts"] })
    },
  })

  const isBash = script.script_type !== "powershell"

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <FileCode size={15} className="shrink-0 text-primary" />
        <span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{script.title}</span>
        <span
          className={`shrink-0 rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
            isBash
              ? "border-green-500/20 bg-green-500/10 text-green-500"
              : "border-blue-500/20 bg-blue-500/10 text-blue-500"
          }`}
        >
          {script.script_type}
        </span>
      </div>

      {/* Code preview */}
      <pre className="max-h-52 overflow-auto bg-[#0d0d0d] p-3 font-mono text-[11px] leading-relaxed text-zinc-200">
        {script.script}
      </pre>

      {/* Warnings */}
      {script.warnings && script.warnings.length > 0 && (
        <div className="flex items-start gap-1.5 border-t border-border bg-amber-500/5 px-3 py-2 text-xs text-amber-600 dark:text-amber-400">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          <span>{script.warnings.join(" ")}</span>
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-2 border-t border-border px-3 py-2">
        {savedId ? (
          <>
            <span className="flex items-center gap-1.5 rounded-lg bg-green-500/10 px-3 py-1.5 text-xs font-medium text-green-600 dark:text-green-400">
              <Check size={13} />
              Saved
            </span>
            <button
              onClick={() => navigate("/scripts")}
              className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
            >
              View in My Scripts
              <ExternalLink size={12} />
            </button>
          </>
        ) : (
          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
          >
            {saveMutation.isPending ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            Save to My Scripts
          </button>
        )}
        <button
          onClick={() => navigate("/scripts/generate", { state: { prefill: script } })}
          className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent"
        >
          <Pencil size={12} />
          Open in editor
        </button>
      </div>

      {saveMutation.isError && (
        <p className="px-3 pb-2 text-xs text-destructive">Couldn't save — please try again.</p>
      )}
    </div>
  )
}

import { useState, useCallback } from "react"
import { useNavigate, useLocation } from "react-router-dom"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import Editor from "@monaco-editor/react"
import {
  Sparkles,
  Terminal,
  Monitor,
  Layers,
  AlertTriangle,
  CheckCircle2,
  Save,
  RotateCcw,
  Loader2,
  ChevronRight,
  Clock,
} from "lucide-react"
import { generateScript, createScript } from "@/api/scripts"
import type { GenerateScriptResult } from "@/types"

type OsFamily = "linux" | "windows" | "both"

const OS_OPTIONS: { value: OsFamily; label: string; icon: React.ReactNode; desc: string }[] = [
  { value: "linux", label: "Linux / Unix", icon: <Terminal className="h-4 w-4" />, desc: "Bash script for Ubuntu, Debian, CentOS, etc." },
  { value: "windows", label: "Windows Server", icon: <Monitor className="h-4 w-4" />, desc: "PowerShell script for Windows Server" },
  { value: "both", label: "Cross-platform", icon: <Layers className="h-4 w-4" />, desc: "Works on both Linux and Windows" },
]

const EXAMPLES = [
  "Set up automatic daily MySQL backups to /var/backups",
  "Monitor disk usage and send email alert when above 85%",
  "Install and configure Nginx with SSL redirect",
  "Create a new sudo user and set up SSH key authentication",
  "Find and remove log files older than 30 days",
  "Set up a cron job to restart a service if it's down",
]

function fmtRuntime(sec: number): string {
  if (sec < 60) return `~${sec}s`
  return `~${Math.round(sec / 60)}m`
}

export default function ScriptGenerator() {
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  // "Open in editor" from an Ally chat script card hands the generated script over here.
  const prefill = (location.state as { prefill?: GenerateScriptResult } | null)?.prefill ?? null
  const [osFamily, setOsFamily] = useState<OsFamily>(prefill?.script_type === "powershell" ? "windows" : "linux")
  const [request, setRequest] = useState("")
  const [result, setResult] = useState<GenerateScriptResult | null>(prefill)
  const [editedScript, setEditedScript] = useState<string>(prefill?.script ?? "")
  const [savedId, setSavedId] = useState<string | null>(null)

  const generateMutation = useMutation({
    mutationFn: () => generateScript({ request, os_family: osFamily }),
    onSuccess: (data) => {
      setResult(data)
      setEditedScript(data.script)
      setSavedId(data.saved_id)
    },
  })

  const saveMutation = useMutation({
    mutationFn: () =>
      createScript({
        title: result!.title,
        description: result!.description,
        script_type: result!.script_type,
        script_content: editedScript,
        variables: result!.variables,
        tags: ["ai-generated"],
      }),
    onSuccess: (saved) => {
      setSavedId(saved.id)
      queryClient.invalidateQueries({ queryKey: ["scripts"] })
    },
  })

  const handleGenerate = useCallback(() => {
    if (!request.trim()) return
    setResult(null)
    setSavedId(null)
    generateMutation.mutate()
  }, [request, generateMutation])

  const handleReset = useCallback(() => {
    setResult(null)
    setEditedScript("")
    setSavedId(null)
    generateMutation.reset()
  }, [generateMutation])

  const lang = result?.script_type === "powershell" ? "powershell" : "shell"

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-h1 text-foreground flex items-center gap-2">
          <Sparkles className="h-6 w-6 text-primary" />
          Ally Script Generator
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Describe what you need in plain English — Ally writes the script
        </p>
      </div>

      {/* Input panel */}
      <div className="rounded-xl border border-border bg-card p-6 space-y-5">
        {/* OS selector */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-3">Target OS</label>
          <div className="grid grid-cols-3 gap-3">
            {OS_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setOsFamily(opt.value)}
                className={`flex flex-col items-start p-3 rounded-lg border transition-all text-left ${
                  osFamily === opt.value
                    ? "border-primary/60 bg-primary/5 text-foreground"
                    : "border-border text-muted-foreground hover:border-border/80 hover:text-foreground"
                }`}
              >
                <div className={`mb-1.5 ${osFamily === opt.value ? "text-primary" : ""}`}>
                  {opt.icon}
                </div>
                <span className="text-sm font-medium">{opt.label}</span>
                <span className="text-xs text-muted-foreground mt-0.5 leading-tight">{opt.desc}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Request input */}
        <div>
          <label className="block text-sm font-medium text-foreground mb-1.5">
            Describe what the script should do
          </label>
          <textarea
            value={request}
            onChange={(e) => setRequest(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleGenerate()
            }}
            placeholder="e.g. Set up automatic daily MySQL backups to /var/backups with retention for 7 days"
            rows={3}
            className="w-full rounded-lg border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground/50 px-3 py-2.5 focus:outline-none focus:ring-2 focus:ring-primary/40 resize-none"
          />
          <p className="text-xs text-muted-foreground mt-1.5">
            Press ⌘↵ to generate • Be specific for better results
          </p>
        </div>

        {/* Examples */}
        <div>
          <p className="text-xs text-muted-foreground mb-2">Examples:</p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                onClick={() => setRequest(ex)}
                className="text-xs px-2.5 py-1 rounded-full border border-border text-muted-foreground hover:border-primary/30 hover:text-foreground transition-colors"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>

        {/* Generate button */}
        <div className="flex items-center gap-3 pt-1">
          <button
            onClick={handleGenerate}
            disabled={!request.trim() || generateMutation.isPending}
            className="flex items-center gap-2 px-5 py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors disabled:opacity-50"
          >
            {generateMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating…
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                Generate Script
              </>
            )}
          </button>
          {result && (
            <button
              onClick={handleReset}
              className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <RotateCcw className="h-3.5 w-3.5" />
              Start over
            </button>
          )}
        </div>

        {/* Error — surface the API's friendly detail (e.g. the quota wall) when present */}
        {generateMutation.isError && (
          <div className="flex items-center gap-2 rounded-lg border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-400">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {(generateMutation.error as { response?: { data?: { detail?: string } } })?.response
              ?.data?.detail ?? (generateMutation.error as Error).message}
          </div>
        )}
      </div>

      {/* Result panel */}
      {result && (
        <div className="space-y-5">
          {/* Title + meta */}
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs px-2 py-0.5 rounded border border-border bg-muted text-muted-foreground uppercase tracking-wider font-medium">
                  {result.script_type}
                </span>
                <span className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Clock className="h-3 w-3" />
                  {fmtRuntime(result.estimated_runtime_seconds)}
                </span>
              </div>
              <h2 className="text-lg font-semibold text-foreground">{result.title}</h2>
              {result.description && (
                <p className="text-sm text-muted-foreground mt-0.5">{result.description}</p>
              )}
            </div>

            <div className="flex items-center gap-2 shrink-0">
              {savedId ? (
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-1.5 text-sm text-green-400">
                    <CheckCircle2 className="h-4 w-4" />
                    Saved
                  </span>
                  <button
                    onClick={() => navigate("/scripts")}
                    className="flex items-center gap-1 text-sm text-primary hover:underline"
                  >
                    My Scripts <ChevronRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => saveMutation.mutate()}
                  disabled={saveMutation.isPending}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg border border-border text-sm hover:bg-muted/50 transition-colors disabled:opacity-50"
                >
                  {saveMutation.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Save className="h-3.5 w-3.5" />
                  )}
                  Save to My Scripts
                </button>
              )}
            </div>
          </div>

          {/* Warnings */}
          {result.warnings.length > 0 && (
            <div className="rounded-lg border border-yellow-500/20 bg-yellow-500/10 px-4 py-3 space-y-1">
              {result.warnings.map((w, i) => (
                <div key={i} className="flex items-start gap-2 text-sm text-yellow-400">
                  <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
                  {w}
                </div>
              ))}
            </div>
          )}

          {/* Variables */}
          {result.variables.length > 0 && (
            <div>
              <p className="text-sm font-medium text-foreground mb-2">Variables</p>
              <div className="rounded-xl border border-border overflow-hidden">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-muted/40">
                      <th className="text-left px-4 py-2 text-xs font-medium text-muted-foreground">Name</th>
                      <th className="text-left px-4 py-2 text-xs font-medium text-muted-foreground">Label</th>
                      <th className="text-left px-4 py-2 text-xs font-medium text-muted-foreground">Default</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.variables.map((v) => (
                      <tr key={v.name} className="border-b border-border last:border-0">
                        <td className="px-4 py-2 font-mono text-xs text-primary">{v.name}</td>
                        <td className="px-4 py-2 text-muted-foreground">{v.label}</td>
                        <td className="px-4 py-2 font-mono text-xs text-muted-foreground">{v.default || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Monaco editor */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-sm font-medium text-foreground">Generated Script</p>
              <p className="text-xs text-muted-foreground">You can edit before saving</p>
            </div>
            <div className="rounded-xl border border-border overflow-hidden">
              <Editor
                height="420px"
                language={lang}
                value={editedScript}
                onChange={(v) => setEditedScript(v ?? "")}
                theme="vs-dark"
                options={{
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  fontSize: 13,
                  lineNumbers: "on",
                  folding: true,
                  wordWrap: "off",
                  padding: { top: 12, bottom: 12 },
                  scrollbar: { alwaysConsumeMouseWheel: false },
                }}
              />
            </div>
          </div>

          {/* Post-run instructions */}
          {result.post_run_instructions && (
            <div className="rounded-lg border border-border bg-muted/30 px-4 py-3">
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-1">
                After running
              </p>
              <p className="text-sm text-foreground">{result.post_run_instructions}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

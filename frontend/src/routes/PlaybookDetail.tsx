import { useState } from "react"
import { useParams, useNavigate } from "react-router-dom"
import { useQuery } from "@tanstack/react-query"
import {
  ArrowLeft,
  Play,
  Clock,
  BarChart2,
  Tag,
  Terminal,
  Monitor,
  Loader2,
  AlertCircle,
  ShieldCheck,
} from "lucide-react"
import { getPlaybook } from "@/api/playbooks"
import { listServers } from "@/api/servers"
import ScriptPreview from "@/components/playbooks/ScriptPreview"
import RunPlaybookModal from "@/components/playbooks/RunPlaybookModal"
import ReadinessModal from "@/components/playbooks/ReadinessModal"

const CATEGORY_LABELS: Record<string, string> = {
  setup: "Setup",
  security: "Security",
  backup: "Backup",
  deployment: "Deployment",
  monitoring: "Monitoring",
  maintenance: "Maintenance",
}

function fmtRuntime(sec: number | null): string {
  if (!sec) return "—"
  if (sec < 60) return `~${sec} sec`
  return `~${Math.round(sec / 60)} min`
}

export default function PlaybookDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [showRunModal, setShowRunModal] = useState(false)
  const [showReadiness, setShowReadiness] = useState(false)

  const { data: playbook, isLoading, isError } = useQuery({
    queryKey: ["playbook", id],
    queryFn: () => getPlaybook(id!),
    enabled: !!id,
  })

  const { data: servers = [] } = useQuery({
    queryKey: ["servers"],
    queryFn: listServers,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-32 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin mr-2" />
        Loading playbook...
      </div>
    )
  }

  if (isError || !playbook) {
    return (
      <div className="flex flex-col items-center justify-center py-32 text-center">
        <AlertCircle className="h-10 w-10 text-muted-foreground/40 mb-3" />
        <p className="text-muted-foreground font-medium">Playbook not found</p>
        <button
          onClick={() => navigate("/playbooks")}
          className="mt-4 text-sm text-primary hover:underline"
        >
          Back to playbooks
        </button>
      </div>
    )
  }

  const compatible = servers.filter((s) => {
    if (!playbook.os_family || playbook.os_family === "both") return true
    if (playbook.os_family === "linux") return s.connection_type !== "winrm"
    if (playbook.os_family === "windows") return s.connection_type === "winrm"
    return true
  })

  return (
    <>
      <div className="space-y-6 max-w-4xl">
        {/* Back */}
        <button
          onClick={() => navigate("/playbooks")}
          className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Playbooks
        </button>

        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2 mb-2">
              {playbook.is_official && (
                <span className="text-xs font-semibold uppercase tracking-wider px-2 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">
                  Official
                </span>
              )}
              {playbook.category && (
                <span className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground border border-border">
                  {CATEGORY_LABELS[playbook.category] ?? playbook.category}
                </span>
              )}
              {playbook.os_family && (
                <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground border border-border">
                  {playbook.os_family === "windows" ? (
                    <Monitor className="h-3 w-3" />
                  ) : (
                    <Terminal className="h-3 w-3" />
                  )}
                  {playbook.os_family === "both"
                    ? "Linux + Windows"
                    : playbook.os_family.charAt(0).toUpperCase() + playbook.os_family.slice(1)}
                </span>
              )}
            </div>
            <h1 className="text-2xl font-semibold text-foreground">{playbook.title}</h1>
            {playbook.description && (
              <p className="text-muted-foreground mt-2 leading-relaxed">{playbook.description}</p>
            )}
          </div>

          <div className="flex shrink-0 items-center gap-2">
            {(playbook.category === "control-panel" ||
              (playbook.supported_os && playbook.supported_os.length > 0)) && (
              <button
                onClick={() => setShowReadiness(true)}
                disabled={compatible.length === 0}
                className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium border border-border text-foreground hover:bg-accent transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ShieldCheck className="h-4 w-4" />
                Check readiness
              </button>
            )}
            <button
              onClick={() => setShowRunModal(true)}
              disabled={compatible.length === 0}
              className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <Play className="h-4 w-4" />
              Run Playbook
            </button>
          </div>
        </div>

        {compatible.length === 0 && servers.length > 0 && (
          <div className="flex items-center gap-2 rounded-lg border border-yellow-500/20 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-400">
            <AlertCircle className="h-4 w-4" />
            No compatible servers — add a{" "}
            {playbook.os_family === "windows" ? "Windows (WinRM)" : "Linux (SSH)"} server first
          </div>
        )}

        {/* Stats row */}
        <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <Clock className="h-4 w-4" />
            {fmtRuntime(playbook.est_runtime_sec)}
          </span>
          <span className="flex items-center gap-1.5">
            <BarChart2 className="h-4 w-4" />
            {playbook.run_count.toLocaleString()} runs
          </span>
          <span className="text-xs text-muted-foreground/60">v{playbook.version}</span>
        </div>

        {/* Tags */}
        {playbook.tags && playbook.tags.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <Tag className="h-3.5 w-3.5 text-muted-foreground" />
            {playbook.tags.map((tag) => (
              <span
                key={tag}
                className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground border border-border"
              >
                {tag}
              </span>
            ))}
          </div>
        )}

        {/* Variables */}
        {(playbook.variables ?? []).length > 0 && (
          <div>
            <h2 className="text-sm font-semibold text-foreground mb-3">Variables</h2>
            <div className="rounded-xl border border-border overflow-hidden">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/40">
                    <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Name</th>
                    <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Label</th>
                    <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Default</th>
                    <th className="text-left px-4 py-2.5 font-medium text-muted-foreground">Required</th>
                  </tr>
                </thead>
                <tbody>
                  {(playbook.variables ?? []).map((v) => (
                    <tr key={v.name} className="border-b border-border last:border-0">
                      <td className="px-4 py-2.5 font-mono text-xs text-primary">{v.name}</td>
                      <td className="px-4 py-2.5 text-foreground">{v.label}</td>
                      <td className="px-4 py-2.5 text-muted-foreground font-mono text-xs">
                        {v.default || "—"}
                      </td>
                      <td className="px-4 py-2.5">
                        <span
                          className={`text-xs px-1.5 py-0.5 rounded ${
                            v.required
                              ? "bg-red-500/10 text-red-400"
                              : "bg-muted text-muted-foreground"
                          }`}
                        >
                          {v.required ? "required" : "optional"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Script preview */}
        <div>
          <h2 className="text-sm font-semibold text-foreground mb-3">Script</h2>
          <ScriptPreview
            scriptBash={playbook.script_bash}
            scriptPowershell={playbook.script_powershell}
            defaultTab={playbook.os_family === "windows" ? "powershell" : "bash"}
          />
        </div>
      </div>

      {showRunModal && (
        <RunPlaybookModal
          playbook={playbook}
          servers={compatible.length > 0 ? compatible : servers}
          onClose={() => setShowRunModal(false)}
        />
      )}

      {showReadiness && (
        <ReadinessModal
          playbookId={playbook.id}
          playbookTitle={playbook.title}
          servers={compatible.length > 0 ? compatible : servers}
          onClose={() => setShowReadiness(false)}
        />
      )}
    </>
  )
}

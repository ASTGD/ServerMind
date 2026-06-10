import { useState } from "react"
import { useNavigate } from "react-router-dom"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import Editor from "@monaco-editor/react"
import {
  FileCode,
  Sparkles,
  Search,
  Terminal,
  Monitor,
  Trash2,
  Play,
  X,
  Loader2,
  Calendar,
  ChevronRight,
} from "lucide-react"
import { listScripts, deleteScript } from "@/api/scripts"
import { listServers } from "@/api/servers"
import RunPlaybookModal from "@/components/playbooks/RunPlaybookModal"
import type { UserScript, PlaybookDetail } from "@/types"
import { format } from "date-fns"

type FilterType = "all" | "bash" | "powershell"

function ScriptCard({
  script,
  onSelect,
  onDelete,
}: {
  script: UserScript
  onSelect: (s: UserScript) => void
  onDelete: (id: string) => void
}) {
  const isBash = script.script_type === "bash"
  return (
    <div className="group rounded-xl border border-border bg-card hover:border-primary/30 transition-all p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border ${
                isBash
                  ? "bg-green-500/10 text-green-400 border-green-500/20"
                  : "bg-blue-500/10 text-blue-400 border-blue-500/20"
              }`}
            >
              {script.script_type ?? "script"}
            </span>
            {script.source === "ai_generated" && (
              <span className="text-[10px] px-1.5 py-0.5 rounded border bg-primary/10 text-primary border-primary/20 flex items-center gap-0.5">
                <Sparkles className="h-2.5 w-2.5" />
                AI
              </span>
            )}
          </div>
          <h3 className="font-medium text-sm text-foreground leading-snug line-clamp-1">{script.title}</h3>
          {script.description && (
            <p className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{script.description}</p>
          )}
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
          <button
            onClick={(e) => { e.stopPropagation(); onDelete(script.id) }}
            className="p-1.5 rounded text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Tags */}
      {script.tags && script.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {script.tags.slice(0, 4).map((tag) => (
            <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
              {tag}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center justify-between text-xs text-muted-foreground mt-auto pt-2 border-t border-border">
        <span className="flex items-center gap-1">
          <Calendar className="h-3 w-3" />
          {format(new Date(script.created_at), "MMM d, yyyy")}
        </span>
        <button
          onClick={() => onSelect(script)}
          className="flex items-center gap-1 text-primary hover:underline font-medium"
        >
          View <ChevronRight className="h-3 w-3" />
        </button>
      </div>
    </div>
  )
}

export default function MyScripts() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState<FilterType>("all")
  const [search, setSearch] = useState("")
  const [selected, setSelected] = useState<UserScript | null>(null)
  const [showRunModal, setShowRunModal] = useState(false)

  const { data: scripts = [], isLoading } = useQuery({
    queryKey: ["scripts"],
    queryFn: listScripts,
  })

  const { data: servers = [] } = useQuery({
    queryKey: ["servers"],
    queryFn: listServers,
  })

  const deleteMutation = useMutation({
    mutationFn: deleteScript,
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ["scripts"] })
      if (selected?.id === id) setSelected(null)
    },
  })

  const filtered = scripts.filter((s) => {
    if (filter !== "all" && s.script_type !== filter) return false
    if (search) {
      const q = search.toLowerCase()
      return (
        s.title.toLowerCase().includes(q) ||
        s.description?.toLowerCase().includes(q) ||
        s.tags?.some((t) => t.toLowerCase().includes(q))
      )
    }
    return true
  })

  // Build a PlaybookDetail-like object to pass to RunPlaybookModal
  const scriptAsPlaybook: PlaybookDetail | null = selected
    ? {
        id: selected.id,
        slug: selected.id,
        title: selected.title,
        description: selected.description,
        category: null,
        os_family: selected.script_type === "powershell" ? "windows" : "linux",
        script_type: selected.script_type as "bash" | "powershell" | null,
        variables: [],
        supported_os: null,
        est_runtime_sec: null,
        is_official: false,
        run_count: 0,
        rating: null,
        tags: selected.tags,
        version: "1.0.0",
        created_at: selected.created_at,
        script_bash: selected.script_type !== "powershell" ? selected.script_content : null,
        script_powershell: selected.script_type === "powershell" ? selected.script_content : null,
      }
    : null

  const lang = selected?.script_type === "powershell" ? "powershell" : "shell"

  return (
    <>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-foreground">My Scripts</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Your saved and AI-generated scripts
            </p>
          </div>
          <button
            onClick={() => navigate("/scripts/generate")}
            className="flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
          >
            <Sparkles className="h-4 w-4" />
            Generate with AI
          </button>
        </div>

        {/* Filters */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
          <div className="flex rounded-lg border border-border overflow-hidden">
            {(["all", "bash", "powershell"] as FilterType[]).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors ${
                  filter === f
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:text-foreground hover:bg-muted/50"
                }`}
              >
                {f === "bash" && <Terminal className="h-3.5 w-3.5" />}
                {f === "powershell" && <Monitor className="h-3.5 w-3.5" />}
                {f === "all" ? "All" : f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search scripts..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-4 py-2 rounded-lg border border-border bg-background text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/40"
            />
          </div>
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-24 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin mr-2" />
            Loading scripts...
          </div>
        )}

        {/* Empty state */}
        {!isLoading && scripts.length === 0 && (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <FileCode className="h-10 w-10 text-muted-foreground/40 mb-3" />
            <p className="font-medium text-muted-foreground">No scripts yet</p>
            <p className="text-sm text-muted-foreground/60 mt-1">
              Use AI to generate your first script
            </p>
            <button
              onClick={() => navigate("/scripts/generate")}
              className="mt-4 flex items-center gap-2 px-4 py-2 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:bg-primary/90 transition-colors"
            >
              <Sparkles className="h-4 w-4" />
              Generate with AI
            </button>
          </div>
        )}

        {/* Grid + Detail split view */}
        {!isLoading && scripts.length > 0 && (
          <div className={`flex gap-6 ${selected ? "items-start" : ""}`}>
            {/* Script list */}
            <div className={`${selected ? "w-80 shrink-0" : "w-full"}`}>
              {filtered.length === 0 ? (
                <p className="text-center py-12 text-muted-foreground text-sm">No matching scripts</p>
              ) : (
                <div className={`grid gap-4 ${selected ? "grid-cols-1" : "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"}`}>
                  {filtered.map((s) => (
                    <ScriptCard
                      key={s.id}
                      script={s}
                      onSelect={setSelected}
                      onDelete={(id) => deleteMutation.mutate(id)}
                    />
                  ))}
                </div>
              )}
            </div>

            {/* Detail panel */}
            {selected && (
              <div className="flex-1 min-w-0 rounded-xl border border-border bg-card p-5 space-y-4">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className={`text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border ${
                        selected.script_type === "bash"
                          ? "bg-green-500/10 text-green-400 border-green-500/20"
                          : "bg-blue-500/10 text-blue-400 border-blue-500/20"
                      }`}>
                        {selected.script_type ?? "script"}
                      </span>
                    </div>
                    <h2 className="font-semibold text-foreground">{selected.title}</h2>
                    {selected.description && (
                      <p className="text-xs text-muted-foreground mt-1">{selected.description}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      onClick={() => setShowRunModal(true)}
                      disabled={servers.length === 0}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-40"
                    >
                      <Play className="h-3.5 w-3.5" />
                      Run
                    </button>
                    <button
                      onClick={() => setSelected(null)}
                      className="text-muted-foreground hover:text-foreground transition-colors"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                <div className="rounded-xl border border-border overflow-hidden">
                  <Editor
                    height="360px"
                    language={lang}
                    value={selected.script_content}
                    theme="vs-dark"
                    options={{
                      readOnly: true,
                      minimap: { enabled: false },
                      scrollBeyondLastLine: false,
                      fontSize: 13,
                      lineNumbers: "on",
                      padding: { top: 12, bottom: 12 },
                      scrollbar: { alwaysConsumeMouseWheel: false },
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {showRunModal && scriptAsPlaybook && (
        <RunPlaybookModal
          playbook={scriptAsPlaybook}
          servers={servers}
          onClose={() => setShowRunModal(false)}
          isUserScript
        />
      )}
    </>
  )
}

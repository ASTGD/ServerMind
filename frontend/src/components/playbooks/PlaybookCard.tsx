import { useNavigate } from "react-router-dom"
import { Clock, Play, Terminal, Monitor } from "lucide-react"
import type { Playbook } from "@/types"

const CATEGORY_COLORS: Record<string, string> = {
  setup: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  security: "bg-red-500/10 text-red-400 border-red-500/20",
  backup: "bg-yellow-500/10 text-yellow-400 border-yellow-500/20",
  deployment: "bg-purple-500/10 text-purple-400 border-purple-500/20",
  monitoring: "bg-green-500/10 text-green-400 border-green-500/20",
  maintenance: "bg-gray-500/10 text-gray-400 border-gray-500/20",
}

function fmtRuntime(sec: number | null): string {
  if (!sec) return ""
  if (sec < 60) return `${sec}s`
  return `${Math.round(sec / 60)}m`
}

interface Props {
  playbook: Playbook
}

export default function PlaybookCard({ playbook }: Props) {
  const navigate = useNavigate()
  const categoryStyle =
    CATEGORY_COLORS[playbook.category ?? ""] ??
    "bg-muted text-muted-foreground border-border"

  return (
    <button
      onClick={() => navigate(`/playbooks/${playbook.id}`)}
      className="group text-left w-full rounded-xl border border-border bg-card hover:border-primary/40 hover:bg-card/80 transition-all duration-150 p-5 flex flex-col gap-3 cursor-pointer"
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            {playbook.is_official && (
              <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-primary/10 text-primary border border-primary/20">
                Official
              </span>
            )}
            {playbook.category && (
              <span
                className={`text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded border ${categoryStyle}`}
              >
                {playbook.category}
              </span>
            )}
          </div>
          <h3 className="font-semibold text-foreground text-sm leading-snug line-clamp-2 group-hover:text-primary transition-colors">
            {playbook.title}
          </h3>
        </div>
        <div className="shrink-0 mt-0.5">
          {playbook.os_family === "windows" ? (
            <Monitor className="h-4 w-4 text-muted-foreground" />
          ) : (
            <Terminal className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </div>

      {/* Description */}
      {playbook.description && (
        <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed">
          {playbook.description}
        </p>
      )}

      {/* Tags */}
      {playbook.tags && playbook.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {playbook.tags.slice(0, 4).map((tag) => (
            <span
              key={tag}
              className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground"
            >
              {tag}
            </span>
          ))}
          {playbook.tags.length > 4 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
              +{playbook.tags.length - 4}
            </span>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between text-xs text-muted-foreground mt-auto pt-1 border-t border-border">
        <div className="flex items-center gap-3">
          {playbook.est_runtime_sec != null && (
            <span className="flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {fmtRuntime(playbook.est_runtime_sec)}
            </span>
          )}
          <span className="flex items-center gap-1">
            <Play className="h-3 w-3" />
            {playbook.run_count.toLocaleString()} runs
          </span>
        </div>
        <span className="text-[10px] text-muted-foreground/60">v{playbook.version}</span>
      </div>
    </button>
  )
}

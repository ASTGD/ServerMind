import { Check, Ban, Loader2, AlertTriangle, Bot } from "lucide-react"
import { useMcpActivity } from "@/hooks/useMcpActivity"
import type { McpActivityItem } from "@/api/mcp"

/** What the customer's connected AI did — the "following along" mode of Activity.
 *
 * Deliberately NO progress bar: these actions belong to no known plan, and a bar with no
 * known end is a lie (docs/BLUEPRINTS-PLAN.md §9.2). A growing list, newest first, each
 * row keeping its outcome. Blueprint runs the AI starts show above as full runs; these are
 * the loose one-off actions. */
function Row({ a }: { a: McpActivityItem }) {
  const icon =
    a.status === "running" ? <Loader2 size={14} className="mt-0.5 shrink-0 animate-spin text-primary" />
    : a.status === "ok" ? <Check size={14} className="mt-0.5 shrink-0 text-emerald-600 dark:text-emerald-400" />
    : a.status === "blocked" ? <Ban size={14} className="mt-0.5 shrink-0 text-red-600 dark:text-red-400" />
    : <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400" />
  const when = new Date(a.started_at).toLocaleTimeString()
  return (
    <div className="flex items-start gap-2.5 border-b border-border px-4 py-2.5 last:border-0">
      {icon}
      <div className="min-w-0 flex-1">
        <p className="text-[13px] leading-snug">{a.label}</p>
        <p className="text-xs text-muted-foreground">
          {a.client_name || "Connected AI"}{a.server_name ? ` · ${a.server_name}` : ""} · {when}
          {a.status === "blocked" ? " · refused by ServerAlly" : ""}
        </p>
        {a.command && (
          <p className="mt-1 truncate rounded bg-muted px-2 py-1 font-mono text-[11px] text-muted-foreground">
            {a.command}
          </p>
        )}
      </div>
    </div>
  )
}

export default function AiActionsCard({ hasMcp }: { hasMcp: boolean }) {
  const { data: items = [] } = useMcpActivity(false, hasMcp)
  if (!hasMcp || items.length === 0) return null
  return (
    <div>
      <p className="mb-2 flex items-center gap-1.5 text-[13px] font-medium text-muted-foreground">
        <Bot size={14} /> Your connected AI
      </p>
      <div className="overflow-hidden rounded-xl border border-border bg-card">
        {items.slice(0, 20).map((a) => <Row key={a.id} a={a} />)}
      </div>
    </div>
  )
}

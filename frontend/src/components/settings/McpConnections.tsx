import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Copy, Check, Trash2, Plug, Loader2 } from "lucide-react"
import { getMcpInfo, listMcpConnections, revokeMcpConnection } from "@/api/mcp"
import { Button } from "@/components/ui"

function timeAgo(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return "just now"
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.floor(h / 24)
  if (d < 30) return `${d}d ago`
  return new Date(iso).toLocaleDateString()
}

/** A copyable code line. */
function CodeBox({ text }: { text: string }) {
  return (
    <code className="block overflow-x-auto whitespace-pre rounded-lg border border-border bg-muted/50 px-3 py-2 text-xs">
      {text}
    </code>
  )
}

/**
 * "Connected applications" — the MCP endpoint to connect an AI client, plus the list of
 * connected clients with a Revoke button. Renders inside the Settings `Section` wrapper.
 */
export default function McpConnections() {
  const qc = useQueryClient()
  const { data: info } = useQuery({ queryKey: ["mcp-info"], queryFn: getMcpInfo })
  const { data: conns = [], isLoading } = useQuery({ queryKey: ["mcp-connections"], queryFn: listMcpConnections })
  const [copied, setCopied] = useState(false)
  const revoke = useMutation({
    mutationFn: revokeMcpConnection,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["mcp-connections"] }),
  })

  const url = info?.url ?? ""

  const copy = () => {
    if (!url) return
    void navigator.clipboard.writeText(url)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const onRevoke = (grantId: string, name: string) => {
    if (window.confirm(`Revoke access for ${name}? It will lose access to your servers immediately.`)) {
      revoke.mutate(grantId)
    }
  }

  return (
    <div className="mt-4 space-y-6">
      {/* Endpoint + how to connect */}
      <div>
        <div className="text-xs font-medium text-muted-foreground">Your MCP endpoint</div>
        <div className="mt-1.5 flex items-center gap-2">
          <code className="flex-1 truncate rounded-lg border border-border bg-muted/50 px-3 py-2 text-sm">
            {url || "…"}
          </code>
          <Button size="sm" variant="outline" onClick={copy} disabled={!url}>
            {copied ? <Check size={14} /> : <Copy size={14} />}
            {copied ? "Copied" : "Copy"}
          </Button>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Add this in your AI client to manage your servers by chat — you'll sign in here to approve. In
          <span className="font-medium text-foreground"> Claude Code</span>:
        </p>
        <div className="mt-1.5">
          <CodeBox text={`claude mcp add --transport http serverally ${url || "<url>"}`} />
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          In <span className="font-medium text-foreground">Claude Desktop</span> or{" "}
          <span className="font-medium text-foreground">ChatGPT</span>: Settings → Connectors → add a custom
          connector and paste the URL.
        </p>
      </div>

      {/* Connected apps */}
      <div>
        <div className="mb-2 text-xs font-medium text-muted-foreground">Connected apps</div>
        {isLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="animate-spin" size={14} /> Loading…
          </div>
        ) : conns.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
            No apps connected yet. Add the endpoint above in your AI client to connect.
          </div>
        ) : (
          <ul className="space-y-2">
            {conns.map((c) => {
              const name = c.client_name || c.client_id
              return (
                <li
                  key={c.grant_id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background px-3 py-2.5"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <Plug size={14} className="shrink-0 text-primary" />
                      <span className="truncate text-sm font-medium">{name}</span>
                      <span className="shrink-0 rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                        {c.scopes.join(" ") || "mcp"}
                      </span>
                    </div>
                    <div className="mt-0.5 text-xs text-muted-foreground">
                      Connected {timeAgo(c.connected_at)} · active {timeAgo(c.last_active)}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => onRevoke(c.grant_id, name)}
                    disabled={revoke.isPending}
                    className="shrink-0 text-red-600 hover:bg-red-50 hover:text-red-700 dark:text-red-400 dark:hover:bg-red-950/30"
                  >
                    <Trash2 size={14} /> Revoke
                  </Button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </div>
  )
}

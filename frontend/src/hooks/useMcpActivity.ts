import { useQuery } from "@tanstack/react-query"
import { listMcpActivity } from "@/api/mcp"

/**
 * Shared MCP activity query. `fast` (drawer open) polls ~2s; otherwise ~2.5s so the top-bar
 * badge still catches a newly-running action within a couple seconds. All callers share ONE
 * cache (same queryKey), so this runs a single poll no matter how many components read it.
 * `enabled` gates it to users who actually have a connected AI client — no MCP, no polling.
 */
export function useMcpActivity(fast: boolean, enabled = true) {
  return useQuery({
    queryKey: ["mcp-activity"],
    queryFn: listMcpActivity,
    refetchInterval: enabled ? (fast ? 2000 : 2500) : false,
    refetchIntervalInBackground: false,
    enabled,
  })
}

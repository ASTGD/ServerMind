import { useQuery } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { Link } from "react-router-dom"
import { listRuns } from "@/api/blueprints"

/** The global "something is running" signal in the top bar.
 *
 * ABSENT when nothing runs — never greyed out — the same rule the menus follow. It is a
 * signpost, not a destination: one line and a link; the reading happens on Activity. */
export default function RunningPill() {
  const { data: runs = [] } = useQuery({
    queryKey: ["blueprint-runs"],
    queryFn: () => listRuns(),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((r) => r.status === "running") ? 3000 : 20000,
  })
  const running = runs.filter((r) => r.status === "running")
  if (running.length === 0) return null

  const first = running[0]
  const label = running.length === 1
    ? `${first.title.split(" — ")[1] ?? first.title} · ${Math.min(first.current + 1, first.steps_total)} of ${first.steps_total}`
    : `${running.length} jobs running`
  return (
    <Link to={running.length === 1 ? `/activity/${first.id}` : "/activity"}
      className="hidden items-center gap-2 rounded-full border border-primary/30 bg-primary/5 px-3 py-1 text-xs text-primary hover:bg-primary/10 sm:flex">
      <Loader2 size={12} className="animate-spin" />
      <span className="max-w-[220px] truncate">{label}</span>
    </Link>
  )
}

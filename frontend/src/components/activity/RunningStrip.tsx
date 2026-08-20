import { useQuery } from "@tanstack/react-query"
import { Loader2, ArrowRight } from "lucide-react"
import { Link } from "react-router-dom"
import { listRuns } from "@/api/blueprints"

/** One line at the top of a server's (or site's) own pages: something is running HERE.
 *
 * A signpost, not a destination — it says the fact and links to Activity, where the
 * reading happens. Absent entirely when nothing runs on this server; never grows past one
 * line (two jobs → "2 jobs running here"). `domain` narrows it to runs about one site. */
export default function RunningStrip({ serverId, domain }: { serverId: string; domain?: string }) {
  const { data: runs = [] } = useQuery({
    queryKey: ["blueprint-runs", serverId],
    queryFn: () => listRuns(serverId),
    refetchInterval: (q) =>
      (q.state.data ?? []).some((r) => r.status === "running") ? 3000 : 20000,
  })
  const here = runs.filter((r) =>
    r.status === "running" && (!domain || r.inputs.domain === domain))
  if (here.length === 0) return null

  const first = here[0]
  const text = here.length > 1
    ? `${here.length} jobs running here`
    : domain
      ? `This site is being set up — step ${Math.min(first.current + 1, first.steps_total)} of ${first.steps_total}`
      : `${first.title} — step ${Math.min(first.current + 1, first.steps_total)} of ${first.steps_total}`
  return (
    <Link to={here.length === 1 ? `/activity/${first.id}` : "/activity"}
      className="mb-4 flex items-center gap-2.5 rounded-lg border border-primary/30 bg-primary/5 px-3.5 py-2.5 text-sm text-primary hover:bg-primary/10">
      <Loader2 size={15} className="shrink-0 animate-spin" />
      <span className="min-w-0 flex-1 truncate">{text}</span>
      <span className="flex shrink-0 items-center gap-1 text-[13px]">Open <ArrowRight size={13} /></span>
    </Link>
  )
}

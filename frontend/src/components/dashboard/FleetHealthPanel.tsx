import { useMemo } from "react"
import { useNavigate } from "react-router-dom"
import { ResponsiveContainer, PieChart, Pie, Cell } from "recharts"
import { ShieldCheck } from "lucide-react"
import type { FleetHealth, FleetFinding } from "@/api/fleet"
import type { Server } from "@/types"
import { useAssistantStore } from "@/store/assistantStore"
import { Card } from "@/components/ui"
import { cn } from "@/lib/utils"

const SEVERITY_RANK: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 }
const SEV_DOT: Record<string, string> = {
  critical: "bg-red-500",
  high: "bg-orange-500",
  medium: "bg-amber-500",
  low: "bg-blue-500",
  info: "bg-zinc-400",
}
// Theme-aware token colors — recharts fills accept CSS var() strings (rendered as SVG fill).
const BUCKET_COLOR = {
  healthy: "hsl(var(--success))",
  fair: "hsl(var(--warning))",
  atRisk: "hsl(var(--destructive))",
} as const

interface FlatFinding extends FleetFinding {
  serverId: string
  serverName: string
}

/**
 * The dashboard's fleet-health centerpiece: a grade-distribution donut (average
 * score centered) plus only the top 2 findings fleet-wide, worst first — not a
 * per-server findings dump. Findings keep the same one-click-fix action as the
 * old full report (open Ally with a seeded prompt, or jump to the right page).
 */
export default function FleetHealthPanel({ health, servers }: { health?: FleetHealth; servers: Server[] }) {
  const navigate = useNavigate()
  const openServer = useAssistantStore((s) => s.openServer)
  const serverById = useMemo(() => new Map(servers.map((s) => [s.id, s])), [servers])

  const { buckets, avgScore, topFindings, moreCount } = useMemo(() => {
    if (!health || health.servers.length === 0) {
      return { buckets: [] as { name: string; value: number; color: string }[], avgScore: 0, topFindings: [] as FlatFinding[], moreCount: 0 }
    }
    let healthy = 0
    let fair = 0
    let atRisk = 0
    let scoreSum = 0
    const flat: FlatFinding[] = []
    for (const s of health.servers) {
      scoreSum += s.score
      if (s.grade === "A" || s.grade === "B") healthy++
      else if (s.grade === "C") fair++
      else atRisk++
      for (const f of s.findings) flat.push({ ...f, serverId: s.server_id, serverName: s.name })
    }
    flat.sort((a, b) => (SEVERITY_RANK[a.severity] ?? 9) - (SEVERITY_RANK[b.severity] ?? 9))
    const buckets = [
      { name: "healthy", value: healthy, color: BUCKET_COLOR.healthy },
      { name: "fair", value: fair, color: BUCKET_COLOR.fair },
      { name: "atRisk", value: atRisk, color: BUCKET_COLOR.atRisk },
    ].filter((b) => b.value > 0)
    return {
      buckets,
      avgScore: Math.round(scoreSum / health.servers.length),
      topFindings: flat.slice(0, 2),
      moreCount: Math.max(0, flat.length - 2),
    }
  }, [health])

  function act(f: FlatFinding) {
    const a = f.action
    if (a.kind === "chat" && a.seed) {
      const s = serverById.get(f.serverId)
      if (s) openServer(s, a.seed)
    } else if (a.kind === "page" && a.path) {
      navigate(a.path)
    }
  }

  if (!health) return null

  return (
    <Card className="p-5">
      <h2 className="mb-3 text-sm font-semibold text-foreground">Fleet health</h2>

      <div className="mb-3.5 flex items-center gap-5">
        <div className="relative h-[100px] w-[100px] shrink-0">
          {buckets.length > 0 ? (
            <ResponsiveContainer width={100} height={100}>
              <PieChart>
                <Pie
                  data={buckets}
                  dataKey="value"
                  innerRadius={34}
                  outerRadius={46}
                  startAngle={90}
                  endAngle={-270}
                  stroke="none"
                  isAnimationActive={false}
                >
                  {buckets.map((b) => (
                    <Cell key={b.name} fill={b.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full w-full rounded-full border-[11px] border-muted" />
          )}
          <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-[22px] font-semibold tabular-nums text-foreground">{avgScore}</span>
            <span className="text-[10px] text-muted-foreground">score</span>
          </div>
        </div>
        <div className="flex flex-col gap-1.5 text-xs text-foreground">
          {buckets.map((b) => (
            <div key={b.name} className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: b.color }} />
              {b.value} {b.name === "healthy" ? "healthy, grade A-B" : b.name === "fair" ? "fair, grade C" : "at risk, grade D-F"}
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-border pt-3">
        {topFindings.length === 0 ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <ShieldCheck size={13} className="text-success" />
            Everything looks healthy.
          </div>
        ) : (
          <>
            <p className="mb-1.5 text-[11px] text-muted-foreground">Needs attention</p>
            {topFindings.map((f) => (
              <button
                key={`${f.serverId}-${f.id}`}
                onClick={() => act(f)}
                className="flex w-full items-center gap-2 rounded-md py-1 text-left text-[13px] text-foreground transition-colors hover:bg-accent"
              >
                <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", SEV_DOT[f.severity] ?? SEV_DOT.info)} />
                <span className="min-w-0 flex-1 truncate">
                  {f.serverName}, {f.title.charAt(0).toLowerCase() + f.title.slice(1)}
                </span>
              </button>
            ))}
            {moreCount > 0 && (
              <button
                onClick={() => navigate("/servers")}
                className="pt-1 text-xs text-primary hover:underline"
              >
                View {moreCount} more finding{moreCount === 1 ? "" : "s"}
              </button>
            )}
          </>
        )}
      </div>
    </Card>
  )
}

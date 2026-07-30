import { Cpu, MemoryStick, HardDrive, Activity } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import type { MetricPoint } from "@/api/monitoring"
import { summariseMetric, formatMetric, type MetricKey } from "./metricStats"

/**
 * Current, average and peak per metric — the numbers that make a quiet server readable.
 *
 * A chart shows shape; these show scale. On a box idling at 0.3% the line is flat either
 * way, but "peaked at 96%" is what tells an owner last night's backup nearly ran it out of
 * memory. Average and peak are computed from the history the page has already fetched, so
 * this costs no extra request.
 */

interface Metric {
  key: MetricKey
  label: string
  icon: LucideIcon
  unit: "percent" | "load"
  current: number | null | undefined
  /** e.g. "0.5 / 1.9 GB" — a percentage alone hides how much room is actually left. */
  detail?: string
}

interface Props {
  history: MetricPoint[]
  cpu: number | null | undefined
  ram: number | null | undefined
  disk: number | null | undefined
  load: number | null | undefined
  ramDetail?: string
  diskDetail?: string
  /** Shown so "Avg" is never ambiguous about the period it covers. */
  windowLabel: string
  /**
   * Two columns instead of four, for a narrow container.
   *
   * A prop rather than `lg:grid-cols-4`, because Tailwind breakpoints follow the VIEWPORT:
   * on a wide screen a narrow column would still try four across and squash them. Same
   * mistake cost a live pixel-measuring session on the Assets cards.
   */
  compact?: boolean
}

/** Warm the number, not the whole card — colour should mean "look here", not decoration. */
function toneFor(value: number | null | undefined, unit: "percent" | "load"): string {
  if (value === null || value === undefined) return "text-foreground"
  if (unit === "load") return "text-foreground"
  if (value >= 90) return "text-destructive"
  if (value >= 75) return "text-[hsl(var(--warning))]"
  return "text-foreground"
}

export default function MetricKpis({
  history, cpu, ram, disk, load, ramDetail, diskDetail, windowLabel, compact = false,
}: Props) {
  const metrics: Metric[] = [
    { key: "cpu_percent", label: "CPU", icon: Cpu, unit: "percent", current: cpu },
    { key: "ram_percent", label: "RAM", icon: MemoryStick, unit: "percent", current: ram,
      detail: ramDetail },
    { key: "disk_percent", label: "Disk", icon: HardDrive, unit: "percent", current: disk,
      detail: diskDetail },
    { key: "load_1", label: "Load avg", icon: Activity, unit: "load", current: load },
  ]

  return (
    <div className={`grid gap-3 ${compact ? "grid-cols-2" : "grid-cols-2 lg:grid-cols-4"}`}>
      {metrics.map((m) => {
        const stats = summariseMetric(history, m.key)
        const Icon = m.icon
        return (
          <div key={m.key} className="rounded-lg border border-border bg-background p-3">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                <Icon size={13} /> {m.label}
              </div>
              {stats ? (
                <div className="text-right text-[11px] leading-tight text-muted-foreground">
                  <div>Avg {formatMetric(stats.avg, m.unit)}</div>
                  <div>Peak {formatMetric(stats.peak, m.unit)}</div>
                </div>
              ) : (
                // Never invent an average. A Windows box has no load average, and a
                // just-added server has no history yet — both should say so.
                <div className="text-[11px] text-muted-foreground/70">no history</div>
              )}
            </div>
            <p className={`mt-1.5 font-mono text-2xl font-semibold ${toneFor(m.current, m.unit)}`}>
              {m.current === null || m.current === undefined
                ? "—"
                : formatMetric(Number(m.current), m.unit)}
            </p>
            <p className="mt-0.5 text-[10px] text-muted-foreground/70">
              {m.detail ?? (stats ? `over ${windowLabel}` : " ")}
            </p>
          </div>
        )
      })}
    </div>
  )
}

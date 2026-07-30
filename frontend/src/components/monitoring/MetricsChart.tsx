import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts"
import { format } from "date-fns"
import type { MetricPoint } from "@/api/monitoring"

/**
 * One chart for everything the server reports, rather than a stack of three.
 *
 * Three separate charts made comparison — the actual question — impossible: "was the CPU
 * spike the same moment memory ran out?" needed the reader to line up three x-axes by eye.
 * On one pair of axes the answer is visible at a glance, and the page stops being a column
 * of near-identical flat lines.
 *
 * Load average gets the RIGHT axis, deliberately. It is not a percentage — a load of 3.0 on
 * a 4-core box is busy but healthy, and plotting it on a 0–100 scale pins it to the floor
 * where it can never be read. Two scales cost one extra label; a permanently flat line costs
 * the whole metric.
 */

const SERIES = [
  { key: "cpu", name: "CPU", color: "#3b82f6", axis: "pct" },        // blue-500
  { key: "ram", name: "RAM", color: "#ef4444", axis: "pct" },        // red-500
  { key: "disk", name: "Disk", color: "#d97706", axis: "pct" },      // amber-600
  { key: "load", name: "Load average", color: "#10b981", axis: "load" }, // emerald-500
] as const

interface Props {
  data: MetricPoint[]
  height?: number
}

type Row = {
  time: string
  cpu: number | null
  ram: number | null
  disk: number | null
  load: number | null
}

/** DECIMAL columns arrive as strings over JSON; anything unusable becomes null, not 0. */
function num(v: number | string | null | undefined): number | null {
  if (v === null || v === undefined) return null
  const n = typeof v === "string" ? Number(v) : v
  return Number.isFinite(n) ? n : null
}

function round(v: number | null, dp: number): number | null {
  return v === null ? null : Number(v.toFixed(dp))
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-lg">
      <p className="mb-1 text-muted-foreground">
        {label ? format(new Date(label as string), "MMM d, HH:mm") : ""}
      </p>
      {SERIES.map((s) => {
        const row = payload.find((p: { dataKey: string }) => p.dataKey === s.key)
        if (!row || row.value === null || row.value === undefined) return null
        return (
          <p key={s.key} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full" style={{ background: s.color }} />
              <span className="text-muted-foreground">{s.name}</span>
            </span>
            <span className="font-mono font-medium text-foreground">
              {s.axis === "load" ? Number(row.value).toFixed(2) : `${Number(row.value).toFixed(1)}%`}
            </span>
          </p>
        )
      })}
    </div>
  )
}

export default function MetricsChart({ data, height = 260 }: Props) {
  const rows: Row[] = data.map((p) => ({
    time: p.recorded_at,
    cpu: round(num(p.cpu_percent), 1),
    ram: round(num(p.ram_percent), 1),
    disk: round(num(p.disk_percent), 1),
    load: round(num(p.load_1), 2),
  }))

  // A Windows server records no load average at all, so hide the right axis rather than
  // labelling an axis that governs nothing.
  const hasLoad = rows.some((r) => r.load !== null)

  return (
    <ResponsiveContainer width="100%" height={height}>
      {/* No negative left margin: it clipped the leading "1" off "100%" (measured — the
          label began 5px left of the chart surface, so it rendered as "00%"). The old
          per-metric charts could get away with -20 because their widest label was "75%". */}
      <LineChart data={rows} margin={{ top: 6, right: hasLoad ? 4 : 12, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
        <XAxis
          dataKey="time"
          tickFormatter={(v) => format(new Date(v as string), "HH:mm")}
          tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
          minTickGap={28}
        />
        <YAxis
          yAxisId="pct"
          domain={[0, 100]}
          tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: number) => `${v}%`}
          width={44}
        />
        {hasLoad && (
          <YAxis
            yAxisId="load"
            orientation="right"
            // Never let a quiet server draw a full-height load line: the axis starts at a
            // sensible floor so 0.02 looks like nothing, which is what it is.
            domain={[0, (max: number) => Math.max(1, Math.ceil(max * 1.2))]}
            tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
            tickLine={false}
            axisLine={false}
            width={34}
          />
        )}
        <Tooltip content={<ChartTooltip />} />
        <Legend
          verticalAlign="bottom"
          height={26}
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: 11 }}
        />
        {SERIES.map((s) =>
          s.axis === "load" && !hasLoad ? null : (
            <Line
              key={s.key}
              yAxisId={s.axis}
              type="monotone"
              dataKey={s.key}
              name={s.name}
              stroke={s.color}
              strokeWidth={1.75}
              dot={false}
              activeDot={{ r: 3 }}
              connectNulls
            />
          ),
        )}
      </LineChart>
    </ResponsiveContainer>
  )
}

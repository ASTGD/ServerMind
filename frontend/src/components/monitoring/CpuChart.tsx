import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts"
import { format } from "date-fns"
import type { MetricPoint } from "@/api/monitoring"

interface Props {
  data: MetricPoint[]
  height?: number
}

function colorForValue(v: number): string {
  if (v >= 90) return "#f87171" // red-400
  if (v >= 75) return "#fb923c" // orange-400
  return "#34d399"              // emerald-400
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const v = payload[0]?.value as number | undefined
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-lg">
      <p className="text-muted-foreground mb-1">
        {label ? format(new Date(label as string), "MMM d, HH:mm") : ""}
      </p>
      <p className="font-semibold text-foreground">
        CPU: {v != null ? `${v.toFixed(1)}%` : "—"}
      </p>
    </div>
  )
}

export default function CpuChart({ data, height = 180 }: Props) {
  const lastValue = data.length ? (data[data.length - 1].cpu_percent ?? 0) : 0
  const color = colorForValue(lastValue)

  const chartData = data.map((p) => ({
    time: p.recorded_at,
    cpu: p.cpu_percent != null ? +p.cpu_percent.toFixed(1) : null,
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id="cpuGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.3} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
        <XAxis
          dataKey="time"
          tickFormatter={(v) => format(new Date(v as string), "HH:mm")}
          tick={{ fontSize: 10, fill: "rgba(255,255,255,0.35)" }}
          tickLine={false}
          axisLine={false}
          interval="preserveStartEnd"
        />
        <YAxis
          domain={[0, 100]}
          tick={{ fontSize: 10, fill: "rgba(255,255,255,0.35)" }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: number) => `${v}%`}
        />
        <Tooltip content={<CustomTooltip />} />
        <Area
          type="monotone"
          dataKey="cpu"
          stroke={color}
          strokeWidth={2}
          fill="url(#cpuGrad)"
          dot={false}
          connectNulls
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}

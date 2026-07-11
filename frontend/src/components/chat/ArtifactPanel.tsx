import { memo } from "react"
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
} from "recharts"

/**
 * A Workspace artifact Ally chose to SHOW — a table or a small chart (Track B Phase 2).
 * Ally appends these as `ally-artifact` JSON blocks; the backend validates + forwards them,
 * and they render as panels in the Workspace beside the chat (not buried in the prose).
 */
export type Artifact =
  | { type: "table"; title?: string; columns: string[]; rows: string[][] }
  | {
      type: "chart"
      chartType: "bar" | "pie"
      title?: string
      data: { label: string; value: number }[]
    }

// A calm, theme-agnostic palette for bars / pie slices (readable in light + dark).
const PALETTE = ["#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#06b6d4", "#a855f7", "#ec4899", "#14b8a6"]

function TableArtifact({ columns, rows }: { columns: string[]; rows: string[][] }) {
  return (
    <div className="max-h-80 overflow-auto">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr>
            {columns.map((c, i) => (
              <th
                key={i}
                className="sticky top-0 border-b border-border bg-muted px-2 py-1.5 text-left font-semibold text-foreground"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr key={ri} className="odd:bg-muted/30">
              {r.map((cell, ci) => (
                <td key={ci} className="border-b border-border px-2 py-1 align-top text-foreground">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ChartArtifact({
  chartType,
  data,
}: {
  chartType: "bar" | "pie"
  data: { label: string; value: number }[]
}) {
  const axis = "hsl(var(--muted-foreground))"
  if (chartType === "pie") {
    return (
      <ResponsiveContainer width="100%" height={240}>
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="label" cx="50%" cy="50%" outerRadius={82} label>
            {data.map((_, i) => (
              <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Pie>
          <Tooltip />
        </PieChart>
      </ResponsiveContainer>
    )
  }
  const rotate = data.length > 5
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11, fill: axis }}
          interval={0}
          angle={rotate ? -30 : 0}
          textAnchor={rotate ? "end" : "middle"}
          height={rotate ? 54 : 24}
        />
        <YAxis tick={{ fontSize: 11, fill: axis }} allowDecimals={false} width={32} />
        <Tooltip cursor={{ fill: "hsl(var(--muted))" }} />
        <Bar dataKey="value" radius={[3, 3, 0, 0]}>
          {data.map((_, i) => (
            <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

function ArtifactImpl({ artifact }: { artifact: Artifact }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      {artifact.title && (
        <div className="border-b border-border px-3 py-2 text-sm font-semibold text-foreground">
          {artifact.title}
        </div>
      )}
      <div className="p-3">
        {artifact.type === "table" ? (
          <TableArtifact columns={artifact.columns} rows={artifact.rows} />
        ) : (
          <ChartArtifact chartType={artifact.chartType} data={artifact.data} />
        )}
      </div>
    </div>
  )
}

/** Memoized — artifact data is static once produced. */
const ArtifactPanel = memo(ArtifactImpl)
export default ArtifactPanel

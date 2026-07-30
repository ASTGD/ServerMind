import type { MetricPoint } from "@/api/monitoring"

/**
 * Average and peak for one metric over the loaded window.
 *
 * Why this exists: a chart alone tells you almost nothing on a quiet server. A box idling
 * at 0.3% CPU draws a flat line at the bottom whether it spent the night at 3% or spiked to
 * 97% for four minutes at 04:00. "Peaked at 97%" is the sentence an owner actually needs,
 * and it is the reason every competitor puts these two numbers above the graph.
 *
 * Nulls are genuinely present in our history — Windows servers record no load average, and
 * a collection can partially fail — so they are skipped rather than counted as zero.
 * Counting them as zero would drag the average down and quietly under-report load.
 */
export interface MetricSummary {
  avg: number
  peak: number
  /** How many points actually carried a value — lets the UI stay honest about thin data. */
  samples: number
}

export type MetricKey = "cpu_percent" | "ram_percent" | "disk_percent" | "load_1"

export function summariseMetric(
  history: MetricPoint[],
  key: MetricKey,
): MetricSummary | null {
  let total = 0
  let peak = -Infinity
  let samples = 0

  for (const point of history) {
    const raw = point[key]
    // A metric can be null (not collected) or arrive as a numeric string from the API's
    // DECIMAL columns, so coerce and reject anything that is not a finite number.
    const value = typeof raw === "string" ? Number(raw) : raw
    if (value === null || value === undefined || !Number.isFinite(value)) continue
    total += value as number
    if ((value as number) > peak) peak = value as number
    samples += 1
  }

  if (samples === 0) return null
  return { avg: total / samples, peak, samples }
}

/** Round for display without ever showing a peak lower than the average. */
export function formatMetric(value: number, unit: "percent" | "load"): string {
  if (unit === "load") return value.toFixed(2)
  return `${value.toFixed(1)}%`
}

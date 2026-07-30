import { describe, it, expect } from "vitest"
import { summariseMetric, formatMetric } from "./metricStats"
import type { MetricPoint } from "@/api/monitoring"

function point(values: Partial<MetricPoint>): MetricPoint {
  return {
    id: "x", server_id: "s",
    cpu_percent: null, ram_percent: null, ram_used_mb: null, ram_total_mb: null,
    disk_percent: null, disk_used_gb: null, disk_total_gb: null,
    load_1: null, load_5: null, load_15: null, uptime_seconds: null,
    recorded_at: "2026-07-30T10:00:00Z",
    ...values,
  }
}

describe("summariseMetric", () => {
  it("returns the average and the peak", () => {
    const h = [10, 20, 90, 20].map((v) => point({ cpu_percent: v }))
    const s = summariseMetric(h, "cpu_percent")
    expect(s).not.toBeNull()
    expect(s!.avg).toBe(35)
    expect(s!.peak).toBe(90)
    expect(s!.samples).toBe(4)
  })

  it("skips nulls instead of counting them as zero", () => {
    // Counting a missing sample as 0 would report avg 20 and hide how busy the server was.
    const h = [point({ cpu_percent: 40 }), point({ cpu_percent: null }), point({ cpu_percent: 40 })]
    const s = summariseMetric(h, "cpu_percent")
    expect(s!.avg).toBe(40)
    expect(s!.samples).toBe(2)
  })

  it("returns null when nothing was collected, so the UI can say so", () => {
    // A Windows server records no load average — inventing 0.00 would be a lie.
    expect(summariseMetric([point({ cpu_percent: 5 })], "load_1")).toBeNull()
    expect(summariseMetric([], "cpu_percent")).toBeNull()
  })

  it("handles the numeric strings our DECIMAL columns serialise to", () => {
    const h = [
      point({ cpu_percent: "12.5" as unknown as number }),
      point({ cpu_percent: "87.5" as unknown as number }),
    ]
    const s = summariseMetric(h, "cpu_percent")
    expect(s!.avg).toBe(50)
    expect(s!.peak).toBe(87.5)
  })

  it("ignores values that are not real numbers", () => {
    const h = [
      point({ cpu_percent: 50 }),
      point({ cpu_percent: NaN }),
      point({ cpu_percent: "n/a" as unknown as number }),
    ]
    const s = summariseMetric(h, "cpu_percent")
    expect(s!.avg).toBe(50)
    expect(s!.samples).toBe(1)
  })

  it("never reports a peak below the average", () => {
    const h = [1, 2, 3, 99].map((v) => point({ ram_percent: v }))
    const s = summariseMetric(h, "ram_percent")!
    expect(s.peak).toBeGreaterThanOrEqual(s.avg)
  })

  it("copes with a single sample", () => {
    const s = summariseMetric([point({ disk_percent: 61.4 })], "disk_percent")!
    expect(s.avg).toBeCloseTo(61.4)
    expect(s.peak).toBeCloseTo(61.4)
  })

  it("keeps load average out of percent formatting", () => {
    // 0.4% would be nonsense for a load average; 0.40 is the number a sysadmin expects.
    expect(formatMetric(0.4, "load")).toBe("0.40")
    expect(formatMetric(0.4, "percent")).toBe("0.4%")
  })
})

import { describe, it, expect } from "vitest"
import { hasSeenSetupResult, markSetupResultSeen, shouldShowSetupResult } from "./setupSeen"

const NOW = new Date("2026-08-03T12:00:00Z").getTime()
const run = (over: Partial<{ id: string; status: string; finished_at: string | null }> = {}) => ({
  id: "run-1", status: "done", finished_at: "2026-08-03T11:59:00Z", ...over,
})

describe("showing a finished setup before moving on", () => {
  it("shows a run that just finished", () => {
    // The bug: it finished in under two minutes and the page moved on without saying so.
    expect(shouldShowSetupResult(run(), NOW)).toBe(true)
  })

  it("stops once the customer has acknowledged it", () => {
    expect(shouldShowSetupResult(run({ id: "ack-me" }), NOW)).toBe(true)
    markSetupResultSeen("ack-me")
    expect(shouldShowSetupResult(run({ id: "ack-me" }), NOW)).toBe(false)
  })

  it("does not turn the server's home into an old receipt", () => {
    // Someone who wanders off without clicking must still get their server back.
    expect(shouldShowSetupResult(run({ finished_at: "2026-08-01T11:00:00Z" }), NOW)).toBe(false)
  })

  it("never holds a run that failed or is still going", () => {
    expect(shouldShowSetupResult(run({ status: "failed" }), NOW)).toBe(false)
    expect(shouldShowSetupResult(run({ status: "running", finished_at: null }), NOW)).toBe(false)
  })

  it("is not confused by a clock that disagrees with the server's", () => {
    // A finish stamped slightly in the future must not read as an hour-old run.
    expect(shouldShowSetupResult(run({ finished_at: "2026-08-03T12:05:00Z" }), NOW)).toBe(false)
  })

  it("works where there is no browser storage at all", () => {
    // This test runs without a DOM, so it exercises exactly the private-browsing path:
    // nothing may throw, and a dismissal must still hold for the rest of the visit.
    expect(hasSeenSetupResult("no-storage")).toBe(false)
    expect(() => markSetupResultSeen("no-storage")).not.toThrow()
    expect(hasSeenSetupResult("no-storage")).toBe(true)
  })

  it("has nothing to show when there has never been a setup", () => {
    expect(shouldShowSetupResult(null, NOW)).toBe(false)
  })
})

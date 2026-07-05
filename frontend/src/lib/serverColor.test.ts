import { describe, it, expect } from "vitest"
import { serverColor, FLEET_COLOR, type ServerColor } from "./serverColor"

describe("serverColor", () => {
  it("is stable — the same id always maps to the same color", () => {
    const a = serverColor("srv-abc-123")
    const b = serverColor("srv-abc-123")
    expect(a).toEqual(b)
  })

  it("depends on the id, not object identity", () => {
    // Distinct calls, distinct strings with the same value → identical color.
    const id = ["srv", "abc", "123"].join("-")
    expect(serverColor(id)).toEqual(serverColor("srv-abc-123"))
  })

  it("returns the neutral fleet color for an empty id", () => {
    expect(serverColor("")).toBe(FLEET_COLOR)
  })

  it("always returns a fully-formed color (chip + dot + ring)", () => {
    const ids = ["a", "server-1", "b7f3", "TestServer3", "éç", "0000-1111-2222"]
    for (const id of ids) {
      const c: ServerColor = serverColor(id)
      expect(c.chip).toBeTruthy()
      expect(c.dot).toBeTruthy()
      expect(c.ring).toBeTruthy()
    }
  })

  it("spreads a handful of ids across more than one hue (not all the same)", () => {
    const dots = new Set(
      ["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"].map((id) => serverColor(id).dot),
    )
    expect(dots.size).toBeGreaterThan(1)
  })
})

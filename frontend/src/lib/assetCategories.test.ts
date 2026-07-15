import { describe, it, expect } from "vitest"
import {
  ASSET_CATEGORIES,
  ADDABLE_CATEGORIES,
  inferCategory,
  categoryForServer,
  categoryById,
} from "./assetCategories"

describe("assetCategories registry", () => {
  it("has the six categories, all addable (cloud via its own flow)", () => {
    expect(ASSET_CATEGORIES.map((c) => c.id)).toEqual([
      "bare_metal", "vps", "hosting", "windows", "windows_rdp", "cloud",
    ])
    expect(ADDABLE_CATEGORIES.map((c) => c.id)).toEqual([
      "bare_metal", "vps", "hosting", "windows", "windows_rdp", "cloud",
    ])
    // every addable category either connects over a transport, or opens the cloud flow
    for (const c of ADDABLE_CATEGORIES) expect(Boolean(c.connectionType) || Boolean(c.cloudFlow)).toBe(true)
    // cloud is the account-import flow — no direct transport
    const cloud = categoryById("cloud")!
    expect(cloud.cloudFlow).toBe(true)
    expect(cloud.connectionType).toBeUndefined()
    // every category has the fields the tiles/cards read
    for (const c of ASSET_CATEGORIES) {
      expect(c.label).toBeTruthy()
      expect(c.blurb).toBeTruthy()
      expect(c.icon).toBeTruthy()
    }
  })

  it("infers category from transport (mirrors the backend)", () => {
    expect(inferCategory("winrm", null)).toBe("windows")
    expect(inferCategory("hosting", null)).toBe("hosting")
    expect(inferCategory("ssh", "cyberpanel")).toBe("hosting")
    expect(inferCategory("ssh", null)).toBe("vps")
  })

  it("categoryForServer prefers the stored category, else infers", () => {
    const base = { connection_type: "ssh" as const, panel_type: null }
    expect(categoryForServer({ ...base, category: "bare_metal" }).id).toBe("bare_metal")
    expect(categoryForServer({ ...base, category: null }).id).toBe("vps") // inferred
    // a stored category wins even against what the transport would infer
    expect(categoryForServer({ connection_type: "ssh" as const, panel_type: "cyberpanel", category: "vps" }).id).toBe("vps")
  })

  it("categoryById returns undefined for unknown ids", () => {
    expect(categoryById("nope")).toBeUndefined()
    expect(categoryById("windows")?.label).toBe("Windows Server")
  })
})

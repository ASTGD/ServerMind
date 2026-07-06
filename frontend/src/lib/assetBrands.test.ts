import { describe, it, expect } from "vitest"
import { hostingBrand, cloudBrand, type AssetBrand } from "./assetBrands"

describe("hostingBrand", () => {
  it("maps known panels to their proper name", () => {
    expect(hostingBrand("cpanel")?.name).toBe("cPanel")
    expect(hostingBrand("cyberpanel")?.name).toBe("CyberPanel")
    expect(hostingBrand("plesk")?.name).toBe("Plesk")
    expect(hostingBrand("directadmin")?.name).toBe("DirectAdmin")
  })
  it("returns undefined for unknown / absent panels", () => {
    expect(hostingBrand("unknown")).toBeUndefined()
    expect(hostingBrand(null)).toBeUndefined()
    expect(hostingBrand(undefined)).toBeUndefined()
    expect(hostingBrand("")).toBeUndefined()
  })
})

describe("cloudBrand", () => {
  it("maps known providers to their proper name", () => {
    expect(cloudBrand("aws")?.name).toBe("AWS")
    expect(cloudBrand("digitalocean")?.name).toBe("DigitalOcean")
    expect(cloudBrand("hetzner")?.name).toBe("Hetzner")
    expect(cloudBrand("gcp")?.name).toBe("Google Cloud")
    expect(cloudBrand("azure")?.name).toBe("Azure")
  })
  it("returns undefined for unknown / absent providers", () => {
    expect(cloudBrand("unknown")).toBeUndefined()
    expect(cloudBrand(null)).toBeUndefined()
    expect(cloudBrand(undefined)).toBeUndefined()
  })
})

describe("brand hygiene", () => {
  const fields: (keyof AssetBrand)[] = ["name", "card", "tile", "badge", "button"]
  const all = ["cpanel", "cyberpanel", "plesk", "directadmin"].map(hostingBrand)
    .concat(["aws", "digitalocean", "hetzner", "gcp", "azure"].map(cloudBrand))
  it("every brand fills in all class fields", () => {
    for (const b of all) {
      expect(b).toBeDefined()
      for (const f of fields) expect((b as AssetBrand)[f]).toBeTruthy()
    }
  })
})

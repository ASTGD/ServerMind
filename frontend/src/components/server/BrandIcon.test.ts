import { describe, it, expect } from "vitest"
import { osIconSlug, providerIconSlug, hasBrandIcon } from "./BrandIcon"

describe("osIconSlug", () => {
  it("maps common OS strings to a glyph slug", () => {
    expect(osIconSlug("Ubuntu 22.04")).toBe("ubuntu")
    expect(osIconSlug("ubuntu")).toBe("ubuntu")
    expect(osIconSlug("Debian 12")).toBe("debian")
    expect(osIconSlug("AlmaLinux 8.10")).toBe("almalinux")
    expect(osIconSlug("Rocky Linux 9")).toBe("rockylinux")
    expect(osIconSlug("CentOS 7")).toBe("centos")
    expect(osIconSlug("Fedora 40")).toBe("fedora")
    expect(osIconSlug("Red Hat Enterprise Linux")).toBe("redhat")
    expect(osIconSlug("rhel 9")).toBe("redhat")
    expect(osIconSlug("Windows Server 2022")).toBe("windows")
  })
  it("falls back to generic linux for other unix-likes", () => {
    expect(osIconSlug("Some Linux 1.0")).toBe("linux")
  })
  it("returns undefined for empty / unknown", () => {
    expect(osIconSlug(undefined)).toBeUndefined()
    expect(osIconSlug(null)).toBeUndefined()
    expect(osIconSlug("")).toBeUndefined()
    expect(osIconSlug("BeOS")).toBeUndefined()
  })
})

describe("providerIconSlug", () => {
  it("maps providers (gcp → googlecloud)", () => {
    expect(providerIconSlug("aws")).toBe("aws")
    expect(providerIconSlug("digitalocean")).toBe("digitalocean")
    expect(providerIconSlug("hetzner")).toBe("hetzner")
    expect(providerIconSlug("azure")).toBe("azure")
    expect(providerIconSlug("gcp")).toBe("googlecloud")
  })
  it("returns undefined for unknown / absent", () => {
    expect(providerIconSlug("linode")).toBeUndefined()
    expect(providerIconSlug(null)).toBeUndefined()
  })
})

describe("hasBrandIcon", () => {
  it("is true for simple-icons and custom glyphs", () => {
    expect(hasBrandIcon("ubuntu")).toBe(true) // simple-icons
    expect(hasBrandIcon("cpanel")).toBe(true) // simple-icons
    expect(hasBrandIcon("googlecloud")).toBe(true)
    expect(hasBrandIcon("windows")).toBe(true) // custom
    expect(hasBrandIcon("cyberpanel")).toBe(true) // custom
    expect(hasBrandIcon("directadmin")).toBe(true) // custom
    expect(hasBrandIcon("aws")).toBe(true) // custom
    expect(hasBrandIcon("azure")).toBe(true) // custom
  })
  it("is false for unknown / absent", () => {
    expect(hasBrandIcon("beos")).toBe(false)
    expect(hasBrandIcon(undefined)).toBe(false)
    expect(hasBrandIcon(null)).toBe(false)
  })
  it("every panel and provider slug we use resolves to a glyph", () => {
    for (const p of ["cyberpanel", "cpanel", "plesk", "directadmin"]) expect(hasBrandIcon(p)).toBe(true)
    for (const p of ["aws", "digitalocean", "hetzner", "gcp", "azure"]) expect(hasBrandIcon(providerIconSlug(p))).toBe(true)
  })
})

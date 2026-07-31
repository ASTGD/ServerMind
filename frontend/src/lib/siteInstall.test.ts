import { describe, expect, it } from "vitest"
import { canInstallOnto, wasCreatedHere } from "./siteInstall"
import type { Site } from "@/api/sites"

/**
 * Who may have something installed onto them.
 *
 * Getting this wrong in one direction hides a button on a site that could use it. In the
 * other it offers to install WordPress over somebody's live website — so the cases below
 * are mostly the second kind.
 */

function site(over: Partial<Site> = {}): Site {
  return {
    id: "s1", domain: "shop.example.com", server_id: "srv1",
    source: "manual", app_type: "static", requested_type: "static",
    status: "live", is_present: true, has_ssl: false,
    ...over,
  } as Site
}

describe("what can be installed onto", () => {
  it("allows an empty site ServerAlly just created", () => {
    expect(canInstallOnto(site())).toBe(true)
  })

  it("refuses a site that is still being built", () => {
    // Two installers writing the same vhost at once is the one thing worth preventing here.
    expect(canInstallOnto(site({ status: "installing" }))).toBe(false)
  })

  it("refuses a site whose last install failed", () => {
    // Its folder may be half-made. Remove it and start again rather than layering on top.
    expect(canInstallOnto(site({ status: "failed" }))).toBe(false)
  })

  it("refuses a site that already has something installed", () => {
    expect(canInstallOnto(site({ requested_type: "wordpress", app_type: "wordpress" }))).toBe(false)
    expect(canInstallOnto(site({ requested_type: "app", app_type: "unknown" }))).toBe(false)
  })
})

describe("sites that were already on the server", () => {
  it("refuses a discovered WordPress site", () => {
    // Someone connects a server that has been running WordPress for two years.
    const found = site({
      source: "nginx", app_type: "wordpress", app_version: "6.7", requested_type: null,
    })
    expect(canInstallOnto(found)).toBe(false)
    expect(wasCreatedHere(found)).toBe(false)
  })

  it("refuses a discovered site we could NOT identify", () => {
    // The dangerous one. Discovery labels anything that is not WordPress or Laravel as
    // "unknown" — a hand-built PHP app, a plain HTML site. Judging emptiness by app_type
    // treats every one of those as a blank site and offers to overwrite it.
    const found = site({ source: "nginx", app_type: "unknown", requested_type: null })
    expect(canInstallOnto(found)).toBe(false)
  })

  it("refuses every site found on a CyberPanel server", () => {
    // A bare-metal box with a panel and dozens of sites: each one is somebody's live
    // website, and none of them were made by us.
    for (const app of ["wordpress", "laravel", "unknown", "static"]) {
      const found = site({ source: "cyberpanel", app_type: app, requested_type: null })
      expect(canInstallOnto(found)).toBe(false)
    }
  })

  it("does not mistake a found site for one of ours just because it looks empty", () => {
    const found = site({ source: "openlitespeed", app_type: "static", requested_type: null })
    expect(canInstallOnto(found)).toBe(false)
    expect(wasCreatedHere(found)).toBe(false)
  })
})

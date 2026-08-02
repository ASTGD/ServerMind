import { describe, expect, it } from "vitest"
import type { Site } from "@/api/sites"
import { siteLooksBroken, siteProblem, siteState } from "./siteStatus"

function site(over: Partial<Site> = {}): Site {
  return {
    id: "1", domain: "shop.example.com", aliases: [], server_id: "s1",
    server_name: "Web1", doc_root: null, source: "manual", app_type: "php",
    app_version: null, has_ssl: false, is_present: true, status: "live",
    install_error: null, first_seen: null, last_seen: null, uptime: null,
    ...over,
  }
}

const dnsDown = {
  monitor_id: "m", status: "down", last_checked: null, response_ms: null,
  error: "The domain name could not be resolved — check the site's DNS.",
  cert_days_left: null, cert_state: null,
}

describe("siteState", () => {
  it("knows a site that is still being built", () => {
    expect(siteState(site({ status: "installing" }))).toBe("installing")
  })

  it("knows a site whose install failed", () => {
    expect(siteState(site({ status: "failed" }))).toBe("failed")
  })

  it("does not call a site being built 'missing'", () => {
    // A scan has not seen it yet because it does not exist YET. Calling that missing is
    // how a site gets buried halfway through its own install.
    expect(siteState(site({ status: "installing", is_present: false }))).toBe("installing")
  })

  it("reports a finished site that is no longer on the server", () => {
    expect(siteState(site({ status: "live", is_present: false }))).toBe("absent")
  })
})

describe("siteProblem", () => {
  it("puts the install failure ahead of what the monitor says", () => {
    // The exact bug: a failed install was reported as a DNS problem, because a monitor
    // was watching a domain for a site that was never built.
    const s = site({
      status: "failed",
      install_error: "no web server is running on this server. Set the server up first",
      uptime: dnsDown,
    })
    expect(siteProblem(s)).toBe(
      "no web server is running on this server. Set the server up first")
  })

  it("still says something when the install failed without a reason", () => {
    expect(siteProblem(site({ status: "failed" }))).toBe("The setup did not finish.")
  })

  it("stays quiet while a site is being built", () => {
    // The monitor cannot reach a site that does not exist yet; saying so is noise.
    expect(siteProblem(site({ status: "installing", uptime: dnsDown }))).toBeNull()
  })

  it("reports the monitor's reason for a real site that is down", () => {
    expect(siteProblem(site({ uptime: dnsDown }))).toBe(dnsDown.error)
  })

  it("does not repeat a frozen reason for a site that is no longer there", () => {
    // Its check is paused once we know it is gone, so the monitor's last words are stale
    // and the "No longer found" chip already carries the news.
    expect(siteProblem(site({ is_present: false, uptime: dnsDown }))).toBeNull()
  })

  it("says nothing about a healthy site", () => {
    expect(siteProblem(site())).toBeNull()
    expect(siteProblem(site({ uptime: { ...dnsDown, status: "up", error: null } }))).toBeNull()
  })
})

describe("siteLooksBroken", () => {
  it("does not mark a site being built as broken", () => {
    expect(siteLooksBroken(site({ status: "installing", uptime: dnsDown }))).toBe(false)
  })

  it("marks a failed install as broken even with no monitor", () => {
    expect(siteLooksBroken(site({ status: "failed" }))).toBe(true)
  })

  it("marks a live site whose monitor says down", () => {
    expect(siteLooksBroken(site({ uptime: dnsDown }))).toBe(true)
  })

  it("leaves a healthy site alone", () => {
    expect(siteLooksBroken(site())).toBe(false)
  })
})

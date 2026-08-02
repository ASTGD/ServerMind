import { describe, expect, it } from "vitest"
import type { Site } from "@/api/sites"
import {
  siteDetail, siteLooksBroken, siteProblem, siteState, siteStatusLabel, siteTone,
} from "./siteStatus"

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
  // Classified server-side. `ever_up: true` means it WAS working, so this is an outage.
  unresolved: true, ever_up: true,
}

/** The same words from the checker, for a domain that has never answered. */
const neverPointed = { ...dnsDown, ever_up: false }

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


describe("a domain that was never pointed here", () => {
  it("is not called down, because it was never up", () => {
    // Every site is in this state the moment it is created. Calling it down makes a
    // brand-new site look broken before its owner has touched their DNS.
    expect(siteState(site({ uptime: neverPointed }))).toBe("unpointed")
    expect(siteLooksBroken(site({ uptime: neverPointed }))).toBe(false)
  })

  it("says what to do rather than what failed", () => {
    const said = siteProblem(site({ uptime: neverPointed })) ?? ""
    expect(said).toContain("not pointed anywhere yet")
    // The checker's own words are about DNS resolution, which reads as a fault.
    expect(said).not.toContain("could not be resolved")
  })

  it("still calls it down when the site WAS working", () => {
    // Same words from the checker, completely different situation: a live site whose DNS
    // was deleted is an emergency, and must not be filed under "not set up yet".
    const s = site({ uptime: dnsDown })
    expect(siteState(s)).toBe("normal")
    expect(siteLooksBroken(s)).toBe(true)
    expect(siteProblem(s)).toBe(dnsDown.error)
  })

  it("does not claim it of a site that is down for any other reason", () => {
    const http500 = { ...dnsDown, unresolved: false, ever_up: false,
                      error: "Returned HTTP 500 (expected 200)." }
    expect(siteState(site({ uptime: http500 }))).toBe("normal")
    expect(siteLooksBroken(site({ uptime: http500 }))).toBe(true)
  })

  it("leaves an older answer alone when the server has not told us yet", () => {
    // `ever_up` absent — an older payload. Guessing "never pointed" from silence would
    // quietly downgrade a real outage, so the strict check is on false, not on falsy.
    const legacy = { ...dnsDown, ever_up: undefined }
    expect(siteState(site({ uptime: legacy }))).toBe("normal")
  })

  it("a failed install still outranks it", () => {
    const s = site({ status: "failed", install_error: "no web server is running",
                     uptime: neverPointed })
    expect(siteState(s)).toBe("failed")
    expect(siteProblem(s)).toBe("no web server is running")
  })
})

describe("the status a list can show", () => {
  it("says something exact for every state", () => {
    expect(siteStatusLabel(site({ uptime: { ...dnsDown, status: "up", error: null } }))).toBe("Up")
    expect(siteStatusLabel(site({ uptime: dnsDown }))).toBe("Down")
    expect(siteStatusLabel(site({ uptime: neverPointed }))).toBe("Not pointed here yet")
    expect(siteStatusLabel(site({ status: "failed" }))).toBe("Setup failed")
    expect(siteStatusLabel(site({ status: "installing" }))).toBe("Setting up")
    expect(siteStatusLabel(site({ is_present: false }))).toBe("No longer found")
  })

  it("does not call an unchecked site healthy", () => {
    // A row with no red on it could otherwise mean "fine", "never checked" or "no idea".
    expect(siteStatusLabel(site({ uptime: null }))).toBe("Not checked")
  })

  it("colours only a real fault red", () => {
    expect(siteTone(site({ uptime: { ...dnsDown, status: "up", error: null } }))).toBe("good")
    expect(siteTone(site({ uptime: dnsDown }))).toBe("bad")
    expect(siteTone(site({ status: "failed" }))).toBe("bad")
    expect(siteTone(site({ uptime: neverPointed }))).toBe("calm")
    expect(siteTone(site({ status: "installing" }))).toBe("calm")
    expect(siteTone(site({ uptime: null }))).toBe("calm")
  })

  it("does not repeat the status as a sentence underneath it", () => {
    // "Not pointed here yet" over "this domain is not pointed anywhere yet" is the same
    // fact twice, and that is what makes a list tall and hard to scan.
    expect(siteDetail(site({ uptime: neverPointed }))).toBeNull()
    expect(siteDetail(site({ is_present: false }))).toBeNull()
  })

  it("keeps the sentence when it says more than the status does", () => {
    expect(siteDetail(site({ uptime: dnsDown }))).toBe(dnsDown.error)
    expect(siteDetail(site({ status: "failed", install_error: "no web server" })))
      .toBe("no web server")
  })
})

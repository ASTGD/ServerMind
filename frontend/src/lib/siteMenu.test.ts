import { describe, expect, it } from "vitest"
import { menuForSite } from "./siteMenu"
import type { SiteDetail } from "@/api/sites"

/**
 * A site's menu decides what its owner believes they can do with it. Offering a section
 * that cannot work here is worse than omitting it — by the time it declines, they have
 * already decided to trust it.
 */
function site(over: Partial<SiteDetail> = {}, server: Partial<SiteDetail["server"]> = {}): SiteDetail {
  return {
    id: "s1", domain: "shop.example.com", source: "manual",
    app_type: "wordpress", requested_type: "wordpress", status: "live",
    has_ssl: false, is_present: true,
    server: { id: "srv1", name: "Web One", connection_type: "ssh", panel_type: null, ...server },
    ...over,
  } as SiteDetail
}

const paths = (s: SiteDetail) => menuForSite(s).map((i) => i.path)

describe("a site's own menu", () => {
  it("gives a normal site on a Linux server the full set", () => {
    const p = paths(site())
    expect(p).toContain("")          // overview
    expect(p).toContain("https")
    expect(p).toContain("logs")
    expect(p).toContain("cron")
    expect(p).toContain("settings")
  })

  it("hides HTTPS on a control-panel server, which issues its own", () => {
    // A certificate we obtained behind the panel's back would never be renewed by it.
    const p = paths(site({}, { panel_type: "cyberpanel" }))
    expect(p).not.toContain("https")
    expect(p).toContain("")          // the site still has a page
    expect(p).toContain("settings")
  })

  it("hides everything that needs the machine when there is no shell", () => {
    // A site on a panel reached only by its API: we cannot read its log files or its crontab.
    const p = paths(site({}, { connection_type: "hosting", panel_type: "cpanel" }))
    expect(p).not.toContain("logs")
    expect(p).not.toContain("cron")
    expect(p).not.toContain("https")
  })

  it("never offers a section that has nowhere to go", () => {
    // Every path in the menu must have a route behind it. A row that leads nowhere is the
    // same broken promise as one that leads somewhere that cannot work.
    const ROUTED = new Set(["", "https", "logs", "cron", "uptime", "settings"])
    for (const s of [site(), site({ source: "nginx", requested_type: null }),
                     site({}, { panel_type: "cyberpanel" })]) {
      for (const p of paths(s)) expect(ROUTED.has(p)).toBe(true)
    }
  })

  it("still gives a discovered site a page and its logs", () => {
    // We did not build it, but it is on a server we can reach — watching it is the job.
    const found = site({ source: "nginx", requested_type: null })
    expect(paths(found)).toContain("")
    expect(paths(found)).toContain("logs")
    expect(paths(found)).toContain("settings")
  })

  it("never offers a section twice", () => {
    const p = paths(site())
    expect(new Set(p).size).toBe(p.length)
  })
})

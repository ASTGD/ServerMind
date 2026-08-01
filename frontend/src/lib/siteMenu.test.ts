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
    const ROUTED = new Set(["", "app", "https", "logs", "cron", "uptime", "settings"])
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

describe("the section for the application running on the site", () => {
  it("is named after the application, not called 'App'", () => {
    // Someone with a WordPress site is looking for the word WordPress.
    expect(menuForSite(site()).map((i) => i.label)).toContain("WordPress")
  })

  it("sits straight after Overview, because it is what people came for", () => {
    expect(paths(site()).slice(0, 2)).toEqual(["", "app"])
  })

  it("is absent for an application we have no tools for", () => {
    // Absent, not disabled: a permanently dead row implies the feature exists and is
    // merely switched off. Mirrors app_registry on the server, which actually decides.
    for (const app_type of ["laravel", "php", "static", "unknown", ""]) {
      expect(paths(site({ app_type }))).not.toContain("app")
    }
  })

  it("is absent when we have no shell, because it runs a command-line tool", () => {
    const noShell = site({}, { connection_type: "hosting", panel_type: "cpanel" })
    expect(paths(noShell)).not.toContain("app")
  })

  it("appears on a site somebody installed WordPress onto by hand", () => {
    // Discovery sets app_type from what it finds, so we did not have to build the site.
    const found = site({ source: "nginx", requested_type: null, app_type: "wordpress" })
    expect(paths(found)).toContain("app")
  })
})

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
    const ROUTED = new Set(["", "app", "https", "php", "redirects", "logs", "cron",
                            "daemons", "database", "deploy", "manage", "uptime", "settings"])
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

  it("tells the two kinds of job apart by name", () => {
    // One runs at a time and finishes; the other runs continuously. "Background jobs"
    // beside "Scheduled jobs" would not tell anyone which is which.
    const labels = menuForSite(site()).map((i) => i.label)
    expect(labels).toContain("Scheduled jobs")
    expect(labels).toContain("Always running")
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
    for (const app_type of ["static", "unknown", "", "ghost", "nextcloud"]) {
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

describe("the registry now covers three applications", () => {
  it("names Laravel and PHP after themselves too", () => {
    expect(menuForSite(site({ app_type: "laravel" })).map((i) => i.label)).toContain("Laravel")
    expect(menuForSite(site({ app_type: "php" })).map((i) => i.label))
      .toContain("PHP settings")
  })

  it("still gives a folder of files nothing to manage", () => {
    // `static` has no application; `unknown` means the scan could not tell, and a section
    // for it would be guessing at what is there.
    for (const app_type of ["static", "unknown", ""]) {
      expect(paths(site({ app_type }))).not.toContain("app")
    }
  })

  it("separates the version this site runs from the settings it runs under", () => {
    // Two different questions, and for a while only one of them had an answer here. The
    // app panel reports the limits THIS site runs under — per-pool, and what breaks an
    // upload. `php` chooses which version serves it, which every PHP site needs and not
    // only the ones whose application IS php.
    const p = paths(site({ app_type: "php" }))
    expect(p).toContain("app")
    expect(p).toContain("php")

    const labels = menuForSite(site({ app_type: "php" })).map((i) => i.label)
    expect(labels).toContain("PHP settings")
    expect(labels).toContain("PHP version")
    // Two rows both called "PHP" is the collision that made the panel row get named after
    // the panel. Whatever they are called, they must not be called the same thing.
    expect(new Set(labels).size).toBe(labels.length)
  })

  it("offers the version switch to a WordPress or Laravel site too", () => {
    for (const app_type of ["wordpress", "laravel"]) {
      expect(paths(site({ app_type }))).toContain("php")
    }
  })

  it("leaves a panel's sites to the panel", () => {
    // A panel decides its own sites' PHP version and rewrites the vhost on its own
    // schedule, so a change made behind its back is silently reverted later.
    expect(paths(site({ app_type: "php" }, { panel_type: "cyberpanel" }))).not.toContain("php")
  })
})

import { describe, expect, it } from "vitest"
import {
  actionsFor, capabilitiesOf, installerOptionsFor, menuFor, MENU,
  type ServerRoleName,
} from "./assetMenu"
import type { Server } from "@/types"

/**
 * The menu decides what a customer believes their asset can do. Getting it wrong in one
 * direction offers a section that cannot possibly work; in the other it hides one that
 * does. Both are worse than a plain list, so the rules are pinned here.
 */

function asset(over: Partial<Server> = {}): Server {
  return {
    id: "a1", name: "box", host: "10.0.0.1", port: 22, username: "root",
    connection_type: "ssh", status: "online",
    ...over,
  } as Server
}

const labels = (s: Server) => menuFor(s).map((i) => i.label)
/** A section's stable identity. Labels are customer-facing wording and change. */
const paths = (s: Server) => menuFor(s).map((i) => i.path)

describe("what an asset can do", () => {
  it("gives a plain Linux server the full set", () => {
    // Once it has said ServerAlly runs it — Sites is that answer made visible.
    const items = menuFor(asset(), { role: "serverally" }).map((i) => i.label)
    for (const expected of ["Sites", "Files", "Security", "Firewall & keys", "Backups", "Logs", "Settings"]) {
      expect(items).toContain(expected)
    }
  })

  it("offers no control-panel section until a panel is actually there", () => {
    // Asserted on the path, not the label: the label is named after the panel and is
    // meant to change, while the section's identity is not.
    expect(paths(asset())).not.toContain("hosting")
    expect(paths(asset({ panel_type: "cyberpanel" }))).toContain("hosting")
  })

  it("gives a panel server ONE list of websites, the panel's own", () => {
    // This reverses an earlier decision, deliberately. The two were kept apart on the
    // grounds that Sites is what the machine serves and Control panel is the panel's own
    // records — true, but two menu rows that both list websites is a distinction the
    // owner has to hold in their head on every visit. The panel's page is where its sites
    // are created, deleted and given certificates, so it wins on its own server.
    //
    // What that costs, and it is real: our Sites view carries uptime and certificate
    // expiry, which the panel's list does not. Both live on the fleet-wide Sites page,
    // which is also how the per-site pages stay reachable.
    const items = paths(asset({ panel_type: "cyberpanel" }))
    expect(items).not.toContain("sites")
    expect(items).toContain("hosting")
  })

  it("treats a panel reached over SSH as a panel", () => {
    // The common real case: CyberPanel installed on a box we also have SSH to. It is both,
    // and a per-type list would have to pick one.
    const items = labels(asset({ connection_type: "ssh", panel_type: "cyberpanel" }))
    expect(items).toContain("CyberPanel")
    expect(items).toContain("Files")
    expect(items).toContain("Firewall & keys")
  })

  it("gives a hosting-only account its panel but not a Linux firewall", () => {
    const items = labels(asset({ connection_type: "hosting", panel_type: "cpanel" }))
    expect(items).toContain("cPanel")
    expect(items).not.toContain("Firewall & keys")
    expect(items).not.toContain("Files") // no SFTP to an API-only panel
  })
})

describe("an RDP asset never pretends to be more than it is", () => {
  const rdp = asset({ connection_type: "rdp", port: 3389 })

  it("offers only what a desktop connection can support", () => {
    // There is no command channel at all, so every command-backed section would fail.
    // Overview survives because it is the only home this asset has.
    expect(labels(rdp)).toEqual(["Overview", "Settings"])
  })

  it("offers a desktop and nothing that needs a shell", () => {
    expect(actionsFor(rdp)).toEqual({ terminal: false, desktop: true, ally: false })
  })
})

describe("a Windows server over WinRM", () => {
  const win = asset({ connection_type: "winrm", port: 5985 })

  it("keeps the sections that have a Windows path", () => {
    expect(labels(win)).toContain("Security")
    expect(labels(win)).toContain("Scheduled tasks")
  })

  it("hides the ones that are Linux-only in the code, not merely untested", () => {
    // Files is SFTP; Logs reads Linux paths; Backups shells out to tar and mysqldump; the
    // firewall drives ufw/firewalld; Services reads systemd; site discovery and deploys go
    // over SFTP. None of these have a Windows branch.
    for (const linuxOnly of [
      "Files", "Logs", "Backups", "Firewall & keys", "Installed",
      "Sites", "Services", "Deployments", "PHP",
    ]) {
      expect(labels(win)).not.toContain(linuxOnly)
    }
  })

  it("keeps Monitoring, which does collect Windows metrics", () => {
    expect(labels(win)).toContain("Monitoring")
  })

  it("can open a desktop but not the interactive terminal", () => {
    // The terminal websocket refuses anything that is not SSH, so offering it would open
    // a session that closes immediately.
    expect(actionsFor(win)).toEqual({ terminal: false, desktop: true, ally: true })
  })
})

describe("capabilities", () => {
  it("marks an imported instance as cloud-backed", () => {
    expect(capabilitiesOf(asset({ cloud_account_id: "c1" })).has("cloud")).toBe(true)
    expect(capabilitiesOf(asset()).has("cloud")).toBe(false)
  })

  it("never gives a shell to something with no command channel", () => {
    expect(capabilitiesOf(asset({ connection_type: "rdp" })).has("shell")).toBe(false)
    expect(capabilitiesOf(asset({ connection_type: "hosting" })).has("shell")).toBe(false)
  })
})

describe("the registry itself", () => {
  it("leads with Start here, the one thing that has to happen first", () => {
    expect(MENU[0].path).toBe("")
    expect(MENU[0].label).toBe("Start here")
  })

  it("names the home page for what it actually is on that asset", () => {
    // A Linux server is being asked a question; a Windows or RDP box never will be, so
    // promising it a choice would be a row that leads to a page it does not have.
    const label = (a: Server) => menuFor(a).find((i) => i.path === "")?.label
    expect(label(asset())).toBe("Start here")
    for (const c of ["winrm", "rdp"] as const) {
      expect(label(asset({ connection_type: c }))).toBe("Overview")
    }
    // A hosting account IS its panel — there is no machine of ours to overview, so its
    // home is the panel's own page rather than a row that would summarise nothing.
    const hosting = asset({ connection_type: "hosting", panel_type: "cpanel" })
    expect(label(hosting)).toBeUndefined()
    expect(paths(hosting)).toContain("hosting")
  })

  it("shows only the door the answer opened", () => {
    // The whole rule in one test. Unanswered: the question and nothing about websites,
    // because Sites would be a way to walk straight past a near-irreversible decision.
    // Answered our way: Sites, question retired. Answered with a panel: the panel's own
    // section, which IS its site list — two rows both listing websites is the confusion
    // this removes.
    const paths = (a: Server, role?: ServerRoleName) =>
      menuFor(a, { role }).map((i) => i.path)

    expect(paths(asset(), "undecided")).toContain("")
    expect(paths(asset(), "undecided")).not.toContain("sites")

    expect(paths(asset(), "serverally")).toContain("sites")
    expect(paths(asset(), "serverally")).not.toContain("")

    const panel = asset({ panel_type: "cyberpanel" })
    expect(paths(panel, "panel")).toContain("hosting")
    expect(paths(panel, "panel")).not.toContain("sites")
    expect(paths(panel, "panel")).not.toContain("")
  })

  it("keeps the question up while the answer is still loading", () => {
    // The menu draws before the role query resolves. Hiding the fork by default would
    // flash it away on the one server that has to see it.
    expect(menuFor(asset()).map((i) => i.path)).toContain("")
    expect(menuFor(asset(), { role: undefined }).map((i) => i.path)).toContain("")
  })

  it("keeps Overview forever on an asset that never faces the question", () => {
    // Windows and Remote Desktop cannot host anything, so Overview is the only page they
    // have — no answer to the question may take it away from them.
    for (const c of ["winrm", "rdp"] as const) {
      for (const role of ["undecided", "serverally", "panel"] as const) {
        expect(menuFor(asset({ connection_type: c }), { role }).map((i) => i.label))
          .toContain("Overview")
      }
    }
  })

  it("never leaves an asset with nowhere to land", () => {
    // Every asset must have a home, and there are exactly three: the question while it is
    // open, Sites once ServerAlly runs the machine, the panel's own page when a panel
    // does. A combination that lands on none of them is an asset you cannot open.
    const homes = ["", "sites", "hosting"]
    const cases: [Server, ServerRoleName][] = [
      [asset(), "undecided"],
      [asset(), "serverally"],
      [asset({ panel_type: "cyberpanel" }), "panel"],
      [asset({ connection_type: "hosting", panel_type: "cpanel" }), undefined],
      [asset({ connection_type: "winrm" }), undefined],
      [asset({ connection_type: "rdp" }), undefined],
    ]
    for (const [a, role] of cases) {
      const items = menuFor(a, { role }).map((i) => i.path)
      expect(items.some((p) => homes.includes(p))).toBe(true)
    }
  })

  it("has no duplicate destinations", () => {
    const paths = MENU.map((i) => i.path)
    expect(new Set(paths).size).toBe(paths.length)
  })

  it("shows every asset at least somewhere to land", () => {
    for (const c of ["ssh", "winrm", "rdp", "hosting"] as const) {
      expect(menuFor(asset({ connection_type: c })).length).toBeGreaterThan(0)
    }
  })
})

describe("which 'add a website' doors an asset gets", () => {
  it("gives a Linux server the PHP section, and a Windows box none", () => {
    // PHP management reads and rewrites nginx/Apache configs over SFTP.
    expect(labels(asset())).toContain("PHP")
    expect(labels(asset({ connection_type: "winrm" }))).not.toContain("PHP")
  })

  it("offers the direct installers on a plain Linux server", () => {
    const d = installerOptionsFor(asset())
    expect(d).toEqual({ direct: true, panel: false, ally: true })
  })

  it("never offers a direct installer on a panel server", () => {
    // They write a web-server config, which the panel owns — so they refuse at runtime.
    // Offering a button that then says no is worse than not offering it: the customer has
    // already decided to trust it by the time it declines.
    const d = installerOptionsFor(asset({ panel_type: "cyberpanel" }))
    expect(d.direct).toBe(false)
    expect(d.panel).toBe(true)
    expect(d.ally).toBe(true)
  })

  it("sends a hosting-only account to its panel and nowhere else", () => {
    const d = installerOptionsFor(asset({ connection_type: "hosting", panel_type: "cpanel" }))
    expect(d).toEqual({ direct: false, panel: true, ally: false })
  })

  it("offers nothing at all on an asset with no command channel", () => {
    // An RDP box cannot host, so every door would be a dead end.
    expect(installerOptionsFor(asset({ connection_type: "rdp" })))
      .toEqual({ direct: false, panel: false, ally: false })
  })

  it("does not offer file-writing installers to a Windows box", () => {
    // No SFTP: the installers place files and write an nginx or Apache config.
    const d = installerOptionsFor(asset({ connection_type: "winrm" }))
    expect(d.direct).toBe(false)
    expect(d.ally).toBe(true)
  })
})

describe("a section a control panel owns itself", () => {
  it("hides PHP on a panel server", () => {
    // On a CyberPanel box PHP is lsphp with the panel's own vhost layout and its own
    // switcher. Our page read a server running 77 PHP sites and reported "no PHP websites
    // found" — honest, but a menu item promising something it cannot deliver.
    expect(labels(asset({ panel_type: "cyberpanel" }))).not.toContain("PHP")
    expect(labels(asset({ connection_type: "hosting", panel_type: "cpanel" }))).not.toContain("PHP")
  })

  it("keeps PHP on a plain server, which is where it works", () => {
    expect(labels(asset())).toContain("PHP")
  })

  it("still shows the panel's own section there instead", () => {
    expect(paths(asset({ panel_type: "cyberpanel" }))).toContain("hosting")
  })
})

describe("databases and cron", () => {
  it("offers both on a plain Linux server", () => {
    const paths = menuFor(asset()).map((i) => i.path)
    expect(paths).toContain("databases")
    expect(paths).toContain("cron")
  })

  it("hides Databases on a control panel, which owns its own", () => {
    // Same reasoning as PHP: a panel manages databases through its own screens, and a
    // database we created behind its back would be invisible there.
    const paths = menuFor(asset({ panel_type: "cyberpanel" })).map((i) => i.path)
    expect(paths).not.toContain("databases")
    expect(paths).toContain("hosting")
  })

  it("keeps Cron jobs on a control panel, because the crontab is still the server's", () => {
    // Unlike databases, a panel does not own the machine's crontab — Laravel jobs and
    // backup scripts live there regardless of which panel is installed.
    expect(menuFor(asset({ panel_type: "cyberpanel" })).map((i) => i.path)).toContain("cron")
  })

  it("offers neither on a Windows box", () => {
    // Both are Linux tools: mysql/psql over a unix socket, and crontab.
    const paths = menuFor(asset({ connection_type: "winrm", port: 5985 })).map((i) => i.path)
    expect(paths).not.toContain("databases")
    expect(paths).not.toContain("cron")
  })

  it("offers neither on an RDP-only box", () => {
    const paths = menuFor(asset({ connection_type: "rdp", port: 3389 })).map((i) => i.path)
    expect(paths).not.toContain("databases")
    expect(paths).not.toContain("cron")
  })
})

describe("the panel section is named after the panel", () => {
  it("says CyberPanel on a CyberPanel box, not 'Control panel'", () => {
    const l = labels(asset({ panel_type: "cyberpanel" }))
    expect(l).toContain("CyberPanel")
    expect(l).not.toContain("Control panel")
  })

  it("names cPanel and Plesk too", () => {
    expect(labels(asset({ panel_type: "cpanel" }))).toContain("cPanel")
    expect(labels(asset({ panel_type: "plesk" }))).toContain("Plesk")
  })

  it("keeps the generic label for a panel we have no name for", () => {
    // Better a slightly vague heading than a raw database value shown to a customer.
    const l = labels(asset({ panel_type: "something-new" }))
    expect(l).toContain("Control panel")
  })

  it("still shows nothing panel-ish on a server with no panel", () => {
    const l = labels(asset({ panel_type: null }))
    expect(l).not.toContain("Control panel")
    expect(l).not.toContain("CyberPanel")
  })
})

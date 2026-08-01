import { describe, expect, it } from "vitest"
import {
  actionsFor, capabilitiesOf, homePathFor, installerOptionsFor, menuFor, MENU,
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
    const items = labels(asset())
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

  it("keeps Sites and Control panel as separate ideas", () => {
    // They sound alike and are not. Sites is what the machine actually serves, read from
    // its own web server config; Control panel is the panel's own records and operations.
    // A CyberPanel box legitimately has both, and naming the second one "Websites" made
    // two items compete for one meaning.
    const items = paths(asset({ panel_type: "cyberpanel" }))
    expect(items).toContain("sites")
    expect(items).toContain("hosting")
    expect(items).not.toContain("Websites")
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
  it("leads with Sites, because a server exists to serve something", () => {
    expect(MENU[0].path).toBe("sites")
  })

  it("keeps Overview as the FALLBACK home, never a duplicate section", () => {
    // Everything on Overview is a preview of another section: live metrics duplicate
    // Monitoring, the services panel duplicates Services, its Installed card duplicates
    // Installed. So on an asset that has Sites it is pure duplication and is dropped; on an
    // asset with no Sites it is the only landing place there is and must stay.
    expect(labels(asset())).not.toContain("Overview")                       // Linux: has Sites
    expect(labels(asset({ connection_type: "rdp" }))).toContain("Overview") // RDP: nothing else
    expect(labels(asset({ connection_type: "winrm" }))).toContain("Overview")
    expect(labels(asset({ connection_type: "hosting" }))).toContain("Overview")
  })

  it("never leaves an asset with nowhere to land", () => {
    // The whole point of the fallback: every asset must have a home page.
    for (const c of ["ssh", "winrm", "rdp", "hosting"] as const) {
      const items = labels(asset({ connection_type: c }))
      expect(items.includes("Sites") || items.includes("Overview")).toBe(true)
    }
  })

  it("sends anything that can host to Sites, and everything else to Overview", () => {
    expect(homePathFor(asset())).toBe("sites")
    expect(homePathFor(asset({ connection_type: "rdp" }))).toBe("")
    expect(homePathFor(asset({ connection_type: "winrm" }))).toBe("")
    expect(homePathFor(asset({ connection_type: "hosting" }))).toBe("")
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

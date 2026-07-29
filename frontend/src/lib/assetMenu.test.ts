import { describe, expect, it } from "vitest"
import { actionsFor, capabilitiesOf, menuFor, MENU } from "./assetMenu"
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

describe("what an asset can do", () => {
  it("gives a plain Linux server the full set", () => {
    const items = labels(asset())
    for (const expected of ["Overview", "Files", "Security", "Firewall & keys", "Backups", "Logs", "Settings"]) {
      expect(items).toContain(expected)
    }
  })

  it("offers no websites section until a panel is actually there", () => {
    expect(labels(asset())).not.toContain("Websites")
    expect(labels(asset({ panel_type: "cyberpanel" }))).toContain("Websites")
  })

  it("treats a panel reached over SSH as a panel", () => {
    // The common real case: CyberPanel installed on a box we also have SSH to. It is both,
    // and a per-type list would have to pick one.
    const items = labels(asset({ connection_type: "ssh", panel_type: "cyberpanel" }))
    expect(items).toContain("Websites")
    expect(items).toContain("Files")
    expect(items).toContain("Firewall & keys")
  })

  it("gives a hosting-only account its panel but not a Linux firewall", () => {
    const items = labels(asset({ connection_type: "hosting", panel_type: "cpanel" }))
    expect(items).toContain("Websites")
    expect(items).not.toContain("Firewall & keys")
    expect(items).not.toContain("Files") // no SFTP to an API-only panel
  })
})

describe("an RDP asset never pretends to be more than it is", () => {
  const rdp = asset({ connection_type: "rdp", port: 3389 })

  it("offers only what a desktop connection can support", () => {
    // There is no command channel at all, so every command-backed section would fail.
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
    // Files is SFTP; Logs reads Linux paths; Backups shells out to tar and mysqldump;
    // the firewall section drives ufw/firewalld. None of these have a Windows branch.
    for (const linuxOnly of ["Files", "Logs", "Backups", "Firewall & keys", "Installed"]) {
      expect(labels(win)).not.toContain(linuxOnly)
    }
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
  it("keeps Overview first and always available", () => {
    expect(MENU[0].path).toBe("")
    expect(MENU[0].needs).toBeUndefined()
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

import { describe, expect, it } from "vitest"
import {
  ADD_TILES, ASSET_FILTERS, ASSET_GROUPS, WINDOWS_METHODS,
  assetZones, availableFilters, groupFor, groupForServer,
} from "./assetGroups"
import type { CloudAccount } from "@/api/cloud"
import type { Server } from "@/types"

function account(over: Partial<CloudAccount> = {}): CloudAccount {
  return { id: "acc-1", provider: "aws", label: "ceo@astgd.com", created_at: "", ...over }
}

/**
 * The Assets page answers three different questions, and the old registry answered all three
 * with one list — which is why the list kept growing. These tests hold the three apart:
 * a tile is a CHOICE, a group is DERIVED, and a filter SLICES ACROSS the groups.
 */
function srv(over: Partial<Server> = {}): Server {
  return {
    id: "s1", name: "Web One", host: "10.0.0.1", port: 22, username: "root",
    auth_type: "password", connection_type: "ssh", panel_type: null, category: null,
    os_type: "ubuntu", os_version: "24.04", arch: "x86_64", shell: "bash",
    status: "online", tags: null, notes: null, last_seen: null, created_at: "",
    ...over,
  } as Server
}

describe("what you can add", () => {
  it("offers three tiles — the six were one thing wearing several hats", () => {
    expect(ADD_TILES.map((t) => t.id)).toEqual(["server", "windows", "cloud"])
  })

  it("has no hosting-panel tile, because that route cannot do the job", () => {
    // CyberPanel's admin API has no website, database or SSL endpoint — the reliable
    // surface is its CLI over SSH, which a Server with a panel already gets. A tile that
    // leads anywhere else is a trap, so it must not exist rather than exist and decline.
    expect(ADD_TILES.some((t) => t.connectionType === "hosting")).toBe(false)
  })

  it("every direct-add tile says how it connects", () => {
    // A tile with no transport and no cloud flow could be picked and then do nothing.
    for (const tile of ADD_TILES) {
      expect(Boolean(tile.connectionType) || Boolean(tile.cloudFlow)).toBe(true)
    }
  })

  it("keeps the two Windows transports even though the choice merged", () => {
    // Merge the choice, not the types: RDP has no command channel, so a box added that way
    // must still be treated differently everywhere downstream.
    expect(WINDOWS_METHODS.map((m) => m.id)).toEqual(["rdp", "winrm"])
    expect(WINDOWS_METHODS.map((m) => m.port)).toEqual([3389, 5985])
  })
})

describe("where an asset lives", () => {
  it("puts Windows transports together and everything else under Servers", () => {
    expect(groupFor(srv({ connection_type: "ssh" }))).toBe("server")
    expect(groupFor(srv({ connection_type: "winrm" }))).toBe("windows")
    expect(groupFor(srv({ connection_type: "rdp" }))).toBe("windows")
  })

  it("a control panel is not a group — a panel server is still a Server", () => {
    // The panel becomes a chip on the row. Giving it a group back would re-create the
    // exception this redesign removed, and would split one machine across two ideas.
    expect(groupFor(srv({ connection_type: "ssh", panel_type: "cyberpanel" }))).toBe("server")
    expect(groupFor(srv({ connection_type: "hosting", panel_type: "cyberpanel" }))).toBe("server")
  })

  it("ignores the stored category, which is exactly what went stale", () => {
    // Two doors wrote that column and disagreed: an imported CyberPanel EC2 was filed as a
    // plain VPS while the same machine added by hand was filed as a panel.
    expect(groupFor(srv({ connection_type: "ssh", category: "windows" }))).toBe("server")
    expect(groupFor(srv({ connection_type: "winrm", category: "vps" }))).toBe("windows")
  })

  it("every group an asset can land in is one the page renders", () => {
    // A group with no descriptor would drop its assets off the page entirely.
    const rendered = new Set(ASSET_GROUPS.map((g) => g.id))
    for (const ct of ["ssh", "winrm", "hosting", "rdp"] as const) {
      expect(rendered.has(groupFor(srv({ connection_type: ct })))).toBe(true)
    }
    expect(groupForServer(srv({ connection_type: "rdp" })).label).toBe("Windows servers")
  })
})

describe("filters slice across the groups", () => {
  it("Panels finds a panel wherever it lives", () => {
    const panels = ASSET_FILTERS.find((f) => f.id === "panels")!
    expect(panels.match(srv({ panel_type: "cyberpanel" }))).toBe(true)
    expect(panels.match(srv({ connection_type: "hosting", panel_type: "cpanel" }))).toBe(true)
    expect(panels.match(srv({ panel_type: null }))).toBe(false)
  })

  it("Needs attention means the three states a customer must act on", () => {
    const attention = ASSET_FILTERS.find((f) => f.id === "attention")!
    for (const status of ["auth_failed", "host_changed", "offline"] as const) {
      expect(attention.match(srv({ status }))).toBe(true)
    }
    // "unknown" is a server we have not reached yet, not one we know is broken — putting it
    // here would cry wolf on every freshly added asset.
    expect(attention.match(srv({ status: "online" }))).toBe(false)
    expect(attention.match(srv({ status: "unknown" }))).toBe(false)
  })

  it("counts across the WHOLE fleet, which is the thing a group cannot do", () => {
    const fleet = [
      srv({ id: "a", connection_type: "ssh", panel_type: "cyberpanel" }),   // Servers group
      srv({ id: "b", connection_type: "winrm", panel_type: "plesk" }),      // Windows group
      srv({ id: "c", connection_type: "ssh" }),
    ]
    const panels = availableFilters(fleet).find((f) => f.filter.id === "panels")
    expect(panels?.count).toBe(2)
  })

  it("a filter with nothing to show is absent, not disabled", () => {
    const onlyLinux = [srv({ id: "a" }), srv({ id: "b", status: "online" })]
    expect(availableFilters(onlyLinux).map((f) => f.filter.id)).toEqual([])

    const withWindows = [...onlyLinux, srv({ id: "c", connection_type: "rdp" })]
    expect(availableFilters(withWindows).map((f) => f.filter.id)).toEqual(["windows"])
  })

  it("offers nothing at all for an empty fleet", () => {
    expect(availableFilters([])).toEqual([])
  })
})


describe("provider zones", () => {
  it("an imported asset lives under its account and nowhere else", () => {
    expect(groupFor(srv({ cloud_account_id: "acc-1" }))).toBe("cloud:acc-1")
  })

  it("its account beats what kind of machine it is", () => {
    // An imported Windows EC2 belongs to the AWS zone, not to Windows servers. "There and
    // nowhere else" is the whole rule; listing it twice is what this replaced.
    expect(groupFor(srv({ connection_type: "winrm", cloud_account_id: "acc-1" })))
      .toBe("cloud:acc-1")
  })

  it("disconnecting the account re-files the asset with no special case", () => {
    // The FK is SET NULL, so this is what the row actually looks like afterwards.
    expect(groupFor(srv({ connection_type: "ssh", cloud_account_id: null }))).toBe("server")
    expect(groupFor(srv({ connection_type: "rdp", cloud_account_id: null }))).toBe("windows")
  })

  it("a connected account with nothing imported still gets a zone", () => {
    // Otherwise the account itself becomes invisible and there is no way back to it.
    const zones = assetZones([], [account()])
    expect(zones.map((z) => z.id)).toEqual(["cloud:acc-1"])
    expect(zones[0].servers).toEqual([])
  })

  it("puts the provider zones before the generic groups", () => {
    const zones = assetZones(
      [srv({ id: "a" }), srv({ id: "b", cloud_account_id: "acc-1" })], [account()])
    expect(zones.map((z) => z.id)).toEqual(["cloud:acc-1", "server"])
  })

  it("never renders an empty generic group", () => {
    const zones = assetZones([srv({ id: "a", cloud_account_id: "acc-1" })], [account()])
    expect(zones.map((z) => z.id)).toEqual(["cloud:acc-1"])
  })

  it("an asset whose account we cannot see falls back instead of vanishing", () => {
    // The dangerous failure: it would be filed into a zone nothing draws, disappear from the
    // page, and look exactly like it had been deleted.
    const orphan = srv({ id: "lost", cloud_account_id: "acc-DELETED" })
    const zones = assetZones([orphan], [account()])
    const shown = zones.flatMap((z) => z.servers.map((s) => s.id))
    expect(shown).toContain("lost")
  })

  it("every asset appears in exactly one zone, whatever the accounts say", () => {
    const fleet = [
      srv({ id: "1" }),
      srv({ id: "2", connection_type: "rdp" }),
      srv({ id: "3", cloud_account_id: "acc-1" }),
      srv({ id: "4", cloud_account_id: "acc-1", connection_type: "winrm" }),
      srv({ id: "5", cloud_account_id: "gone" }),
      srv({ id: "6", connection_type: "hosting", panel_type: "cyberpanel" }),
    ]
    const placed = assetZones(fleet, [account()]).flatMap((z) => z.servers.map((s) => s.id))
    expect(placed.slice().sort()).toEqual(["1", "2", "3", "4", "5", "6"])
  })
})

import { describe, it, expect } from "vitest"
import { detectServers, type MentionServer } from "./serverMentions"

const SERVERS: MentionServer[] = [
  { id: "1", name: "TestServer1" },
  { id: "2", name: "TestServer2" },
  { id: "22", name: "TestServer22" },
  { id: "web", name: "web-prod" },
  { id: "db", name: "db" },
]

const names = (r: MentionServer[]) => r.map((s) => s.name)

describe("detectServers", () => {
  it("finds exactly one named server (the targeting happy path)", () => {
    expect(names(detectServers("check disk on TestServer1", SERVERS))).toEqual(["TestServer1"])
  })

  it("finds no server when none is named (falls through to focus)", () => {
    expect(detectServers("why is this slow?", SERVERS)).toEqual([])
  })

  it("finds two servers when two are named (fleet-scoped / ambiguous)", () => {
    const r = detectServers("copy from TestServer1 to web-prod", SERVERS)
    expect(names(r)).toEqual(["TestServer1", "web-prod"])
  })

  it("treats an @-mention the same as a bare name", () => {
    expect(names(detectServers("@TestServer1 restart nginx", SERVERS)))
      .toEqual(names(detectServers("TestServer1 restart nginx", SERVERS)))
  })

  it("is case-insensitive", () => {
    expect(names(detectServers("look at testserver1", SERVERS))).toEqual(["TestServer1"])
  })

  it("respects word boundaries — a host in an email/ssh string never counts", () => {
    // "db" is a real server name; it must not match inside "adbc" or an address.
    expect(detectServers("connect to root@1.2.3.4 for adbc", SERVERS)).toEqual([])
  })

  it("prefers the longest name (TestServer22, not TestServer2 + trailing 2)", () => {
    expect(names(detectServers("deploy to TestServer22", SERVERS))).toEqual(["TestServer22"])
  })

  it("de-duplicates a name repeated in the message", () => {
    expect(names(detectServers("TestServer1 then TestServer1 again", SERVERS)))
      .toEqual(["TestServer1"])
  })

  it("returns [] when there are no servers", () => {
    expect(detectServers("TestServer1 do a thing", [])).toEqual([])
  })

  it("preserves first-seen order", () => {
    expect(names(detectServers("first web-prod, then TestServer2", SERVERS)))
      .toEqual(["web-prod", "TestServer2"])
  })
})

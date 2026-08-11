import { describe, expect, it } from "vitest"
import { addressFor, importable, needsLogin, ssmCount, viaSsm } from "./cloudImport"
import type { CloudInstance } from "@/api/cloud"

/**
 * The form and the endpoint apply the same rule. When they drift, the button submits a batch
 * the API refuses and the customer has to work out which of their choices caused it — so
 * these mirror `tests/test_ssm_import.py` on the other side.
 */
function ec2(over: Partial<CloudInstance> = {}): CloudInstance {
  return {
    instance_id: "i-1", name: "web", public_ip: "203.0.113.9", private_ip: "10.0.0.9",
    os: "linux", state: "running", region: "eu-west-2", instance_type: "t3.small",
    already_imported: false, ...over,
  } as CloudInstance
}

const PLAIN = { preferSsm: false, usePrivateIp: false }

describe("which way in", () => {
  it("an address beats Systems Manager", () => {
    // SSM has no file transfer and no terminal yet, so choosing it for a machine that has a
    // perfectly good address hands over a server missing both — a downgrade nobody asked for.
    expect(viaSsm(ec2({ ssm_managed: true }), PLAIN)).toBe(false)
  })

  it("the customer can ask for it anyway", () => {
    expect(viaSsm(ec2({ ssm_managed: true }), { ...PLAIN, preferSsm: true })).toBe(true)
  })

  it("asking cannot conjure an agent that is not there", () => {
    expect(viaSsm(ec2({ ssm_managed: false }), { ...PLAIN, preferSsm: true })).toBe(false)
  })

  it("an instance with no address uses it without being asked", () => {
    const nowhere = ec2({ public_ip: null, private_ip: null, ssm_managed: true })
    expect(viaSsm(nowhere, PLAIN)).toBe(true)
  })

  it("honours the private-IP choice when deciding whether there is an address", () => {
    // A public-only instance, with the customer asking to use private addresses: there is no
    // private address, so there is nothing to reach — and SSM is then the only way in.
    const publicOnly = ec2({ private_ip: null, ssm_managed: true })
    expect(addressFor(publicOnly, { ...PLAIN, usePrivateIp: true })).toBeNull()
    expect(viaSsm(publicOnly, { ...PLAIN, usePrivateIp: true })).toBe(true)
    expect(viaSsm(publicOnly, PLAIN)).toBe(false)
  })
})

describe("what can be imported at all", () => {
  it("no address and no agent means no way in", () => {
    expect(importable(ec2({ public_ip: null, private_ip: null }), PLAIN)).toBe(false)
  })

  it("the agent makes an addressless instance importable — the thing SSH cannot do", () => {
    expect(importable(ec2({ public_ip: null, private_ip: null, ssm_managed: true }), PLAIN))
      .toBe(true)
  })
})

describe("what the customer is asked for", () => {
  it("an all-Systems-Manager batch needs no login", () => {
    const batch = [
      ec2({ instance_id: "a", public_ip: null, private_ip: null, ssm_managed: true }),
      ec2({ instance_id: "b", public_ip: null, private_ip: null, ssm_managed: true }),
    ]
    expect(needsLogin(batch, PLAIN)).toBe(false)
    expect(ssmCount(batch, PLAIN)).toBe(2)
  })

  it("one SSH instance brings the login back", () => {
    const batch = [
      ec2({ instance_id: "a", public_ip: null, private_ip: null, ssm_managed: true }),
      ec2({ instance_id: "b" }),
    ]
    expect(needsLogin(batch, PLAIN)).toBe(true)
    expect(ssmCount(batch, PLAIN)).toBe(1)
  })

  it("an empty selection asks for nothing", () => {
    // The Import button is disabled on an empty selection anyway; demanding a key here would
    // make the form look broken before anything is chosen.
    expect(needsLogin([], PLAIN)).toBe(false)
  })

  it("a provider with no Systems Manager always needs a login", () => {
    // DigitalOcean and Hetzner have no such thing, so the field is absent rather than false.
    const droplet = ec2({ instance_id: "d", ssm_managed: undefined })
    expect(viaSsm(droplet, { ...PLAIN, preferSsm: true })).toBe(false)
    expect(needsLogin([droplet], PLAIN)).toBe(true)
  })
})

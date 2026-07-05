import { describe, it, expect } from "vitest"
import { redactSecrets, SECRET_MASK } from "./redactSecrets"

const hidden = (out: string, v: string) => !out.includes(v)

describe("redactSecrets", () => {
  it("masks wp-config define() password", () => {
    const { text } = redactSecrets(`define('DB_PASSWORD', 'Wp$3cretPr0d!');`)
    expect(hidden(text, "Wp$3cretPr0d!")).toBe(true)
    expect(text).toContain(SECRET_MASK)
  })

  it("masks KEY=value env secrets, keeps the key", () => {
    const { text } = redactSecrets("API_KEY=abc123supersecret\nPORT=8080")
    expect(hidden(text, "abc123supersecret")).toBe(true)
    expect(text).toContain("API_KEY")
    expect(text).toContain("PORT=8080") // ordinary config untouched
  })

  it("masks an OFF-LIST key name like bearer / authorization (red-team gap)", () => {
    const { text } = redactSecrets("bearer: Sup3rS3cretDBv4lue!!\nauthorization: Token xyz987abc")
    expect(hidden(text, "Sup3rS3cretDBv4lue!!")).toBe(true)
    expect(hidden(text, "xyz987abc")).toBe(true)
  })

  it("masks a YAML next-line block-scalar value under a sensitive key (red-team gap)", () => {
    const yaml = "db:\n  password: |\n    Sup3rBlockScalarSecret\n  host: localhost"
    const { text } = redactSecrets(yaml)
    expect(hidden(text, "Sup3rBlockScalarSecret")).toBe(true)
    expect(text).toContain("host: localhost") // sibling non-secret stays
  })

  it("masks a PEM private-key block body", () => {
    const pem = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAA\n-----END OPENSSH PRIVATE KEY-----"
    const { text } = redactSecrets(pem)
    expect(hidden(text, "b3BlbnNzaC1rZXktdjEAAAA")).toBe(true)
  })

  it("masks connection-string passwords and standalone tokens", () => {
    const { text } = redactSecrets("url = postgres://user:p4ssw0rd@db:5432/app\ntok = ghp_0123456789abcdef0123456789abcdef")
    expect(hidden(text, "p4ssw0rd")).toBe(true)
    expect(hidden(text, "ghp_0123456789abcdef0123456789abcdef")).toBe(true)
  })

  it("leaves an ordinary config file untouched", () => {
    const cfg = "server:\n  host: 0.0.0.0\n  port: 443\n  workers: 4"
    const { text, count } = redactSecrets(cfg)
    expect(text).toBe(cfg)
    expect(count).toBe(0)
  })
})

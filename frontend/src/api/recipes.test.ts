import { describe, it, expect } from "vitest"
import { composeRecipeMessage, missingRequired, type Recipe } from "./recipes"

const wp: Recipe = {
  slug: "cyberpanel-host-website",
  title: "Host a Website / WordPress on CyberPanel",
  summary: "…",
  icon: "wordpress",
  os_family: "linux",
  budget: 25,
  variables: [
    { name: "domain", required: true, default: "" },
    { name: "title", required: false, default: "{{domain}}" },
    { name: "email", required: false, default: "admin@{{domain}}" },
  ],
  goal_template: "Host a WordPress site at {{domain}}, title '{{title}}', admin email {{email}}",
}

const gh: Recipe = {
  slug: "github-deploy",
  title: "Deploy a GitHub Repo",
  summary: "…",
  icon: "github",
  os_family: "linux",
  budget: 25,
  variables: [{ name: "repo", required: true, default: "" }],
  goal_template: "Deploy the GitHub repo {{repo}} to this server",
}

describe("composeRecipeMessage", () => {
  it("resolves defaults that reference an earlier variable", () => {
    // only domain given → title + email defaults fill from it
    const msg = composeRecipeMessage(wp, { domain: "shop.example.com" })
    expect(msg).toBe(
      "Host a WordPress site at shop.example.com, title 'shop.example.com', admin email admin@shop.example.com",
    )
  })

  it("uses explicit values over defaults", () => {
    const msg = composeRecipeMessage(wp, {
      domain: "shop.example.com",
      title: "My Shop",
      email: "me@x.io",
    })
    expect(msg).toBe("Host a WordPress site at shop.example.com, title 'My Shop', admin email me@x.io")
  })

  it("fills a simple required variable", () => {
    expect(composeRecipeMessage(gh, { repo: "github.com/acme/app" })).toBe(
      "Deploy the GitHub repo github.com/acme/app to this server",
    )
  })

  it("collapses whitespace when an unresolved slot ends up empty", () => {
    // a template slot with no value + no default collapses rather than leaving a gap
    const r: Recipe = { ...gh, goal_template: "Deploy {{repo}} now", variables: [{ name: "repo", required: false, default: "" }] }
    expect(composeRecipeMessage(r, {})).toBe("Deploy now")
  })
})

describe("missingRequired", () => {
  it("flags a blank required field", () => {
    expect(missingRequired(wp, {})).toEqual(["domain"])
    expect(missingRequired(wp, { domain: "  " })).toEqual(["domain"]) // whitespace-only counts as blank
  })

  it("passes when required fields are filled; optionals may be blank", () => {
    expect(missingRequired(wp, { domain: "x.com" })).toEqual([])
  })
})

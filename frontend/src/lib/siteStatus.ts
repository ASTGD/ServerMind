import type { Site } from "@/api/sites"

/**
 * What a site's state is, and the one honest sentence explaining it.
 *
 * This lives in one place because the two site lists — the fleet-wide page and the one
 * inside a server — drifted: the server's list knew a site could still be installing or
 * have failed, and the fleet list did not. So a site whose install never finished was
 * shown there as a normal site whose DNS was broken, sending the customer to fix DNS when
 * the real answer was already recorded ("no web server is running on this server").
 *
 * Both lists read from here now, so a state added later cannot be shown in one and missed
 * in the other.
 */

export type SiteState = "installing" | "failed" | "absent" | "normal"

export function siteState(site: Site): SiteState {
  if (site.status === "installing") return "installing"
  if (site.status === "failed") return "failed"
  // Only once the install has settled does "we cannot find it" mean anything. A site
  // being built is not missing; it has not finished.
  if (!site.is_present) return "absent"
  return "normal"
}

/**
 * The single reason to put in front of the customer, or null when nothing is wrong.
 *
 * An install that failed outranks whatever the uptime monitor thinks: the monitor is
 * checking a site that was never built, so its answer ("the domain could not be resolved")
 * is true but useless, and it hides the reason we already know.
 */
export function siteProblem(site: Site): string | null {
  const state = siteState(site)
  if (state === "failed") {
    return site.install_error || "The setup did not finish."
  }
  if (state === "installing") return null
  if (site.uptime?.status === "down" && site.uptime.error) return site.uptime.error
  return null
}

/** Whether the row should read as broken. A site still being built is not a failure yet. */
export function siteLooksBroken(site: Site): boolean {
  const state = siteState(site)
  if (state === "installing") return false
  return state === "failed" || site.uptime?.status === "down"
}

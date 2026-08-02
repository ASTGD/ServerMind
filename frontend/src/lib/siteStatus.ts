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

export type SiteState = "installing" | "failed" | "absent" | "unpointed" | "normal"

export function siteState(site: Site): SiteState {
  if (site.status === "installing") return "installing"
  if (site.status === "failed") return "failed"
  // Only once the install has settled does "we cannot find it" mean anything. A site
  // being built is not missing; it has not finished.
  if (!site.is_present) return "absent"
  // A domain that does not resolve AND has never answered was never pointed here. That is
  // a step nobody has done yet, not an outage — and it is the state every site is in the
  // moment it is created, so calling it "down" makes a brand-new site look broken.
  //
  // "Has never answered" is what makes this safe. A live site whose DNS is deleted gives
  // the same words from the checker and IS an emergency, so it stays down.
  if (site.uptime?.unresolved && site.uptime.ever_up === false) return "unpointed"
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
  // The chip already says we can no longer find it, and its check is paused once we know
  // that — so the last thing the monitor said is frozen in time and only adds noise.
  if (state === "absent") return null
  if (state === "unpointed") {
    // What to DO, not what failed. The fix is at the registrar, not on the server.
    return "This domain is not pointed anywhere yet, so nobody can reach the site."
  }
  if (site.uptime?.status === "down" && site.uptime.error) return site.uptime.error
  return null
}

/** Whether the row should read as broken. A site still being built is not a failure yet. */
export function siteLooksBroken(site: Site): boolean {
  const state = siteState(site)
  // Neither of these is a fault. One has not finished arriving; the other has not been
  // pointed here. Painting them red teaches people to ignore red.
  if (state === "installing" || state === "unpointed") return false
  return state === "failed" || site.uptime?.status === "down"
}

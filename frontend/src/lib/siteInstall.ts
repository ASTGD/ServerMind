import type { Site } from "@/api/sites"

/**
 * May something be installed onto this site?
 *
 * Only a site ServerAlly created as an empty one — a folder, an address and a placeholder
 * page, with nothing put there yet. That is exactly what `requested_type === "static"`
 * means, because it is set only when we create or install.
 *
 * The tempting version of this test is "does it look empty", off `app_type`. It is wrong,
 * and dangerously so: discovery labels any site it cannot identify as `unknown` — a plain
 * HTML site, someone's hand-built PHP app, anything that is not WordPress or Laravel — so
 * "unknown means empty" offers to install WordPress over a real site with real content in
 * it. The server would refuse (its takeover guard requires ServerAlly's own marker in the
 * config), so nothing would be destroyed, but the button would be a promise we cannot
 * keep, aimed at exactly the sites where being wrong costs the most.
 */
export function canInstallOnto(site: Pick<Site, "requested_type" | "status">): boolean {
  return site.requested_type === "static" && site.status === "live"
}

/** Did ServerAlly make this site, or did we find it already on the server? */
export function wasCreatedHere(site: Pick<Site, "source">): boolean {
  return site.source === "manual"
}

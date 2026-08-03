import type { ReactNode } from "react"
import { Globe, Loader2, ShieldAlert, ShieldCheck } from "lucide-react"
import { APP_LABEL, type Site } from "@/api/sites"
import { siteState, siteStatusLabel, siteTone } from "@/lib/siteStatus"
import { cn } from "@/lib/utils"

/**
 * The small pills a site row is built from.
 *
 * Shared by both site lists on purpose. The rule behind these — what a site's state is —
 * already lives in one place because the two lists drifted once and showed different
 * answers for the same site. Rendering that rule twice would let them drift again, just
 * in appearance instead of in meaning.
 *
 * Everything here is deliberately small and quiet. A list is scanned, not read: the only
 * thing allowed to shout is a real fault.
 */

type PillTone = "good" | "bad" | "warn" | "calm" | "quiet"

const TONE: Record<PillTone, string> = {
  good: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-300",
  bad: "bg-red-500/12 text-red-700 dark:text-red-300",
  warn: "bg-amber-500/12 text-amber-700 dark:text-amber-300",
  // For a state that is neither good nor bad — a step nobody has done yet.
  calm: "bg-primary/10 text-primary",
  quiet: "bg-muted text-muted-foreground",
}

export function Pill({ tone = "quiet", icon, title, children }: {
  tone?: PillTone
  icon?: ReactNode
  title?: string
  children: ReactNode
}) {
  return (
    <span
      title={title}
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5",
        "text-[10.5px] font-medium leading-none",
        TONE[tone],
      )}
    >
      {icon}
      {children}
    </span>
  )
}

/** Plain supporting detail — a path, a version. Never a pill: pills are for states. */
export function InfoText({ children, title, mono }: {
  children: ReactNode
  title?: string
  mono?: boolean
}) {
  return (
    <span
      title={title}
      className={cn("truncate text-[11px] text-muted-foreground",
        mono && "font-mono")}
    >
      {children}
    </span>
  )
}

/** What is running here. Its own pill because it is the first thing anyone looks for. */
export function TypePill({ site }: { site: Site }) {
  const label = APP_LABEL[site.app_type] ?? site.app_type
  if (!label || label === "unknown") return null
  return (
    <Pill tone="quiet">
      {label}
      {site.app_version ? ` ${site.app_version}` : ""}
    </Pill>
  )
}

/**
 * Where the site stands, in one pill.
 *
 * "Not pointed here yet" was a sentence pretending to be a status — long enough to make
 * every row taller and vague enough that it did not say where to go and fix it. "DNS not
 * set" names the thing and, by naming it, names the place: the registrar, not the server.
 * The full explanation stays, as the pill's tooltip.
 */
export function StatusPill({ site }: { site: Site }) {
  const state = siteState(site)
  const tone = siteTone(site)

  if (state === "installing" || state === "removing") {
    return (
      <Pill tone="quiet" icon={<Loader2 size={9} className="animate-spin" />}>
        {siteStatusLabel(site)}
      </Pill>
    )
  }
  if (state === "unpointed") {
    return (
      <Pill
        tone="calm"
        icon={<Globe size={9} />}
        title="This domain is not pointed anywhere yet, so nobody can reach the site. Point its DNS at this server."
      >
        DNS not set
      </Pill>
    )
  }
  return (
    <Pill tone={tone === "bad" ? "bad" : tone === "good" ? "good" : "quiet"}>
      {siteStatusLabel(site)}
    </Pill>
  )
}

/** The certificate a visitor actually receives, not the one named in the config. */
export function CertPill({ site }: { site: Site }) {
  const days = site.uptime?.cert_days_left
  const state = site.uptime?.cert_state

  if (state === "expired") {
    return (
      <Pill tone="bad" icon={<ShieldAlert size={9} />}>Certificate expired</Pill>
    )
  }
  if (typeof days === "number" && days <= 14) {
    return (
      <Pill tone="warn" icon={<ShieldAlert size={9} />}>HTTPS ends in {days}d</Pill>
    )
  }
  if (typeof days === "number") {
    return (
      <Pill tone="quiet" icon={<ShieldCheck size={9} />}
        title="Days until the certificate a visitor receives expires.">
        HTTPS {days}d
      </Pill>
    )
  }
  if (site.has_ssl) {
    return (
      <Pill tone="quiet" icon={<ShieldCheck size={9} />}
        title="The server is set up for HTTPS. Watch this site to track when it expires.">
        HTTPS
      </Pill>
    )
  }
  return null
}

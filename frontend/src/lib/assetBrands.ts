/**
 * Brand theming for Hosting panels and Cloud providers, so a CyberPanel card
 * reads as CyberPanel and an AWS account reads as AWS — the card background,
 * border, icon tile, badge, and launch button all pick up the brand's color.
 *
 * The class strings are LITERAL on purpose: Tailwind's JIT only keeps classes it
 * can see as complete strings in source, so we can't build `bg-${color}-50`.
 */
export interface AssetBrand {
  /** Proper display name (e.g. "cPanel", "DigitalOcean"). */
  name: string
  /** Outer card wash + border (replaces the neutral `border-border bg-card`). */
  card: string
  /** The icon tile. */
  tile: string
  /** A small brand pill/badge. */
  badge: string
  /** The launch button's branded hover (Open panel / Open console). */
  button: string
}

/** Keyed by `servers.panel_type`. */
const HOSTING_BRANDS: Record<string, AssetBrand> = {
  cpanel: {
    name: "cPanel",
    card: "border-orange-200 bg-orange-50/60 dark:border-orange-900/50 dark:bg-orange-950/20",
    tile: "bg-orange-500/15 text-orange-600 dark:text-orange-400",
    badge: "bg-orange-500/15 text-orange-700 dark:text-orange-400",
    button: "hover:border-orange-400/60 hover:bg-orange-500/10 hover:text-orange-700 dark:hover:text-orange-400",
  },
  cyberpanel: {
    name: "CyberPanel",
    card: "border-sky-200 bg-sky-50/60 dark:border-sky-900/50 dark:bg-sky-950/20",
    tile: "bg-sky-500/15 text-sky-600 dark:text-sky-400",
    badge: "bg-sky-500/15 text-sky-700 dark:text-sky-400",
    button: "hover:border-sky-400/60 hover:bg-sky-500/10 hover:text-sky-700 dark:hover:text-sky-400",
  },
  plesk: {
    name: "Plesk",
    card: "border-slate-300 bg-slate-100/60 dark:border-slate-700/60 dark:bg-slate-800/30",
    tile: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
    badge: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
    button: "hover:border-slate-400/60 hover:bg-slate-500/10 hover:text-slate-800 dark:hover:text-slate-200",
  },
  directadmin: {
    name: "DirectAdmin",
    card: "border-blue-200 bg-blue-50/60 dark:border-blue-900/50 dark:bg-blue-950/20",
    tile: "bg-blue-500/15 text-blue-600 dark:text-blue-400",
    badge: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
    button: "hover:border-blue-400/60 hover:bg-blue-500/10 hover:text-blue-700 dark:hover:text-blue-400",
  },
}

/** Keyed by `cloud_accounts.provider`. */
const CLOUD_BRANDS: Record<string, AssetBrand> = {
  aws: {
    name: "AWS",
    card: "border-amber-200 bg-amber-50/60 dark:border-amber-900/50 dark:bg-amber-950/20",
    tile: "bg-amber-500/15 text-amber-600 dark:text-amber-500",
    badge: "bg-amber-500/15 text-amber-700 dark:text-amber-500",
    button: "hover:border-amber-400/60 hover:bg-amber-500/10 hover:text-amber-700 dark:hover:text-amber-500",
  },
  digitalocean: {
    name: "DigitalOcean",
    card: "border-blue-200 bg-blue-50/60 dark:border-blue-900/50 dark:bg-blue-950/20",
    tile: "bg-blue-500/15 text-blue-600 dark:text-blue-400",
    badge: "bg-blue-500/15 text-blue-700 dark:text-blue-400",
    button: "hover:border-blue-400/60 hover:bg-blue-500/10 hover:text-blue-700 dark:hover:text-blue-400",
  },
  hetzner: {
    name: "Hetzner",
    card: "border-red-200 bg-red-50/60 dark:border-red-900/50 dark:bg-red-950/20",
    tile: "bg-red-500/15 text-red-600 dark:text-red-400",
    badge: "bg-red-500/15 text-red-700 dark:text-red-400",
    button: "hover:border-red-400/60 hover:bg-red-500/10 hover:text-red-700 dark:hover:text-red-400",
  },
  gcp: {
    name: "Google Cloud",
    card: "border-indigo-200 bg-indigo-50/60 dark:border-indigo-900/50 dark:bg-indigo-950/20",
    tile: "bg-indigo-500/15 text-indigo-600 dark:text-indigo-400",
    badge: "bg-indigo-500/15 text-indigo-700 dark:text-indigo-400",
    button: "hover:border-indigo-400/60 hover:bg-indigo-500/10 hover:text-indigo-700 dark:hover:text-indigo-400",
  },
  azure: {
    name: "Azure",
    card: "border-cyan-200 bg-cyan-50/60 dark:border-cyan-900/50 dark:bg-cyan-950/20",
    tile: "bg-cyan-500/15 text-cyan-600 dark:text-cyan-400",
    badge: "bg-cyan-500/15 text-cyan-700 dark:text-cyan-400",
    button: "hover:border-cyan-400/60 hover:bg-cyan-500/10 hover:text-cyan-700 dark:hover:text-cyan-400",
  },
}

/** The brand theme for a hosting panel, or undefined for an unknown/absent panel. */
export function hostingBrand(panelType: string | null | undefined): AssetBrand | undefined {
  return panelType ? HOSTING_BRANDS[panelType] : undefined
}

/** The brand theme for a cloud provider, or undefined for an unknown/absent provider. */
export function cloudBrand(provider: string | null | undefined): AssetBrand | undefined {
  return provider ? CLOUD_BRANDS[provider] : undefined
}

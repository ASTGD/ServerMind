import { SIMPLE_ICON_PATHS } from "@/lib/brandIconData"

/** Dark-mode color override for glyphs whose brand hex is too dark to read on a dark
 *  card (simple-icons AlmaLinux is pure black, CentOS a near-black navy). */
const HEX_DARK: Record<string, string> = {
  almalinux: "#E5E7EB",
  centos: "#A5A8F0",
}

/** The five brands simple-icons doesn't carry (trademark) — hand-authored below. */
const CUSTOM = new Set(["windows", "aws", "azure", "cyberpanel", "directadmin"])

/** Map a server's os_type to a known OS glyph slug (undefined → caller falls back). */
export function osIconSlug(osType: string | null | undefined): string | undefined {
  if (!osType) return undefined
  const s = osType.toLowerCase()
  if (s.includes("ubuntu")) return "ubuntu"
  if (s.includes("debian")) return "debian"
  if (s.includes("alma")) return "almalinux"
  if (s.includes("rocky")) return "rockylinux"
  if (s.includes("cent")) return "centos"
  if (s.includes("fedora")) return "fedora"
  if (s.includes("red hat") || s.includes("redhat") || s.includes("rhel")) return "redhat"
  if (s.includes("windows")) return "windows"
  if (s.includes("linux") || s.includes("unix")) return "linux"
  return undefined
}

/** Map a cloud provider key to a glyph slug (gcp → googlecloud). */
export function providerIconSlug(provider: string | null | undefined): string | undefined {
  if (!provider) return undefined
  if (provider === "gcp") return "googlecloud"
  if (["aws", "digitalocean", "hetzner", "azure"].includes(provider)) return provider
  return undefined
}

/** True if we can render a real glyph for this slug (else the caller shows a fallback icon). */
export function hasBrandIcon(slug: string | undefined | null): boolean {
  return !!slug && (slug in SIMPLE_ICON_PATHS || CUSTOM.has(slug))
}

interface Props {
  slug?: string
  size?: number
  className?: string
}

/** A colored brand/OS glyph for an asset card. OS/panel/provider all resolve to a slug;
 *  simple-icons glyphs render from inlined CC0 path data, and five trademark-missing
 *  brands (Windows, AWS, Azure, CyberPanel, DirectAdmin) are hand-authored. Returns null
 *  for an unknown slug so callers can fall back to a generic icon. */
export default function BrandIcon({ slug, size = 26, className }: Props) {
  if (!slug) return null
  if (CUSTOM.has(slug)) return <CustomGlyph slug={slug} size={size} className={className} />

  const icon = SIMPLE_ICON_PATHS[slug]
  if (!icon) return null
  const dark = HEX_DARK[slug]
  if (dark) {
    return (
      <>
        <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden fill={icon.hex} className={`${className ?? ""} dark:hidden`.trim()}><path d={icon.path} /></svg>
        <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden fill={dark} className={`${className ?? ""} hidden dark:block`.trim()}><path d={icon.path} /></svg>
      </>
    )
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden fill={icon.hex} className={className}><path d={icon.path} /></svg>
}

/** Hand-authored marks for the brands simple-icons lacks — colored + recognizable,
 *  paired with the brand-name badge on the card so identity is unambiguous. */
function CustomGlyph({ slug, size, className }: { slug: string; size: number; className?: string }) {
  const box = { width: size, height: size, viewBox: "0 0 24 24", "aria-hidden": true as const, className }
  switch (slug) {
    case "windows": // four panes (Windows 11)
      return (
        <svg {...box} fill="#00A4EF">
          <rect x="2.5" y="2.5" width="8.5" height="8.5" rx="0.6" />
          <rect x="13" y="2.5" width="8.5" height="8.5" rx="0.6" />
          <rect x="2.5" y="13" width="8.5" height="8.5" rx="0.6" />
          <rect x="13" y="13" width="8.5" height="8.5" rx="0.6" />
        </svg>
      )
    case "aws": // the "smile" arrow
      return (
        <svg {...box} fill="none" stroke="#FF9900" strokeWidth={2.3} strokeLinecap="round" strokeLinejoin="round">
          <path d="M3.6 14.4 Q12 20.4 20.4 14.4" />
          <path d="M17.1 16.1 L20.7 14.2 L19.1 10.7" />
        </svg>
      )
    case "azure": // stylized "A"
      return (
        <svg {...box} fill="#0089D6">
          <path d="M12 3 L21 20.6 H14.6 L12 14.2 L9.4 20.6 H3 Z" />
        </svg>
      )
    case "cyberpanel": // hexagon + inner "C"
      return (
        <svg {...box} fill="none" stroke="#0EA5E9" strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round">
          <path d="M12 2.4 L20.2 7 V17 L12 21.6 L3.8 17 V7 Z" />
          <path d="M15 9.6 a4 4 0 1 0 0 4.8" />
        </svg>
      )
    case "directadmin": // blue disc + play mark
      return (
        <svg {...box}>
          <circle cx="12" cy="12" r="9.6" fill="#1E63D0" />
          <path d="M9.2 7.6 L16.6 12 L9.2 16.4 Z" fill="#fff" />
        </svg>
      )
    default:
      return null
  }
}

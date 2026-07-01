/**
 * ServerAlly brand mark + wordmark.
 *
 * The mark is a gradient squircle badge holding an AI spark above a server bar —
 * "an AI companion for your server." The gradient (indigo→violet→purple) matches
 * the top-bar accent and the account avatar for one cohesive identity.
 */

interface MarkProps {
  /** Rendered pixel size (square). */
  size?: number
  className?: string
}

export function LogoMark({ size = 32, className }: MarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="ServerAlly"
    >
      <defs>
        <linearGradient id="sa-grad" x1="4" y1="3" x2="36" y2="37" gradientUnits="userSpaceOnUse">
          <stop stopColor="#6366F1" />
          <stop offset="0.55" stopColor="#8B5CF6" />
          <stop offset="1" stopColor="#A855F7" />
        </linearGradient>
        <linearGradient id="sa-hi" x1="20" y1="2" x2="20" y2="26" gradientUnits="userSpaceOnUse">
          <stop stopColor="#FFFFFF" stopOpacity="0.24" />
          <stop offset="1" stopColor="#FFFFFF" stopOpacity="0" />
        </linearGradient>
      </defs>

      {/* Badge */}
      <rect x="2" y="2" width="36" height="36" rx="11" fill="url(#sa-grad)" />
      <rect x="2" y="2" width="36" height="36" rx="11" fill="url(#sa-hi)" />

      {/* AI spark */}
      <path
        d="M20 6.5 Q20.7 13 26.5 14.5 Q20.7 16 20 22.5 Q19.3 16 13.5 14.5 Q19.3 13 20 6.5 Z"
        fill="#FFFFFF"
      />

      {/* Server bar with status lights */}
      <rect x="9.5" y="25" width="21" height="6" rx="3" fill="#FFFFFF" />
      <circle cx="13.6" cy="28" r="1.15" fill="#7C3AED" />
      <circle cx="17" cy="28" r="1.15" fill="#7C3AED" />
    </svg>
  )
}

interface LogoProps {
  size?: "md" | "lg"
  className?: string
}

/** Full lockup: mark + "ServerAlly" wordmark ("Ally" in the brand gradient). */
export default function Logo({ size = "md", className }: LogoProps) {
  const markSize = size === "lg" ? 40 : 30
  const textCls = size === "lg" ? "text-2xl" : "text-lg"
  return (
    <span className={`inline-flex items-center gap-2.5 ${className ?? ""}`}>
      <LogoMark size={markSize} />
      <span className={`${textCls} font-bold tracking-tight text-foreground`}>
        Server
        <span className="bg-gradient-to-r from-indigo-500 to-violet-500 bg-clip-text text-transparent">
          Ally
        </span>
      </span>
    </span>
  )
}

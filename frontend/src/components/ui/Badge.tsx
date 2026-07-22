import type { ComponentProps } from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

export const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        default: "bg-secondary text-secondary-foreground",
        outline: "border border-border text-muted-foreground",
        success: "bg-success/10 text-success",
        warning: "bg-warning/10 text-warning",
        danger: "bg-destructive/10 text-destructive",
        brand: "bg-primary/10 text-primary",
      },
    },
    defaultVariants: { variant: "default" },
  },
)

export type BadgeProps = ComponentProps<"span"> & VariantProps<typeof badgeVariants>

/** Small label chip (counts, categories, states). */
export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}

const pillTone = {
  success: "border-success/30 bg-success/10 text-success",
  warning: "border-warning/30 bg-warning/10 text-warning",
  danger: "border-destructive/30 bg-destructive/10 text-destructive",
  neutral: "border-border bg-muted/60 text-muted-foreground",
  brand: "border-primary/30 bg-primary/10 text-primary",
} as const

export type StatusTone = keyof typeof pillTone

export interface StatusPillProps extends ComponentProps<"span"> {
  tone?: StatusTone
  /** Show the leading status dot (default true). */
  dot?: boolean
  /** Pulse the dot (e.g. live/running states). */
  pulse?: boolean
}

/** Status pill with a colored dot — online/offline, verified, running, blocked… */
export function StatusPill({ tone = "neutral", dot = true, pulse, className, children, ...props }: StatusPillProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        pillTone[tone],
        className,
      )}
      {...props}
    >
      {dot && (
        <span className="relative flex h-1.5 w-1.5">
          {pulse && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-60" />}
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-current" />
        </span>
      )}
      {children}
    </span>
  )
}

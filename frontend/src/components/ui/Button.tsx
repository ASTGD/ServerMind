import type { ComponentProps } from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

export const buttonVariants = cva(
  // Base — matches the app's existing button idiom (rounded-lg, text-sm font-medium).
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-primary text-primary-foreground shadow-sm hover:bg-primary/90",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        outline: "border border-border bg-transparent text-foreground hover:bg-muted/60",
        ghost: "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
        danger: "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
        /** The signature brand gradient (Ask Ally / Start mission). */
        gradient: "bg-brand-gradient text-white shadow-sm hover:opacity-95",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-9 px-4",
        lg: "h-10 px-5",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
)

export type ButtonProps = ComponentProps<"button"> & VariantProps<typeof buttonVariants>

/** Themed button. Variants: primary · secondary · outline · ghost · danger · gradient. */
export function Button({ className, variant, size, type = "button", ...props }: ButtonProps) {
  return <button type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />
}

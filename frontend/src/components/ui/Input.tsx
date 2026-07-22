import type { ComponentProps } from "react"
import { cn } from "@/lib/utils"

/** Themed text input — matches the app's established field style. */
export function Input({ className, ...props }: ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground",
        "placeholder:text-muted-foreground/60",
        "focus:outline-none focus:ring-2 focus:ring-primary/40",
        "disabled:cursor-not-allowed disabled:opacity-60",
        className,
      )}
      {...props}
    />
  )
}

/** Field label — pairs with Input. */
export function Label({ className, ...props }: ComponentProps<"label">) {
  return <label className={cn("mb-1.5 block text-xs font-medium text-muted-foreground", className)} {...props} />
}

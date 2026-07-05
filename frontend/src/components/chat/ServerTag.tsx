import { cn } from "@/lib/utils"
import { serverColor, FLEET_COLOR } from "@/lib/serverColor"

/**
 * A small, stable-colored pill naming the server a message / plan / step is about.
 * The color is consistent per server everywhere it appears — like an avatar in a group
 * chat, so you can tell at a glance which resource a line concerns. With no name it
 * reads "All servers" in the neutral fleet color.
 */
export default function ServerTag({
  name,
  className,
}: {
  name?: string | null
  className?: string
}) {
  const isFleet = !name
  // Color by NAME (not id): a plan card and a mission step only carry the server's name,
  // never its id — hashing by the one key present everywhere keeps a server's color the
  // same on every surface it appears.
  const c = isFleet ? FLEET_COLOR : serverColor(name!)
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
        c.chip,
        className,
      )}
      title={isFleet ? "About all your servers" : `About ${name}`}
    >
      <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", c.dot)} />
      {isFleet ? "All servers" : name}
    </span>
  )
}

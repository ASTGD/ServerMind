/**
 * A stable, per-server color so a server looks the same everywhere it appears — the chip
 * on a chat message, a mission card header, a focus indicator. The point is recognition:
 * once the user sees "TestServer3" is teal, teal *means* TestServer3 at a glance, the way
 * avatars work in a group chat.
 *
 * Derived by hashing the server id (not the name — a rename keeps the color), so it's
 * deterministic and needs no storage. The palette is intentionally small and calm; each
 * className is a full literal string so Tailwind's scanner generates it.
 */

export interface ServerColor {
  /** Pill styling on a light surface: soft tinted background + readable text. */
  chip: string
  /** A solid dot / accent of the same hue (headers, focus indicator). */
  dot: string
  /** The same hue as a left border / ring accent. */
  ring: string
}

// Calm, well-separated hues. Order is irrelevant (we hash into it); count should be a
// handful more than a typical fleet so collisions are rare but graceful when they happen.
const PALETTE: ServerColor[] = [
  { chip: "bg-blue-500/10 text-blue-700 dark:text-blue-300", dot: "bg-blue-500", ring: "border-blue-500/40" },
  { chip: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300", dot: "bg-emerald-500", ring: "border-emerald-500/40" },
  { chip: "bg-violet-500/10 text-violet-700 dark:text-violet-300", dot: "bg-violet-500", ring: "border-violet-500/40" },
  { chip: "bg-amber-500/10 text-amber-700 dark:text-amber-400", dot: "bg-amber-500", ring: "border-amber-500/40" },
  { chip: "bg-teal-500/10 text-teal-700 dark:text-teal-300", dot: "bg-teal-500", ring: "border-teal-500/40" },
  { chip: "bg-rose-500/10 text-rose-700 dark:text-rose-300", dot: "bg-rose-500", ring: "border-rose-500/40" },
  { chip: "bg-cyan-500/10 text-cyan-700 dark:text-cyan-300", dot: "bg-cyan-500", ring: "border-cyan-500/40" },
  { chip: "bg-fuchsia-500/10 text-fuchsia-700 dark:text-fuchsia-300", dot: "bg-fuchsia-500", ring: "border-fuchsia-500/40" },
]

/** A neutral fallback when there's no server (fleet-wide messages). */
export const FLEET_COLOR: ServerColor = {
  chip: "bg-muted text-muted-foreground",
  dot: "bg-zinc-400",
  ring: "border-border",
}

/** Stable FNV-1a-ish hash of the id → an index into {@link PALETTE}. */
function hash(id: string): number {
  let h = 0
  for (let i = 0; i < id.length; i++) {
    h = (h * 31 + id.charCodeAt(i)) >>> 0
  }
  return h
}

/** The stable color for a server id. Same id → same color, always. */
export function serverColor(id: string): ServerColor {
  if (!id) return FLEET_COLOR
  return PALETTE[hash(id) % PALETTE.length]
}

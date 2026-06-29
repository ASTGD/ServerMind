/**
 * True if a server's OS is compatible with a playbook's supported OS families
 * (Update 21 — per-playbook OS guard).
 *
 * - `null`/empty `supported` → OS-agnostic playbook → always compatible.
 * - unknown server OS (null / "linux") → don't block (never block on uncertainty).
 */
export function osCompatible(
  serverOsType: string | null | undefined,
  supported: string[] | null | undefined,
): boolean {
  if (!supported || supported.length === 0) return true
  const os = (serverOsType ?? "").toLowerCase()
  if (!os || os === "linux") return true
  return supported.map((s) => s.toLowerCase()).includes(os)
}

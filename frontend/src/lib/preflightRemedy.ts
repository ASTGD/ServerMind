/**
 * Plain-English "what to do" for a known install / pre-flight failure reason.
 *
 * Keyed off stable phrases in the failure reason text (which the backend's
 * pre-flight guard and error extraction produce). Returns null when we have no
 * specific suggestion, so the UI only shows guidance it's confident about
 * (Update 19, Tier 1 — actionable failures).
 */
export function failureRemedy(reason: string | null | undefined): string | null {
  if (!reason) return null
  const r = reason.toLowerCase()

  // Something is already serving web traffic (port 80/443, or a named web server).
  if (r.includes("port 80") || r.includes("port 443") || r.includes("web server")) {
    return "Control panels need a fresh server with nothing else serving web traffic. Use a brand-new VPS, or stop and remove what's using the port first — that deletes any sites it hosts."
  }
  // Not enough memory.
  if (r.includes("ram") || r.includes("memory")) {
    return "Resize this VPS to a larger plan (it doesn't have enough memory), then run the install again."
  }
  // Unsupported operating system.
  if ((r.includes("supports") && r.includes("found")) || r.includes("unsupported os")) {
    return "Reinstall this VPS with a supported OS — usually Ubuntu 22.04 or AlmaLinux 8 — then try again."
  }
  // Connection dropped mid-run.
  if (
    r.includes("connection reset") ||
    r.includes("errno") ||
    r.includes("connection closed") ||
    r.includes("timed out")
  ) {
    return "The connection dropped mid-install. Check the server is reachable and has enough memory, then try again — or open the Terminal to run it live."
  }
  // Server already has another panel / Docker / existing stack.
  if (
    r.includes("already installed") ||
    r.includes("docker is") ||
    r.includes("clean server") ||
    r.includes("fresh server")
  ) {
    return "This server isn't empty. A control panel needs a brand-new VPS — you can't run it alongside another panel or an existing web stack."
  }
  return null
}

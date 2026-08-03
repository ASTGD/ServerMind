/**
 * Has this browser shown the customer how their setup ended?
 *
 * A setup can finish in under two minutes. The moment it does, the server is "decided" and
 * its home becomes Sites — so the run the customer sat and watched ended by replacing
 * itself with an empty list, and they never saw a result. The owner's reaction on hitting
 * exactly that: "I'm really confused, was the server installed?"
 *
 * Genuinely client state: WE know the setup finished, only this browser knows whether the
 * person in front of it has been told. Storing it server-side would mean one device's
 * glance silences the news on every other.
 *
 * Every call is guarded — private browsing throws on localStorage, and a page that cannot
 * remember a dismissal must still work. Failing to remember shows the result again, which
 * is the harmless direction.
 */
const key = (setupId: string) => `serverally:setup-seen:${setupId}`

/** Remembered here too, always. Private browsing throws on localStorage, and a customer
 *  who dismissed the result should not be shown it again on the next click of the same
 *  visit — forgetting across sessions is acceptable, forgetting within one is not. */
const thisSession = new Map<string, string>()

function read(k: string): string | null {
  try {
    return globalThis.localStorage?.getItem(k) ?? thisSession.get(k) ?? null
  } catch {
    return thisSession.get(k) ?? null
  }
}

function write(k: string, v: string): void {
  thisSession.set(k, v)
  try {
    globalThis.localStorage?.setItem(k, v)
  } catch {
    /* private mode — the session map above still carries it */
  }
}

export function hasSeenSetupResult(setupId: string | null | undefined): boolean {
  return Boolean(setupId) && read(key(setupId as string)) === "1"
}

export function markSetupResultSeen(setupId: string | null | undefined): void {
  if (setupId) write(key(setupId), "1")
}

/** How long a finished run still counts as news. */
const STILL_NEWS_MS = 60 * 60 * 1000

/**
 * Should the finished run be shown instead of moving on?
 *
 * Bounded by time as well as by the acknowledgement, so a customer who wanders off without
 * clicking is not met by a completion screen for a setup they ran last month — the page
 * would have stopped being their server's home and become a receipt.
 */
export function shouldShowSetupResult(
  latest: { id: string; status: string; finished_at: string | null } | null | undefined,
  now: number = Date.now(),
): boolean {
  if (!latest || latest.status !== "done" || !latest.finished_at) return false
  if (hasSeenSetupResult(latest.id)) return false
  const age = now - new Date(latest.finished_at).getTime()
  return age >= 0 && age < STILL_NEWS_MS
}

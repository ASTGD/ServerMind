import { useMemo } from "react"

/** The minimal server shape mentions need (id + display name). */
export interface MentionServer {
  id: string
  name: string
}

/** An active @-mention being typed: `at` is the index of the "@", `query` the text
 *  between it and the caret. */
export interface MentionQuery {
  at: number
  query: string
}

// What may appear inside a mention query while the popup stays open. Letters/digits
// (any language), spaces and ._- ; no newlines; bounded so a lone "@" typed mid-
// sentence stops tracking once the user clearly moved on.
const QUERY_RE = /^[\p{L}\p{N} ._-]{0,30}$/u

/**
 * Find the @-mention being typed at the caret, if any.
 * The "@" must start a word (text start or after whitespace) — so emails and
 * ssh-style strings like root@1.2.3.4 never trigger the popup.
 */
export function findMentionQuery(text: string, caret: number): MentionQuery | null {
  const upto = text.slice(0, caret)
  const at = upto.lastIndexOf("@")
  if (at === -1) return null
  if (at > 0 && !/\s/.test(upto[at - 1])) return null
  const query = upto.slice(at + 1)
  if (!QUERY_RE.test(query)) return null
  return { at, query }
}

/** Filter servers for the mention popup — substring match, capped for the UI. */
export function matchServers(servers: MentionServer[], query: string, cap = 6): MentionServer[] {
  const q = query.trim().toLowerCase()
  const hits = q
    ? servers.filter((s) => s.name.toLowerCase().includes(q))
    : servers
  return hits.slice(0, cap)
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

/**
 * Build a case-insensitive, word-boundary regex that matches any known server name,
 * plus a name→server map. Longer names win over shorter prefixes (TestServer22 before
 * TestServer2). Shared by the chip renderer and by {@link detectServers} so "which
 * server is this message about?" uses exactly the same matching as what's highlighted.
 */
export function buildServerNameRegex(
  servers: MentionServer[],
): { re: RegExp | null; byName: Map<string, MentionServer> } {
  const named = servers.filter((s) => s.name.trim())
  if (named.length === 0) return { re: null, byName: new Map() }
  const sorted = [...named].sort((a, b) => b.name.length - a.name.length)
  const pattern = sorted.map((s) => escapeRegExp(s.name)).join("|")
  return {
    re: new RegExp(`(?<![\\p{L}\\p{N}_])(${pattern})(?![\\p{L}\\p{N}_])`, "giu"),
    byName: new Map(named.map((s) => [s.name.toLowerCase(), s])),
  }
}

/**
 * The known servers whose names appear in a message, in first-seen order, de-duplicated.
 * This is how a typed or @-mentioned name becomes a real target — same matching as the
 * chips, so what you see highlighted is exactly what gets targeted. Word-boundaried, so
 * `root@1.2.3.4` or a name inside another word never counts.
 */
export function detectServers(text: string, servers: MentionServer[]): MentionServer[] {
  const { re, byName } = buildServerNameRegex(servers)
  if (!re || !text) return []
  const found = new Map<string, MentionServer>()
  for (const m of text.matchAll(re)) {
    const s = byName.get(m[1].toLowerCase())
    if (s && !found.has(s.id)) found.set(s.id, s)
  }
  return [...found.values()]
}

/**
 * Render text with known server names highlighted as clickable chips ("show like a
 * link"). Plain-text in, spans out — never used on command/output blocks. Matching
 * is case-insensitive on word boundaries; longer names win over shorter prefixes
 * (TestServer22 before TestServer2).
 */
export function HighlightServerNames({
  text,
  servers,
  onServerClick,
  chipClassName,
}: {
  text: string
  servers: MentionServer[]
  onServerClick?: (id: string) => void
  /** Chip styling — bubbles on dark/primary backgrounds pass a lighter variant. */
  chipClassName?: string
}) {
  const { re, byName } = useMemo(() => buildServerNameRegex(servers), [servers])

  if (!re || !text) return <>{text}</>
  const parts = text.split(re)
  if (parts.length === 1) return <>{text}</>

  const chip =
    chipClassName ??
    "rounded bg-indigo-500/10 px-1 py-px font-medium text-indigo-600 dark:text-indigo-400"

  return (
    <>
      {parts.map((part, i) => {
        const server = i % 2 === 1 ? byName.get(part.toLowerCase()) : undefined
        if (!server) return <span key={i}>{part}</span>
        return (
          <button
            key={i}
            type="button"
            onClick={() => onServerClick?.(server.id)}
            title={`Talk to Ally about ${server.name}`}
            className={`${chip} ${onServerClick ? "cursor-pointer hover:underline" : "cursor-default"}`}
          >
            {part}
          </button>
        )
      })}
    </>
  )
}

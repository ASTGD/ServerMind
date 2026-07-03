/**
 * Redact secret-looking values from text BEFORE it leaves the browser as Ally context
 * ("Ask Ally about this file", Context C2). The user still sees real values in the
 * editor — but a password/key/token must never be forwarded into an AI prompt. We keep
 * the file readable (keys and structure stay) and mask only the sensitive VALUES.
 *
 * This is a best-effort, conservative filter: it errs toward over-masking. The AI layer
 * also frames file context as untrusted data, never instructions.
 */
export const SECRET_MASK = "[secret hidden]"

// Key names whose value should be hidden. Precise enough to avoid masking ordinary
// config (kept out: bare "auth", "key", "credentials" — too broad).
const SENSITIVE_KEY =
  "pass(?:word|wd|phrase)?|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|" +
  "secret[_-]?key|private[_-]?key|client[_-]?secret|auth[_-]?token"

// Standalone high-signal tokens, masked wherever they appear.
const TOKEN_PATTERNS: RegExp[] = [
  /\b(?:sk|pk|rk)-[A-Za-z0-9]{16,}\b/g, // OpenAI/Stripe-style
  /\bsm_live_[A-Za-z0-9_-]{10,}\b/g, // our own gateway token
  /\bghp_[A-Za-z0-9]{20,}\b/g, // GitHub PAT
  /\bgithub_pat_[A-Za-z0-9_]{20,}\b/g,
  /\bAKIA[0-9A-Z]{16}\b/g, // AWS access key id
  /\bxox[baprs]-[A-Za-z0-9-]{10,}\b/g, // Slack
  /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{6,}\b/g, // JWT
]

export function redactSecrets(input: string): { text: string; count: number } {
  let count = 0
  let inPem = false

  const lines = input.split("\n").map((raw) => {
    // Multi-line PEM private-key blocks → mask the body.
    if (/-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----/.test(raw)) {
      inPem = true
      count++
      return raw
    }
    if (inPem) {
      if (/-----END/.test(raw)) {
        inPem = false
        return raw
      }
      return raw.trim() ? SECRET_MASK : raw
    }

    let line = raw

    // 1) define('DB_PASSWORD', 'value')  — PHP / wp-config.php
    line = line.replace(
      new RegExp(
        `(define\\s*\\(\\s*['"][^'"]*(?:${SENSITIVE_KEY})[^'"]*['"]\\s*,\\s*['"])([^'"]+)(['"])`,
        "i",
      ),
      (_m, a: string, _v: string, b: string) => {
        count++
        return a + SECRET_MASK + b
      },
    )

    // 2) KEY=value | KEY: value | KEY => value  — env / ini / yaml / json (key stays)
    line = line.replace(
      new RegExp(
        `^(\\s*['"]?[\\w.\\- ]*(?:${SENSITIVE_KEY})[\\w.\\- ]*['"]?\\s*(?:=>|[:=])\\s*)(['"]?)([^\\n]*?)(['"]?\\s*[,;]?\\s*)$`,
        "i",
      ),
      (m, pre: string, q: string, val: string, post: string) => {
        if (!val.trim() || val.trim() === SECRET_MASK) return m
        count++
        return pre + q + SECRET_MASK + post
      },
    )

    // 3) Connection strings: scheme://user:password@host
    line = line.replace(
      /(\b[a-z][a-z0-9+.\-]*:\/\/[^\s:@/]+:)([^@\s/]+)(@)/gi,
      (_m, a: string, _p: string, c: string) => {
        count++
        return a + SECRET_MASK + c
      },
    )

    // 4) Standalone tokens anywhere on the line.
    for (const re of TOKEN_PATTERNS) {
      line = line.replace(re, () => {
        count++
        return SECRET_MASK
      })
    }

    return line
  })

  return { text: lines.join("\n"), count }
}

/**
 * A password nobody has to invent.
 *
 * Anywhere we ask a customer to make one up, they make up a weak one — and these end up on
 * database users and admin logins reachable from the internet, which scanners find within
 * the hour. So the field arrives already filled with a good one.
 *
 * Generated in the browser from crypto.getRandomValues rather than Math.random, which is
 * predictable enough to reproduce given a few outputs.
 *
 * The alphabet deliberately omits the characters people misread when copying by hand or
 * from a screenshot: l, I, 1, O and 0. Losing five characters costs almost nothing here —
 * 24 characters from a 56-character alphabet is far beyond what anyone will guess — and it
 * removes a whole class of "the password does not work" support.
 */
const ALPHABET = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"

export function strongPassword(length = 24): string {
  const bytes = new Uint32Array(length)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => ALPHABET[b % ALPHABET.length]).join("")
}

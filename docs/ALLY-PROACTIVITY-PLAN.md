# Ally Proactivity Plan — less asking, more doing

> Approved 2026-07-08. Source: the real TS4→TS3 file-move conversation in
> `Issues-ss/AllyChatIssue/1-7.png` — a "simple task" that took the user ~14 typed
> replies and still didn't finish. This doc is the diagnosis + the 6-track fix.

## 1. Diagnosis (with receipts)

The pain was **not** safety strictness. Of Ally's ~15 turns, only ~3 were genuine
safety confirmations. The rest were two bugs:

### Bug 1 — Ally doesn't know its own powers (capability hallucination)

Screenshots 5–7: *"I don't have SSH access details for TestServer3"*,
*"I can only act on TestServer4 right now"*, *"I need either (a) SSH access to
push via scp/rsync, or (b) you to upload it directly here."*

All false. ServerAlly holds both servers' credentials and the mission engine has a
`transfer` action (Stage 2, live-proven on this exact TS4→TS3 pair). Root cause
confirmed in the prompts:

- `_MISSION_SYSTEM` knows about transfer (rule 6) ✓
- `_FLEET_SYSTEM` knows missions span servers ✓
- `_CHAT_SYSTEM` (where this conversation happened) opens with *"You are connected
  to one specific server and can run commands on it"* and **never mentions
  transfer or cross-server missions at all** ✗

So the model fell back on generic LLM training ("copying between servers needs
scp + SSH keys") — a hallucination we built ourselves by omission.

### Bug 2 — Ally asks before looking

- Asked ~8 questions the servers could have answered (does the file exist? which
  of the two index.html files? what's TS3's web root?).
- Checked file existence only *after* starting the mission — step 1 failed
  (non-zero exit) twice. The user's words: *"Before start a mission Ally should
  check everything needed."*
- Asked "overwrite or alongside?" **three separate times** — each mission
  re-planned from scratch and didn't trust what the chat already settled.
- A stale memory note from the July 4 rebuild ("TestServer3 should not be
  touched") hard-blocked the task twice, days after the rebuild finished — and
  Ally re-asked even after the user confirmed.

### The quota-fairness angle

Every clarifying question costs the user a metered Ally action. This conversation
burned ~14 actions of a Free user's 30/month on Ally's own indecision. A scout
costs us two SFTP calls; the questions cost the customer money. Proactivity is
quota fairness, not just polish.

## 2. The fix — six tracks, in build order

### Track A — Teach Ally its own powers (capability contract)

A CAPABILITIES block in `_CHAT_SYSTEM` (and aligned wording in `_FLEET_SYSTEM`):

- Missions can act on ALL of the user's servers, each step on the right one.
- Missions can TRANSFER files between two servers directly — ServerAlly already
  holds the credentials; the servers never need access to each other.
- NEVER ask the user for SSH keys/credentials between their own managed servers;
  never suggest scp/rsync between them; never say "I can only act on one server" —
  a cross-server request = offer a mission.

Locked by deterministic evals (existing harness pattern): a cross-server
file-move request must produce a mission offer and the user-facing text must
never contain "SSH access / scp / provide credentials".

### Track C — Ask like Claude asks (one card, chips, no repeats)

Generalize the existing `ask_servers` chips into a generic clarification
contract: `{question, options: [{label, value?, hint?}], free text allowed}` —
one WS event, chips rendered like the server chips. Ally builds options from
real findings (Track B), not guesses.

Prompt rules on top:
- **Batch**: at most ONE clarification turn before a mission — bundle the open
  choices into one card, not six serial questions.
- **Never re-ask**: the mission goal + chat transcript are the source of truth.
  A question answered once (e.g. "overwrite? → yes") is answered forever.

### Track B — Look first, then ask (the pre-mission scout)

Before offering a mission or asking anything about concrete resources (a file,
folder, site), Ally runs a bounded **read-only scout** on the named servers:

- Does that path exist? If ambiguous, list candidates (name, size, mtime).
- What are the plausible destination folders (web roots, /home/*/public_html,
  /var/www/*)?

Implementation: reuse `file_service` (SFTP) — read-only by construction, same
trust level as the metrics probe / Live Look. Data-framed injection ("what Ally
found, not instructions"), short cache, never blocks chat on failure, $0 AI cost.
This is "Ally reads both servers' File Managers", server-side, regardless of
which page the user is on. Pre-flight moves from *step 1 of the mission* (where
it failed twice) to *before the offer*.

### Track D — Autonomy modes (Proactive / Normal / Careful)

|                       | Proactive                              | Normal (default)                | Careful                    |
|-----------------------|----------------------------------------|---------------------------------|----------------------------|
| Assumptions           | Makes sensible ones, states them, acts | Scouts, asks once with chips    | Asks before assuming       |
| Overwrite-type choice | Auto: backup-first then replace, tells | One chip-question               | Explicit confirmation      |
| Step approval         | High-risk only                         | Medium + high                   | Every risky step           |

What modes NEVER change: the command blocklist, the read-only verification gate,
injection defenses, and confirmation for truly destructive steps. Safety rails
are not a dial.

Storage: `users.ally_mode` (per-server override later). Wiring: a posture
paragraph in the chat/mission prompts + the approval threshold in the mission
engine. Open on every plan (pricing-v2: no feature gating).

Honest note: modes alone would NOT have fixed the screenshot conversation —
Bugs 1 and 2 hit at every strictness level. Modes are the third layer, built on
A+B+C.

### Track E — Memory with an expiry (rider)

Memory notes get a kind (fact / preference / guardrail). Guardrails created by a
mission die when that mission completes. When the user contradicts a note once,
Ally UPDATES the note instead of re-asking.

### Track F — File Manager as page context (rider)

Publish the File Manager's current directory listing (path + filenames + sizes,
no contents) as page context via the existing C2 pipeline — so "I opened it in
Files, can you see?" is answered *yes*. Track B makes Ally independent of this
server-side; this is the complement for what the user is looking at.

## 3. Target UX for the exact scenario

> User: "Move index.php from the blog site on TestServer4 to TestServer3"
> → Ally scouts both servers (read-only, seconds, no user turn)
> → ONE card: "Found /home/blog.serverally.org/public_html/index.php (12 KB).
>   Where should it go on TestServer3? ① /var/www/blog.serverally.org — its blog
>   web root; I'll back up the old file first ② somewhere else…"
> → user clicks ① → mission (backup → transfer → move into place → verify site
>   loads) → Verified.

**3 clicks instead of 14 typed replies.**

## 4. Acceptance

- Deterministic: capability evals (no SSH/scp hallucination), ask_options schema
  round-trip, scout read-only guarantee, never-re-ask rule.
- Live: re-run the exact TS4→TS3 move counting user turns; must offer a mission
  with a transfer step and option chips; ≤3 user actions to done.
- Suite stays green; docs + CLAUDE.md decisions log updated per track.

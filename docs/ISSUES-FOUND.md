# ServerAlly — Ally Issues Found During Live Testing

> Running log of bugs / unexpected or unwanted Ally behavior observed while testing against REAL servers and REAL tasks (not the eval harness — see `docs/EVAL-DRIVEN-DEV.md` for that).
>
> **Rule:** when live-testing and something looks wrong, do NOT fix it in place mid-task. Log it here, keep going with the actual task, fix everything after the session. See the "Live Testing — Bug Capture Protocol" section in `CLAUDE.md`.
>
> Newest entries at the top of each section. Each entry gets a sequential ID (BUG-001, BUG-002, ...) — next ID to use: **BUG-003**.

---

## Entry template

Copy this block for each new finding:

```
### BUG-XXX — <short title>
- **Date:** YYYY-MM-DD
- **Status:** Open
- **Context:** what task/session was running (e.g. "malware cleanup mission on panel2.firevps.net, site 14 of 90")
- **Server / mission:** server name + mission id/link if applicable
- **Observed:** what Ally actually did or said
- **Expected:** what it should have done instead
- **Severity:** Low / Medium / High / Critical
- **Suspected cause:** (optional — a file/service/prompt if it's obvious, else "unknown")
- **Repro:** steps to reproduce, or "not yet reproduced — only seen once live"
```

## How to close an entry

1. Reproduce it — ideally via a Dev Door dry-run (`/dev` → Prompt Inspector) so you can see the exact prompt/plan without touching a real server.
2. Fix the root cause.
3. Flip **Status** to `Fixed`, move the entry to the Fixed section, and add one line to the **Decisions Log** in `CLAUDE.md` (existing convention: date + what changed + why).
4. If it's the kind of thing that could regress, capture it as an eval case (Dev Door "capture as eval case", or add it directly to `app/evals/corpus.py`) so it's covered by the eval suite going forward.

---

## Open

_(none)_

## Fixed

### BUG-001 — Ally forgets its own prior cleanup (chat-memory cap) → nearly proposed a stale full-backup restore on a live site
- **Date:** 2026-07-15
- **Status:** Fixed (2026-07-15)
- **Context:** Live remediation on panel2.firevps.net. User asked Ally why `news.rmp.gov.bd` (a Laravel site under the `desktopit.net` account) isn't serving. The day before (Jul 14), Ally had cleaned that account and created `/home/desktopit.net/quarantine_20260714`.
- **Server / mission:** panel2.firevps.net (`0b8e62f9-83f4-4f51-a453-2b0e0f13113e`); done in **chat**, not a formal mission.
- **Observed:** Ally did not remember that *it* created `quarantine_20260714`. It said "I haven't opened any files in that quarantine folder, so I don't know yet if it's an old backup someone made, or genuine malware that got isolated." It correctly found `index.php` / `public/index.php` missing from the live docroot, but its proposed fix was to restore from `BackUp25August25.zip` — a **10-month-old** August backup — which on a live government site would roll back ~10 months of data. It treated a site it had personally worked on the day before as a cold, first-time investigation.
- **Expected:** Carry forward that it cleaned this account yesterday and created `quarantine_20260714`, recall WHAT it quarantined (only some `vendor/` webshells — not `index.php`), and reason from that: "the entry point isn't in my quarantine and the app is otherwise intact → restore only a clean `index.php`, never a stale full backup." At minimum, treat its own prior quarantine folder as its own action, not an unknown.
- **Severity:** High — on a live gov-site recovery the forgotten context pointed at a data-losing stale restore; only caught because the human + operator re-supplied the facts.
- **Root cause (confirmed):** the chat REMEMBER guidance only covered PASSIVE facts ("runs the client's shop") — it never told Ally to record the lasting ACTIONS it takes (quarantine/clean/restore), so the Jul-14 chat cleanup left no durable note, and there was no recall nudge to treat an unfamiliar quarantine folder as possibly its own work. (Missions already save a completion note; this cleanup was chat-only.)
- **Fix:** prompt/skill-level. (1) `_CHAT_SYSTEM` REMEMBER now instructs Ally to record a lasting change — especially a cleanup — as a `fact` with the exact destination PATH ("Cleaned site X: quarantined webshell → /root/quarantine_…"), plus a recall nudge: a change/folder it finds may be its OWN prior work — check memory, never propose a stale full-backup restore for a site it already cleaned. (2) The injected `WHAT ALLY REMEMBERS` block gained a bullet to reason FROM a note about a change it made. (3) Both incident skills (`security-incident.md` step 10, `security-incident-response.md` Stage 5) now instruct saving the cleanup (what + site + quarantine path) to memory so chat AND mission cleanups leave a durable record.
- **Repro / guard:** locked with three regression tests in `tests/test_ally_evals.py` — `test_chat_prompt_records_its_own_cleanup_actions`, `test_memories_block_reasons_from_own_prior_work`, `test_incident_skills_record_cleanup_to_memory`. Suite 598 pass. (Follow-up left open: a code-level auto-write of a memory note the moment a quarantine dir is created — a stronger guarantee than relying on the model to emit `remember` — and giving chat-run cleanups a durable per-server record like missions have.)

### BUG-002 — Malware scan false-positive quarantined legitimate vendor libraries → took a live Laravel gov site offline
- **Date:** 2026-07-15
- **Status:** Fixed (2026-07-15)
- **Context:** panel2.firevps.net. Yesterday (Jul 14) Ally's malware scan of the `desktopit.net` account moved **128 files** out of `news.rmp.gov.bd/vendor/` into `quarantine_20260714` — the **entire `intervention/image` package + `symfony/error-handler` assets**, all legitimate library code. Combined with a missing root `index.php`, this took the site down. Restoring `index.php` exposed a secondary crash: the Laravel/Symfony error renderer couldn't find `symfony-ghost.svg.php` (quarantined), so even the error page 500-crashed.
- **Server / mission:** panel2.firevps.net (`0b8e62f9-83f4-4f51-a453-2b0e0f13113e`); chat.
- **Observed:** The scan flagged + quarantined (1) `Intervention\Image\AbstractDecoder.php` because it contains `base64_decode()` — legit: it decodes data-URI images (`isBase64`/`initFromBinary`); (2) `symfony-ghost.svg.php` because it's a `.php` file containing SVG markup — a legit Symfony error-page asset with zero PHP logic; and ~126 other Imagick `Command`/`Shape` class files alongside them (guilt-by-directory). **0 of 128 quarantined files were actually malicious.**
- **Expected:** Never quarantine a file purely because it contains `base64_decode` (ubiquitous in legit libraries) or because a `.php` holds non-PHP content. Should (a) skip/whitelist known vendor package paths, or verify against `composer.lock`/package checksums before touching a `vendor/` file; (b) require a stronger signal than one suspicious token (obfuscation **and** user-input-into-exec); (c) never move a whole directory because one sibling matched.
- **Severity:** Critical — a false positive took a live **government** site offline for ~a day, and the damage was non-obvious (the missing entry point looked like the whole problem; the vendor damage only surfaced after `index.php` was restored).
- **Root cause (confirmed):** NOT the read-only `threat_service` scan — its webshell regex is already tight (requires `eval(base64_decode(` or user-input-into-exec). The false positives came from **Ally's chat-driven broad grep** in the `security-incident.md` first-response skill (step 5b matched a bare `base64_decode`/`eval(`/`assert(` token), and the `security-incident-response.md` cleanup mission had **no rule** stopping Ally from quarantining vendored library files (or a whole directory) on that weak signal.
- **Fix:** prompt/skill-level (matching every other Ally-behavior fix). (1) `security-incident.md` step 5b now EXCLUDES `vendor/`/`node_modules/` from the signature grep and adds a hard judging rule — one token is not proof; a real shell needs a long obfuscated blob AND/OR user input flowing into exec; never condemn a file because a sibling matched; verify against `composer.lock`/`package-lock.json`. (2) `security-incident-response.md` Stage 4 + a new PITFALL: never quarantine a `vendor/`/`node_modules/` file on a weak signal, verify against the package manifest or restore the whole tree via `composer install`/`npm ci`, one file at a time (never a whole directory), and a `.php` holding only SVG/HTML is not a shell. (3) Raised `skill_service._BODY_MAX` 11000→14000 so the fuller runbook — including the previously-truncated reboot/injection pitfalls — actually reaches the prompt.
- **Repro (deterministic):** reproduced the exact grep FP on a fake `vendor/intervention/image/AbstractDecoder.php` (`base64_decode` call) — the old grep flags it, the `-not -path "*/vendor/*"` grep clears it. **Regression guard:** two skill-content contract tests (`test_security_incident_does_not_flag_vendor_libraries`, `test_incident_response_protects_vendor_libraries` in `tests/test_ally_evals.py`) lock the rules in. Suite 596 pass.

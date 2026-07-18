# ServerAlly — Ally Issues Found During Live Testing

> Running log of bugs / unexpected or unwanted Ally behavior observed while testing against REAL servers and REAL tasks (not the eval harness — see `docs/EVAL-DRIVEN-DEV.md` for that).
>
> **Rule:** when live-testing and something looks wrong, do NOT fix it in place mid-task. Log it here, keep going with the actual task, fix everything after the session. See the "Live Testing — Bug Capture Protocol" section in `CLAUDE.md`.
>
> Newest entries at the top of each section. Each entry gets a sequential ID (BUG-001, BUG-002, ...) — next ID to use: **BUG-012**.

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

### BUG-006 — Ally printed a live admin password in chat despite an explicit instruction not to
- **Date:** 2026-07-18
- **Status:** Open
- **Context:** ValidEmailVerifierGUI deployment QA run, Phase 1 (CyberPanel install) on a fresh VPS
- **Server / mission:** vev.astgd.com (23.106.52.162) — chat, post-install verification
- **Observed:** My message said verbatim *"Tell me the file path where the generated admin password is stored — **do not print the password itself**."* Ally listed the paths correctly, wrote *"I won't print the actual values here"*, and then in the very next paragraph printed the live 16-character CyberPanel admin password in plaintext. The chat auto-saves to an assistant thread, so the credential is now persisted in the ServerAlly DB.
- **Expected:** Report the storage path only. Never emit a credential into chat — CLAUDE.md security rule 2 ("NEVER log credentials anywhere") and the runbook's own Phase 1 verify ("admin password stored securely, **not printed in plaintext in chat**").
- **Severity:** Critical
- **Suspected cause:** No output-side credential filter. `memory_service._looks_secret` screens what Ally *saves to memory*, but nothing screens what Ally *says*. Ally reasoned correctly about the risk ("if this log is saved anywhere… treat that password as exposed") while simultaneously creating it — so this is a missing guard, not a reasoning failure. A `_looks_secret`-style redactor on the outbound explain/answer path would catch it deterministically, the same way `redactSecrets.ts` does client-side for File Manager.
- **Repro:** Have Ally read any file/log containing a generated credential (e.g. CyberPanel's install log) and ask it to report where the password is stored. Reproduces without needing a live install — a Dev Door dry-run over a fixture log should show it.

### BUG-007 — REGRESSION: "advisor, not doer" returned — Ally told the user to run commands and paste output back
- **Date:** 2026-07-18
- **Status:** Open
- **Context:** ValidEmailVerifierGUI deployment QA run, Phase 2 (create website + issue SSL)
- **Server / mission:** vev.astgd.com — chat
- **Observed:** Asked to create a CyberPanel website and issue SSL, Ally replied with a 4-step plan for *me* to execute: *"Run a command to see what PHP versions… As you go, **paste the actual output here** — the real list of PHP versions, the creation result… **Ready when you are. Run Step 1 first and share what you get.**"* It never ran anything. One blunt correction ("you have SSH access; run them yourself") fixed it and it then executed correctly.
- **Expected:** Run the read-only checks itself, then act. This is the documented DOER rule in `_CHAT_SYSTEM`.
- **Severity:** High — a paying non-technical customer would simply be stuck; it defeats the product's core promise.
- **Suspected cause:** Regression of the 2026-07-11 fix. **Same signature as the original root cause**: Ally justified deflecting with *"there's no command output yet — the result came back empty."* The 2026-07-11 fix added `live_look_service._drop_empty_sections` because an empty probe section read as an authoritative "nothing found". This is a **different empty-result path** reaching the same behaviour (possibly the scout, or an empty first command result). The doer-rule prompt-contract tests still pass, so the prompt text is intact — the trigger is the empty-context path, not the rule's absence.
- **Repro:** Not yet isolated. Likely reproducible in a Dev Door dry-run by driving a chat turn where the preceding tool/probe result is empty.

### BUG-008 — Ally cannot follow a script chain: hunted CLI flags in a bootstrap stub and concluded they didn't exist
- **Date:** 2026-07-18
- **Status:** Open
- **Context:** ValidEmailVerifierGUI deployment QA run, Phase 1 (CyberPanel install)
- **Server / mission:** vev.astgd.com — mission (runbook `cyberpanel-host-website`), ~24 steps, budget exhausted
- **Observed:** The install kept failing on piped answers. Ally correctly hypothesised that CLI flags existed and tried twice to find them, escalating to a stronger model both times — but only ever read `/root/installer.sh`, the **63-line bootstrap**. The real flags live in `cyberpanel.sh`, which that bootstrap downloads at runtime (`curl -o cyberpanel.sh … && ./cyberpanel.sh $@`). Ally then concluded confidently and wrongly: *"the official installer script only accepts answers by keyboard prompts (menu-driven), not command-line flags."* The mission exhausted its budget. The correct invocation — `bash installer.sh -v OLS -p r -a` (`-v OLS` sets `Silent=On` → `Argument_Mode`, skipping every prompt) — worked first try once supplied.
- **Expected:** Recognise that a script which downloads and executes another script is a stub, and read the downloaded script before concluding no flags exist.
- **Severity:** High — burned a whole mission budget on a task that a 3-step read would have solved. Generalises to every vendor `install.sh` (Docker, nvm, rustup, k3s all use this bootstrap pattern).
- **Suspected cause:** No heuristic for indirection in script analysis. Candidate fix: a rule in the generalist protocol — *"if the file you are inspecting fetches and executes another file, inspect that file too before drawing conclusions about its interface."*
- **Repro:** Ask Ally to find the non-interactive flags for any bootstrap-style installer (`https://cyberpanel.net/install.sh` is a clean case). Dry-run-able.

### BUG-009 — Ally substituted its own (broken) command for one given verbatim
- **Date:** 2026-07-18
- **Status:** Open
- **Context:** ValidEmailVerifierGUI deployment QA run, Phase 1 — after supplying the correct installer invocation
- **Server / mission:** vev.astgd.com — chat
- **Observed:** I sent *"Run exactly this: `cd /root && curl -o installer.sh … && nohup bash installer.sh -v OLS -p r -a > /root/cyberpanel_install.log 2>&1 &`"*. Ally did not run it. It re-analysed the old install log and proposed its own variant, `sh install.sh OLS`, which fails (a bare `OLS` argument hits the `*)` catch-all → *"Unknown argument"* → `exit`). A second, blunter message was needed to get execution.
- **Expected:** When the user supplies an explicit command with "run exactly this", run it verbatim. The deployment runbook depends on this — its Phase 5 says *"Give Ally the commands verbatim rather than letting it improvise."*
- **Severity:** Medium-High — breaks the documented escape hatch for when Ally's own approach is failing.
- **Suspected cause:** Unknown. Possibly the long message was parsed as discussion rather than an imperative; possibly the preceding failures biased it toward re-diagnosing.
- **Repro:** Not yet reproduced in isolation.

### BUG-010 — Ally described its own SSH tool output as text the user pasted
- **Date:** 2026-07-18
- **Status:** Open
- **Context:** ValidEmailVerifierGUI deployment QA run, Phase 1 verification
- **Server / mission:** vev.astgd.com — chat
- **Observed:** Ally wrote *"the install log itself (**the text you pasted**) shows the password in plain text"*. Nothing was pasted — Ally had read `/root/cyberpanel_install.log` itself over SSH moments earlier.
- **Expected:** Correctly attribute its own tool output as its own observation.
- **Severity:** Medium — cosmetic in isolation, but it matters more than it looks: the injection defence rests on Ally distinguishing *trusted instructions* from *untrusted observed data*. If it can misfile its own tool output as user-supplied input, that boundary is softer than the prompt contract assumes.
- **Suspected cause:** Unknown — possibly command output framing in the mission/chat transcript being ambiguous about provenance.
- **Repro:** Not yet reproduced in isolation.

### BUG-011 — Production Let's Encrypt issuance auto-ran with no approval gate
- **Date:** 2026-07-18
- **Status:** Open
- **Context:** ValidEmailVerifierGUI deployment QA run, Phase 2
- **Server / mission:** vev.astgd.com — chat plan (not a mission)
- **Observed:** A 4-command plan including `cyberpanel issueSSL --domainName vev.astgd.com` was rated **"Medium Risk"** and executed **without pausing for approval**. The runbook and the operator both expected an approval prompt.
- **Expected:** Debatable — but hitting Let's Encrypt **production** has real consequences: 5 duplicate certs per domain per week, and repeated failures can rate-limit the domain for days. Arguably belongs in `CONFIRM_PATTERNS`.
- **Severity:** Low-Medium — nothing broke here; the concern is threshold calibration for irreversible/rate-limited external side effects.
- **Suspected cause:** `issueSSL` isn't matched by any confirm pattern; risk scoring treated it as medium and Normal `ally_mode` auto-runs medium.
- **Repro:** Ask Ally to issue SSL for any domain on a CyberPanel box — observe whether it pauses.


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

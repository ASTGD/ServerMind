# ServerAlly — Ally Issues Found During Live Testing

> Running log of bugs / unexpected or unwanted Ally behavior observed while testing against REAL servers and REAL tasks (not the eval harness — see `docs/EVAL-DRIVEN-DEV.md` for that).
>
> **Rule:** when live-testing and something looks wrong, do NOT fix it in place mid-task. Log it here, keep going with the actual task, fix everything after the session. See the "Live Testing — Bug Capture Protocol" section in `CLAUDE.md`.
>
> Newest entries at the top of each section. Each entry gets a sequential ID (BUG-001, BUG-002, ...) — next ID to use: **BUG-001**.

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

_(none yet)_

## Fixed

_(none yet)_

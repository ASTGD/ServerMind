# Update 19 — Make background work legible & safe

> Three observations from dogfooding the fleet install, all one gap: ServerMind now
> does real work in the *background* (durable installs across a fleet), but the UI
> doesn't make that state legible/safe. Why did it fail? Is this server already busy?
> What's running right now?

Planned in three independent phases:

| # | Problem | Fix | Status |
|---|---------|-----|--------|
| 1 | Failure reason buried in a terminal popup | Show the reason inline on the row | ✅ shipped |
| 2 | Re-selecting a busy server starts a duplicate install with no warning | "Installing now" badge in the picker + backend refuses duplicates | ✅ shipped |
| 3 | Dashboard "Running now" is a full-width band | Compact card in the right rail, auto-hides when empty | ✅ shipped |

## Phase 1 — failure reason inline (shipped)

The reason a run failed is the most useful thing on a failed row, yet it was the most
hidden (one click deep into a terminal log). Now it's a first-class field.

- **Backend:** `failure_reason` column on `playbook_runs` (migration 015). A shared
  `playbook_service.extract_failure_reason(output)` pulls a short, human line —
  preferring an explicit `>>> ERROR: …` (pre-flight guard) and otherwise the last
  meaningful line, collapsed to one capped line. Set on both finalize paths (the
  Celery worker and the inline WebSocket path) when status is `failed`/`stalled`.
  Returned by `POST /api/playbooks/runs/status`, `PlaybookRunOut`, and `/api/activity`.
  Existing failed runs were backfilled.
- **Frontend:** `BatchRunModal` shows the reason under each failed/stalled server row
  (red for failed, orange for stalled); the single-run banner already showed it; the
  Activity log (`Logs.tsx`) now shows it under failed items. "View log →" stays as the
  optional drill-down — the reason no longer requires opening the terminal.

Verified: the extractor produces clean reasons on real pre-flight/command failures
("CyberPanel is already installed…", "supports Ubuntu/AlmaLinux 8. Found Debian 12",
"Virtualmin needs at least 2048MB RAM"); 58 tests pass; build clean.

## Phase 2 — busy indicator + duplicate guard (shipped)

A durable background run means a server can be busy without the current screen
knowing — so starting a second identical install was easy (and collided, as a real
"Error downloading packages:" dpkg/dnf-lock failure showed). Made busy state visible
and duplicates impossible.

- **Picker (`RunPlaybookModal`):** `/api/active-runs` now exposes `playbook_id` /
  `user_script_id`. A server already running *this* playbook shows an amber
  "Installing now" badge, its checkbox is disabled, and it's excluded from the run
  count / targets. Single-run targeting picks the first non-busy selected server.
- **Backend guards (defense in depth):**
  - `run-multi` skips any selected server already running this playbook and returns
    them under `skipped` — surfaced in `BatchRunModal` as "Already running — skipped".
  - the single-run WebSocket path detects an in-progress run of the same
    playbook/script on the server and **attaches** to it instead of starting a
    second (reusing `_attach_run`).

Verified: the busy query flags an in-progress server; `/api/active-runs` exposes the
playbook id; 58 tests pass; build clean.

## Phase 3 — compact "Running now" card (shipped)

The full-width band gave transient background tasks more weight than they deserve
and looked empty with one short line. Moved it into the dashboard right rail.

- `RunningTasks` is now a compact card (`border-border bg-card`, matching the other
  rail cards) at the **top of the right column**, above Quick actions. Rows are tight
  single lines: a pulsing dot + `Title · Server` + short elapsed (`4m`) + chevron, in
  a `max-h-64` scroll area. It still **auto-hides when nothing is running**, so the
  rail collapses to Quick actions.

Verified live: with two installs in progress the card shows "Running now (2)" in the
rail with two compact rows; the full-width band is gone; build clean.

## Follow-on — actionable failures (Tier 1)

A failed control-panel install named the symptom but not the fix. Now every install
failure carries a plain-English next step:
- the pre-flight guard names the **culprit** holding port 80 (e.g. "Port 80 is already
  in use by 'litespeed'") via `ss -tlnp`;
- a frontend `failureRemedy()` maps each failure class — port/web server in use, low
  RAM, unsupported OS, mid-install connection drop, existing panel — to a "What to do"
  line shown under the reason on the batch rows, the single-run banner, and the
  Activity log.

Safe by design: it only ever *recommends* (use a fresh VPS / resize / reinstall the
OS); nothing destructive runs automatically. Guided remediation ("free port 80 by
stopping litespeed — ⚠️ deletes its sites") is the AI-assisted Tier 3, for when an AI
key is configured.

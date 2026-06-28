# Update 19 — Make background work legible & safe

> Three observations from dogfooding the fleet install, all one gap: ServerMind now
> does real work in the *background* (durable installs across a fleet), but the UI
> doesn't make that state legible/safe. Why did it fail? Is this server already busy?
> What's running right now?

Planned in three independent phases:

| # | Problem | Fix | Status |
|---|---------|-----|--------|
| 1 | Failure reason buried in a terminal popup | Show the reason inline on the row | ✅ shipped |
| 2 | Re-selecting a busy server starts a duplicate install with no warning | "Installing now" badge in the picker + backend refuses duplicates | ⏳ planned |
| 3 | Dashboard "Running now" is a full-width band | Compact card in the right rail, auto-hides when empty | ⏳ planned |

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

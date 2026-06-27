# Update 17 — Background Tasks & Notifications

> Goal: long installs run in the background (survive the window closing), you can
> rejoin a running one, get notified when it finishes, and (Phase 3) see what's
> running where. Built on the durable execution engine (Update 15).

**Status:** Phase 1 ✅ shipped · Phase 2 ✅ shipped · Phase 3 📋 planned.

## Phase 1 — Background installs + rejoin on reopen ✅
- `EXECUTION_BACKEND` now defaults to `"celery"` (durable worker). It falls back to
  inline when no worker responds, so it's safe on by default.
- `GET /api/servers/{id}/active-runs` — recent (<2h) still-running playbook/script
  runs for a server.
- `RunPlaybookModal`, on open, finds a run already in progress for this
  playbook+server and rejoins it (reusing the proven attach/replay path) — showing
  live output and preventing a duplicate start.
- **Needs a worker running** for the durable path: `celery -A app.celery_app worker`
  (or the `worker` service in docker-compose).
- Verified end-to-end on a live worker: run keeps going → active-runs finds it →
  reopen replays live output to completion.

## Phase 2 — "Done!" notifications ✅
- `notifications` table (migration 014) + `Notification` model.
- `notification_service.create_run_notification()` fires when a playbook/script run
  reaches a terminal state — wired into both the worker and inline finalize paths;
  best-effort (never breaks a run).
- `GET /api/notifications` (recent + unread count); `POST /api/notifications/read-all`.
- Frontend: a **bell** in the top bar — unread badge, dropdown list (status icon +
  title + relative time), polls every 30s + on window focus, marks read on open,
  click → the relevant server.
- Verified: a finished run creates a notification ("Playbook finished — on TestServer")
  and the unread count reflects it.

## Phase 3 — Running-tasks dashboard 📋 PLANNED
- A live panel of what's running on which server, with click-through to the live log.
  Builds on `/active-runs` (extended across all the user's servers) + the durable run
  log. Medium.

## Later / optional
- Browser push + email notifications (extends Phase 2).
- Notifications for AI-chat runs (currently playbook/script runs only).
- Reconnect-to-running after a full browser restart (persist the active run id
  client-side, not just within an open window).

# Update 18 — Fleet Install (run a playbook on many servers at once)

> Goal: from a playbook's run screen, select multiple servers and install on all of
> them at once. Built on the durable engine (Update 15) + background tasks (Update
> 17) — each server is just an independent background run, so most of this was free.

**Status:** ✅ shipped (same variables for all; per-server customization later).

## How it works
- The run screen's server picker is now a **multi-select** (official playbooks only;
  user scripts stay single-server). Pick 2+ → the button reads "Run on N servers".
- `POST /api/playbooks/{id}/run-multi` `{server_ids, variables}` → creates one durable
  background run per server (the same rendered script + variables, picking
  bash/PowerShell per server's OS), enqueues each to the worker, returns the run ids.
  Guardrail: **max 25** at once; confirm above 10.
- The screen switches to a **batch view** (`BatchRunModal`): one row per server with
  live status (Installing… / Done / Failed / Stopped), polling `POST
  /api/playbooks/runs/status`; click a row → `RunLogModal` (that server's live log).
- Everything else is free: each run is **durable** (survives closing the window),
  shows in the Dashboard "Running now" panel, and fires its own completion
  notification.
- **Needs a worker running** (the durable path). One worker with enough lanes runs
  the whole fleet in parallel — no need for multiple workers:
  `celery -A app.celery_app worker --concurrency=10`.

## Verified
- `run-multi` creates one running PlaybookRun per server with the correct playbook +
  variables; `runs/status` returns each run's status; the single-server flow is
  untouched. 58 tests pass; build clean.

## Later
- **Per-server variables** (e.g. a unique hostname/FQDN per server) — currently the
  same values apply to all.
- Fleet runs for saved **user scripts** (currently official playbooks only).
- **"Retry failed only"** action from the batch view.

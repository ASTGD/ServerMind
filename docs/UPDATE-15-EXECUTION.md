# Update 15 — Resilient Execution Engine

> Goal: move long-running command/playbook execution off the web event loop onto
> durable Celery workers with Redis pub/sub streaming, so a run survives client
> disconnects, web restarts, and server reboots — and the web tier can scale.

## Architecture
- A **Celery worker** (broker + result backend = Redis) executes the run.
- Output is published to a Redis **pub/sub** channel `run:{run_id}`; the final
  state is persisted to the `playbook_runs` row.
- The **WebSocket handler is a subscriber**: it authenticates, creates the run
  record, subscribes to the channel, enqueues the task, then relays output to the
  browser. If the client drops, the worker keeps running.

## Safe rollout — `EXECUTION_BACKEND` flag
- `inline` (**default**) — runs in the web process, no worker needed, behavior
  unchanged.
- `celery` — durable worker path. Set the flag **and run a worker** to use it.

## Run a worker
```bash
cd backend && source venv/bin/activate
celery -A app.celery_app worker --loglevel=info
```

## Slice 1 — shipped
Playbook runs (`/ws/playbook-run`) execute via Celery + Redis pub/sub, behind the flag.
- `app/celery_app.py` — the Celery app (Redis broker/backend, JSON serializer).
- `app/workers/playbook_tasks.py` — `run_playbook` task → `_execute()` streams
  output to Redis and persists `status`/`output`/`completed_at`. A fresh Redis
  client per task (each task gets its own event loop).
- `websocket/terminal.py` — `_relay_celery_run()` subscribes **before** enqueuing
  (so no early output is missed), then relays until `complete`.
- **Verified:** `_execute` against a live VPS streams to Redis + persists
  success/failed; a `.delay()` → background-worker round-trip ran end-to-end and
  updated the run row; 52 unit tests still green; default-inline path unchanged.

## Slice 2 — shipped (reconnect-to-running)
The worker now appends each output message to a Redis **list** `run:{run_id}:log`
(TTL `EXECUTION_LOG_TTL`, default 1h) rather than fire-and-forget pub/sub. The WS
**tails the list** (`_stream_run_log`) — fresh runs and reconnects use the same
path: a reconnecting client replays from the start of the buffered log, then
follows live appends. Falls back to the DB-stored result if the log expired or the
worker died.
- New WS message `{type:"attach", run_id}` resumes an existing run on the same
  server (`_attach_run`, access-checked against the connection's server).
- Frontend (`RunPlaybookModal`): on a mid-run socket drop it auto-reconnects and
  re-attaches by `run_id` (up to 5 tries, 1.5s apart), so a Wi-Fi/LAN blip doesn't
  lose a long install — the worker keeps going and the client re-syncs.
- Verified on a live VPS: list replay (output + complete) **and** DB-fallback
  after log expiry both reproduce the full run; default-inline path unchanged.

## Remaining slices
- AI-chat command execution and the interactive terminal over the same model.
- `run_count` increment + richer run metadata on the celery path.
- Worker in `docker-compose` / prod (DEPLOY.md); horizontal web scaling with
  `ENABLE_SCHEDULER` on a single process.
- Run **cancellation** (signal/revoke the task) and per-run resource limits.

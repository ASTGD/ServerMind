# Update 15 — Resilient Execution Engine

> Goal: move long-running command/playbook execution off the web event loop onto
> durable Celery workers with Redis pub/sub streaming, so a run survives client
> disconnects, web restarts, and server reboots — and the web tier can scale.

## Architecture
- A **Celery worker** (broker + result backend = Redis) executes the run.
- Each output message is appended to a Redis **list** `run:{run_id}:log` (a
  replayable backlog with a TTL); the final state is persisted to the DB row
  (`playbook_runs` for playbooks, `command_logs` for chat).
- The **WebSocket handler tails that list**: it authenticates, creates the run
  record, enqueues the task, then replays + live-tails the log to the browser. If
  the client drops the worker keeps running and persists; a reconnecting client
  replays from the log (or the DB once it has expired).

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

## Slice 3 — shipped (cancellation)
A user can stop a running install. Cancellation goes over a separate **HTTP
endpoint** (the streaming WS is busy sending, not receiving):
`POST /api/playbooks/runs/{run_id}/cancel` (execute-access checked) sets a Redis
flag `run:{run_id}:cancel`, marks the run `cancelled`, and emits a final
`complete` to the run log so the tailing WS resolves immediately. **Both**
executors — the celery worker `_execute` and the inline WS loop — check the flag
each output line and stop. Frontend: the run modal's primary button becomes
**Stop** while running, plus a distinct amber `cancelled` state.
- Verified on a live VPS: a baseline run completes `success` (5/5 lines); with the
  flag set mid-run the executor stops early and the run ends `cancelled`.
- Known limits (follow-ups): the remote process isn't force-killed — we stop
  streaming and mark cancelled (could send a kill over SSH); the per-line flag
  check means a fully-silent command is only interrupted when it next prints,
  though the HTTP endpoint resolves the UI immediately regardless.

## Slice 4 — shipped (durable AI chat execution)
AI chat — the headline NL flow — now runs its command execution on the same
durable rails as playbooks. Planning, safety validation, and approval stay in the
web process; once approved, the chat WS (when `EXECUTION_BACKEND=celery`) creates
the CommandLog up front (`status=running`), sends `run_started` with its id,
enqueues `run_chat` (`_execute_chat`), and tails the log via `_stream_chat_log`.
- The worker emits the **same** protocol the inline path does — `command_start` /
  `output` / `command_done` / `execution_complete` — so the chat UI needed no
  changes for durability; it just streams from the worker instead.
- Cancellable: `POST /api/commands/{log_id}/cancel` sets the flag, marks the log
  cancelled, and emits `execution_complete`; the worker honours the flag per
  command and per line. The chat UI shows a **Stop** button while a run is live
  (keyed off the `run_started` log id).
- `_stream_run_log` was generalised into `_tail_log(terminal_types, finished)` so
  the playbook (`complete`) and chat (`execution_complete`) tails share one loop,
  with the DB-fallback resolving from PlaybookRun or CommandLog. (Also fixed: the
  playbook fallback now recognises the `cancelled` terminal status.)
- Verified on a live VPS: a 2-command plan streams the full protocol and persists
  `success` + an explanation; a pre-set cancel flag yields `cancelled`; the tail
  replays live and falls back to the DB after the log expires.

## Remaining slices
- The interactive terminal (`/ws/terminal`) over the durable model; chat
  reconnect-to-running from the UI.
- `run_count` increment + richer run metadata on the celery path.
- Worker in `docker-compose` / prod (DEPLOY.md); horizontal web scaling with
  `ENABLE_SCHEDULER` on a single process.
- Force-kill the remote process on cancel; per-run resource limits.

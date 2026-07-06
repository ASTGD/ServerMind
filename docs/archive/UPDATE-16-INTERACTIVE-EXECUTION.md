# Update 16 — Interactive Execution (Smart SSH Agent)

> **Goal:** an install can never freeze silently. First make a stuck install fail
> *clearly* (Phase A), then let the app run installs through a real interactive
> session that auto-answers safe questions, pauses to ask the user for the rest,
> and keeps the chat usable alongside (Phase B).
>
> Solves **Risk 1** from the server-connection audit. Scenario 3 from the concept
> (changing the plan mid-install) is explicitly **out of scope** here — see §7.

**Status:** Phase A ✅ shipped · Phase B 📋 planned · Phase C 🔭 deferred. This doc
is the living roadmap — Phases B and C are retained here as the plan of record for
when we pick them up.

---

## 0. Plain-English summary (for the PM)

Today the app runs an install "fire-and-forget": it starts it, watches the output
go by, and waits for it to finish. If the install stops to ask a question, the app
can't answer, so it waits forever and the screen looks frozen.

- **Phase A** puts a stopwatch on every install. If it goes silent too long, the
  app stops it and says clearly *"this got stuck — here's the last thing it
  showed."* No more frozen-forever screens. **(~3 days.)**
- **Phase B** upgrades installs to a real two-way session. The app can type back:
  it auto-answers safe yes/no questions, and for real questions ("what domain?")
  it pauses and asks you in chat, then continues with your answer — all while you
  can still chat normally. **(~3–4 weeks, built in 5 small steps.)**

Both reuse the "keep-the-job-alive" engine we just built (Update 15), so we're
extending, not starting over.

---

## 1. How execution works today (the starting point)

- **Linux commands** run through `backend/app/services/ssh_service.py`:
  - `execute_stream(...)` opens a channel, runs the command with
    `channel.exec_command(command)` (**no terminal attached, no way to type
    back**), streams output lines, and raises `CommandError` on a non-zero exit.
    This is what AI chat and playbooks use today.
  - `open_shell(...)` already opens a **real interactive terminal** (`get_pty` +
    `invoke_shell`) — this is the manual Terminal page. **Phase B builds on this.**
- **Durable engine (Update 15)** — `backend/app/workers/playbook_tasks.py`:
  - A Celery worker runs the job, appends each output message to a Redis list
    `run:{id}:log` (via `_emit`), and persists the final result.
  - A WebSocket *tails* that log (`_tail_log` in `backend/app/websocket/terminal.py`).
  - A cancel flag `run:{id}:cancel` stops a run. Behind `EXECUTION_BACKEND=celery`.
- **The gap:** the streaming path is one-way (read only) and non-interactive.
  Nothing can answer a prompt, and nothing stops a silent hang.

---

## 2. Phase A — Stop the freeze ✅ SHIPPED

**Outcome:** a stuck install becomes a clear, honest failure instead of a frozen
screen. ~80% of Risk 1 removed for a fraction of Phase B's cost.

> **Shipped.** Watchdog (idle + max-runtime) in `ssh_service.execute_stream` raising
> `CommandStalled` with the captured output tail; all four execution paths (inline
> + worker, playbook + chat) catch it, show a clear note, set status `stalled`, and
> stop remaining steps; the run modal shows an amber "Stopped responding" state;
> non-interactive env preamble injected into every bash playbook. Verified on a
> live VPS (stalls on real silence, no false-stall on output-every-1s) + 2 unit
> tests. **Note:** existing seeded playbooks need a resync to pick up the
> non-interactive preamble (the watchdog applies to all runs immediately).

### 2.1 Idle + max-runtime watchdog
Add two timers to the streaming loop in `ssh_service.execute_stream` (and the
WinRM equivalent):
- **Idle timeout** — if no output for `SSH_IDLE_TIMEOUT_SECONDS` *and* the command
  hasn't exited, treat it as stuck.
- **Hard ceiling** — if total runtime exceeds `SSH_MAX_RUNTIME_SECONDS`, stop.
- On either, close the channel and raise a new `CommandStalled(last_output)`
  exception carrying the **last ~1 KB of output** (so the user sees what it was
  stuck on, e.g. the unanswered question).

> ⚠️ Real-world tuning: control-panel installs run ~40 min and have legitimately
> quiet stretches (downloads, compiles). Default idle to **300s (5 min)**, make it
> configurable, and let a playbook raise it via its `est_runtime_sec`. Max-runtime
> default **3600s (60 min)**. These are conservative on purpose — better a rare
> late catch than killing a slow-but-healthy install.

### 2.2 Non-interactive by design
Reduce how often a prompt appears at all:
- Run commands with a non-interactive environment preamble
  (`DEBIAN_FRONTEND=noninteractive`, default-yes flags). Implement as a wrapper in
  `playbook_service.py` alongside the existing `_ensure_docker` / `_preflight`
  helpers, applied to playbook scripts.
- Update the AI planning prompt in `ai_service.plan_commands` to prefer
  non-interactive flags (`apt-get -y`, `-q`, etc.).

### 2.3 Surface it clearly
- Catch `CommandStalled` in both execution paths (`terminal.py` chat loop and
  `playbook_tasks.py` `_execute` / `_execute_chat`); emit a `stalled` message with
  the captured tail; set run status to **`stalled`** (new).
- Frontend (`RunPlaybookModal`, `ChatWindow`): a distinct amber **"Stopped
  responding"** state — *"This install went quiet for 5 minutes and may be waiting
  for an answer we couldn't provide. Nothing was broken. You can try again, or run
  it in the Terminal to answer by hand."* Show the captured last output.

### 2.4 Phase A — files, config, tests

| Area | Change |
|---|---|
| `ssh_service.py` | idle + max watchdog in the stream thread; new `CommandStalled` |
| `winrm_service.py` | idle watchdog parity (can ship slightly later) |
| `config.py` | `SSH_IDLE_TIMEOUT_SECONDS=300`, `SSH_MAX_RUNTIME_SECONDS=3600` |
| `terminal.py`, `playbook_tasks.py` | catch `CommandStalled` → emit `stalled`, set status |
| `playbook_service.py` | non-interactive env preamble helper |
| `ai_service.py` | prompt: prefer non-interactive flags |
| Frontend modal + chat | `stalled` UI state + captured tail |
| New WS message | `{ "type": "stalled", "last_output": "…", "run_id": "…" }` |

**Tests:** a silent command (`sleep 600`, no output) stalls after the idle timeout;
a normal command never false-stalls; a slow-but-chatty command (prints every few
seconds) never stalls; max-runtime ceiling fires; stalled status persists and the
UI shows the tail.

**Size: Medium (~3 days).** No architecture change; mostly timers + a new status +
UI state.

---

## 3. Phase B — Smart answers (interactive session) 📋 PLANNED (future)

**Outcome:** installs run through a real two-way session. The app auto-answers safe
questions, pauses and asks the user for real input, and the chat stays usable —
all durable (survives disconnects) like the rest of Update 15.

### 3.1 The shift: an interactive agent in the worker
For interactive runs, replace the one-way `exec_command` stream with a **PTY shell
session** (the `open_shell` mechanism) driven by the worker:
1. Open a PTY shell; send the command.
2. Continuously read output → stream to the user (existing `_emit` → log).
3. Watch the output for a prompt (§3.3).
4. On a prompt: classify → **auto-answer** (safe allow-list) or **pause and ask the
   user**.
5. Read the user's answer from a shared inbox (§3.2) and type it into the session.
6. Detect completion via a **sentinel**: after the command, echo a unique marker +
   `$?`; seeing the marker means done, and gives the real exit code. (A PTY shell
   doesn't hand back a clean exit code like `exec_command` does — this is the
   standard `expect`/`pexpect` technique and a key implementation detail.)

This lives in a new worker path `_execute_interactive` and a new
`backend/app/services/interactive_service.py` (the managed PTY runner). Gated by a
flag so the existing paths are untouched.

### 3.2 How the agent and chat share state (the "whiteboard")
One worker does the work; the chat talks to the user; they share Redis (the same
store we already use for the run log). Per run:

| Redis key | Direction | Purpose |
|---|---|---|
| `run:{id}:log` | agent → user | output stream (**exists**) |
| `run:{id}:input` | user → agent | answers the user provides (**new**) |
| `run:{id}:cancel` | user → agent | stop (**exists**) |
| run status (DB + log) | shared | `running` / `awaiting_input` / `stalled` / … |

The agent, when it needs input, **blocks reading `run:{id}:input`** with a timeout
(= Phase A idle limit, so an unanswered prompt still fails clearly).

### 3.3 Prompt detection (the hard core — three layers)
1. **Pattern library** (`prompt_detector.py`, new) — regexes for common prompts,
   each tagged: `safe_confirm` (e.g. `[Y/n]`, `Do you want to continue?`),
   `needs_input` (`Enter … :`, `… name:`), `secret` (`password:`), `dangerous`
   (`overwrite?`, default-no `[y/N]` on destructive actions).
2. **Idle + no-newline heuristic** — output stops for a *short* window (2–5s) and
   the last line has no trailing newline and the shell hasn't returned → likely a
   prompt. (This short window sits *well below* Phase A's 5-min stall net.)
3. **AI fallback** — on a short idle with text we don't recognise, send the last
   few lines to `ai_service.detect_prompt(...)` (new) → structured
   `{ waiting, question, classification, suggested_answer }`. Handles unknown
   prompts; costs one AI round-trip, only on the unrecognised + idle case.

> Honest caveat to bake into expectations: detection is **educated guessing**. It
> will sometimes misread a slow step as a question, or miss an oddly-worded prompt.
> That's why Phase A's watchdog and the conservative auto-answer policy (§3.4) are
> non-negotiable backstops.

### 3.4 Auto-answer safety policy (must-have)
- Only patterns on a **curated `safe_confirm` allow-list** are auto-answered
  (`y` / Enter). Everything else → **ask the user**.
- `dangerous` and `unknown` → **never auto-answer**, always ask.
- `secret` (passwords) → ask the user, **mask** it, **never** write it to the log
  or history (reuse the no-plaintext-credentials rule).
- Cross-check the proposed answer against `safety_service` (a "yes" that triggers a
  destructive action is blocked).
- Every auto-answer is shown live (`→ answered: yes`) and recorded for audit.

### 3.5 The pause-and-ask flow (Scenario 2)
1. Agent detects `needs_input` → emits `awaiting_input` (with the question + a
   `mask` flag) and sets status `awaiting_input`.
2. UI shows an inline box: *"The server is asking: 'Enter your domain name:' —
   what should I send?"*
3. User answers → `POST /api/runs/{run_id}/input` (access-checked, need-execute) →
   pushed to `run:{id}:input`.
4. Agent reads it, types it into the session, resumes. No answer within the timeout
   → `stalled` (Phase A net).

### 3.6 Chat alongside (Scenario 4)
Already mostly true on the durable engine (chat WS and the run are independent).
Phase B formalises it: the chat handler can **read the run's state** (status,
elapsed, recent log) to answer *"how long will this take?"* without touching the
agent.

### 3.7 Phase B — files, endpoints, migration, messages

| Area | Change |
|---|---|
| `interactive_service.py` (new) | PTY-driven agent: read/write stdin, sentinel-based completion + exit code |
| `prompt_detector.py` (new) | pattern library + classification + idle/no-newline heuristic |
| `ai_service.py` | `detect_prompt(output_tail, context)` + new prompt template |
| `safety_service.py` | `classify_prompt_answer(...)` — is auto-answering this safe? |
| `playbook_tasks.py` | new `_execute_interactive` worker path + `run:{id}:input` inbox |
| `terminal.py` | relay `awaiting_input`; chat answers status from run state |
| New endpoint | `POST /api/runs/{run_id}/input` (provide an answer) |
| New WS messages | `awaiting_input` (server→client), auto-answer notices |
| Migration | new statuses `awaiting_input` / `stalled`; optional `interactive_events` JSON on the run/log for the Q&A audit trail |
| Frontend | run modal + chat: awaiting-input box, masked password input, inline auto-answer notes |
| `config.py` | `INTERACTIVE_EXECUTION_ENABLED`, idle-prompt window, AI-detection toggle |

### 3.8 Build B in 5 small steps (each shippable)
| Step | Delivers | Size |
|---|---|---|
| **B1** | Interactive PTY runner + sentinel completion (foundation) | ~3–4 days |
| **B2** | Pattern detection + safe auto-answer (Scenario 1) | ~2–3 days |
| **B3** | Pause-and-ask + input endpoint + UI (Scenario 2) | ~3–4 days |
| **B4** | AI fallback for unknown prompts | ~2 days |
| **B5** | Chat answers status questions from run state (Scenario 4) | ~1 day |

**Size: Large (~3–4 weeks total).** B1 is the riskiest (interactive completion
detection is fiddly); B2–B3 are the user-visible payoff.

---

## 4. Tests (Phase B)
- Pattern detection classifies known prompts correctly (safe / needs-input /
  dangerous / secret).
- A `[Y/n]` is auto-answered; a destructive `[y/N]` is **not** — it asks the user.
- Pause-and-ask: a `needs_input` prompt pauses; the input endpoint delivers the
  answer; the session resumes.
- No answer within the timeout → `stalled`.
- Password prompt: asked, masked, **never** in the log/history.
- AI fallback (mocked) classifies an unknown prompt.
- Completion detection: the session ends cleanly with the correct exit code.
- Safety: never auto-answers a blocklisted/destructive prompt.
- Durability: client disconnects while `awaiting_input` → agent keeps waiting;
  reconnect shows the awaiting-input state (reuses Update 15 reconnect).

---

## 5. Rollout & flags
- Interactive execution is **opt-in** behind `INTERACTIVE_EXECUTION_ENABLED` and
  runs on the **durable (Celery) path** — consistent with `EXECUTION_BACKEND`. The
  current non-interactive path stays the default until proven.
- Phase A ships **independently and first** (it's valuable even without Phase B).

## 6. Safety summary (because we're acting on a live server)
- Conservative auto-answer allow-list; destructive/unknown always ask the user.
- Passwords masked, never logged (existing credential rule).
- Every auto-answer audited in history.
- Phase A watchdog is the hard backstop against any detection miss.

## 7. Phase C — change the plan mid-install 🔭 DEFERRED (future)
- **Scenario 3 — change the plan mid-install.** Installs are a row of dominoes and
  most run as one script; cleanly "skipping a step" needs installs rebuilt as
  separate, resumable, dependency-aware steps. That's a much larger effort and a
  half-configured-server risk. Revisit only after A + B are proven and customers
  ask. (Very Hard.)

## 8. Open decisions to confirm before building
1. **Idle-timeout default** — 5 min reasonable, or do your installs have longer
   quiet stretches?
2. **Ship Phase A alone first?** (Recommended — fast win, no architecture change.)
3. **AI-detection cost** — OK to spend one AI call per *unknown* prompt for smarter
   handling, or keep Phase B pattern-only at first?
4. **Auto-answer appetite** — start ultra-conservative (auto-answer only the 3–4
   safest confirmations, ask for everything else)?

---

## 9. Cost at a glance
| | Solves | Size |
|---|---|---|
| **Phase A** | ~80% of Risk 1 (no more frozen-forever) | **Medium — ~3 days** |
| **Phase B** | Smart two-way installs (Scenarios 1, 2, 4) | **Large — ~3–4 weeks (5 steps)** |
| Scenario 3 | Mid-install re-planning | **Deferred — Very Hard** |

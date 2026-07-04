# Ally Missions — the agentic ops loop

> **Status: Phase 1 SHIPPED (2026-07-03).** A *mission* is a multi-step job Ally works
> autonomously on ONE server — approve once, then Ally loops *plan a step → run it →
> read the output → plan the next step* until done, blocked, stopped, or out of budget.
> This is the engine behind "ops skills" like deploying a GitHub repo. Companion to
> the skills system (`backend/app/skills/`) and [AI-METERING.md](AI-METERING.md).

---

## 1. Why an engine, not just a skill

A normal chat turn produces ONE plan up front. Jobs like "host this GitHub repo" can't
be planned up front: what's inside the repo (Node? PHP? static?) decides every later
step. The mission loop lets Ally adapt to what it discovers — the defining property of
an agent. Deliberately **one agent, no swarm**: server ops is sequential work on one
box; a multi-agent hierarchy would multiply cost (we meter tokens) and failure modes
without adding speed. The only real parallel case (same action, many servers) is
already covered by the batch runner.

## 2. Lifecycle

```
user message ("host github.com/x/y on mysite.com")
  → normal chat planning; a mission-mode skill hint may be injected
  → Ally replies with a MISSION OFFER (goal, no commands)
  → user clicks Start (the single mission-level approval)
  → loop (≤ 20 steps):
      plan ONE next step (goal + runbook + steps-so-far transcript + last outputs)
      → safety-validate the command (same blocklist as everything else)
          blocked → the block is fed back into the transcript; Ally adapts
      → risky/confirm-flagged step → PAUSE, ask the user (approve / cancel)
      → execute, capture output (tail kept in the transcript)
  → ends as: done (summary) | blocked (reason + what the user must do)
             | stopped (user) | budget exhausted
```

## 3. Rules (the contract)

- **One mission at a time, one action per step.** Small steps keep the
  observe→decide granularity right and every step individually reviewable.
- **Cross-server (Stage 2, 2026-07-03):** every step carries a `server_id` resolved
  against the user's **executable roster** (every server they hold `can_execute` on,
  hosting-panel connections excluded, capped at 15 in the prompt). An id the model
  invents falls back to the home server or fails the step — it can never touch a
  server outside the roster. Safety validates each command against the TARGET's OS.
- **Transfer steps (Stage 2):** `action: "transfer"` copies ONE file between two
  roster SSH servers **through the backend** (SFTP both ways) — the servers never
  hold credentials for each other. Guards: absolute paths, 512 MB cap, never
  overwrites an existing destination, refuses directories (tar first). The step shows
  as `transfer A:/path → B:/path` with an `A → B` badge.
- **Step budget: 20.** Hitting it ends the mission honestly ("ran out of steps") with
  the transcript so far. No silent continuation.
- **Safety is per step, not per mission.** Every command passes `safety_service`;
  `requires_confirmation`/high-risk steps pause for the user even mid-mission. The
  mission-level "Start" never pre-approves a risky command.
- **Stop button** takes effect between steps (a long-running step finishes first —
  v1 semantics, shown in the UI).
- **Disconnect = mission ends** between steps (v1 runs inside the chat WebSocket;
  durable/resumable missions are Phase 2).
- **Hosting-mode guard:** panel-API connections (`connection_type='hosting'`) can't
  run shell steps — mission start is refused with a plain explanation (connect the
  same box over SSH).
- **Outputs are data.** Step outputs enter the transcript as observations (truncated
  tails), never as instructions — same injection discipline as everywhere else.
- **Memory:** a completed mission may save one server-scoped note (what was deployed,
  where) via the existing secret-filtered memory path.

## 4. Metering (see AI-METERING.md §2)

A mission charges **1 action** at start; every model call it makes is ledgered with
`feature="mission"` and the skill tag, so we learn the true token cost per mission from
real data. If missions prove expensive, pricing may later count them differently (e.g.
Pro-only or N actions) — decide from ledger data, not guesses.

## 5. Ops skills (mission runbooks)

A skill with `mode: mission` in its frontmatter is a **runbook**: staged procedure,
per-stack decision tables, pitfalls, verify steps. It is NOT injected into normal
chat planning; instead its presence makes chat *offer a mission*, and the full runbook
is injected into every step-planning call of the mission itself. First runbook:
**github-deploy** (detect stack → create site (panel-aware) → clone → build → wire →
SSL → verify → leave a redeploy path).

## 6. One socket, mission offers from anywhere (Stage 2)

`/ws/chat` is now THE Ally socket: each `message`/`mission_start` frame may carry a
`server_id`, with execute-access resolved **per message** (Rule 7 enforced; email
verification honored). Fleet-scoped messages (no id) take the advisory path, which
can now offer missions too (`"mission": {goal, server}` in the fleet contract — the
home server matched by name like handoffs, or null for a pure fleet mission).
A pending plan's approval binds server-side to ITS server — switching the drawer
target can never redirect an approval — and a running mission keeps streaming to the
same conversation. A new user message arriving where approve/cancel was expected
cancels the pending plan and is handed back to the loop, never swallowed. The
per-server endpoint `/ws/chat/{id}` remains as a pinned-target alias (ServerDetail
chat tab / older clients). Billing: home-server owner's pool, or the acting user's
own pool for fleet missions.

Live-verified (2026-07-03): "Take a backup of the WordPress database on TestServer4
and move the backup file to TestServer3" as ONE fleet instruction → 7 steps: locate
WordPress (TS4) → read config w/o exposing the password → mysqldump via a temp cnf →
compress → **transfer TS4→TS3 (23,766 bytes)** → verify on TS3 → done.

## 7. Verification gate (never trust a self-declared "done")

A mission that *says* it is done is not proof it *is* done — a model can claim
success while a goal is still unmet (we hit exactly this: an incident-response
mission reported the server clean while a rogue cron was still live). So the
engine does not accept `status:"done"` on trust. When the executor declares done,
an **independent, adversarial verifier** runs before success is reported:

1. `ai_service.verify_mission` (a distinct prompt/role from the executor) is asked:
   *what fresh evidence would PROVE this goal is met?* It returns read-only
   `checks[]` and/or a `verdict`.
2. `_verify_mission_complete` runs those checks — **strictly read-only**, enforced
   by `safety_service.is_read_only_command` (default-deny: any mutating token →
   skipped, never executed; a verification pass may only OBSERVE). They stream to
   the UI with a `verifying` badge and are appended to the transcript.
3. The verifier renders a final verdict on the fresh evidence:
   - `confirmed` → `mission_complete` with `verified:true` + what it checked.
   - `unverified` → the executor gets a **bounded** chance to close the gap the
     verifier named (fed back as an observation; `_VERIFY_MAX_ATTEMPTS`); if it
     still can't be proven, the mission finishes **honestly** with `verified:false`
     + a caveat — an honest non-success, **never a false green**.

Bounds: ≤ `_VERIFY_ROUNDS` gather↔verdict cycles × `_VERIFY_MAX_CHECKS` checks,
≤ `_VERIFY_MAX_ATTEMPTS` re-loops. Verification steps do **not** count against the
executor's `_MISSION_BUDGET` (verifying must never be what exhausts a mission).
Best-effort: any verifier error resolves to `unverified` (safe), never a crash.
A `confirmed` verdict is required before a mission may leave a memory note.

Tests: `tests/test_mission_verification.py` (engine branching + the read-only
guarantee — a mutating "check" is never executed) and the read-only corpus in
`tests/ally_eval_corpus.py`; live: `test_ally_evals_live.py` asserts the real
verifier refuses to confirm an unmet goal.

## 8. Budgets & long-running work

A mission runs at most `budget` steps. Ad-hoc missions use `MISSION_BUDGET_DEFAULT`
(20); a **mission-mode skill may declare its own** `budget:` in frontmatter,
clamped to `[10, 40]` (a deep investigation or multi-stage install needs more than
a quick fix — but no skill can remove the bound). Set today: security-incident-
response 30, cyberpanel-host-website 25, github-deploy 25.

What does **not** count against that budget:
- **Verification checks** (§7) — verifying must never be what exhausts a mission.
- **`wait` steps** — a mission polls a long-running background job (install
  finishing, a service coming up) with `action:"wait"` (`seconds`, ≤5 min each).
  The prompt tells the executor to launch slow work in the background
  (`nohup … > log 2>&1 &`) and `wait`-poll instead of blocking one command for
  minutes (which risks the SSH idle-watchdog and hides progress). Waits are bounded
  so a mission can never hang: ≤5 min each, ≤1 h and ≤60 waits total; a Stop takes
  effect mid-wait. Bounding logic is the pure, tested `_wait_plan`.

The prompt also nudges the executor to be economical — combine related read-only
checks into one command, and converge (stop exploring, finish) as the budget shrinks.

## 9. Phase 3 (not built)

Durable missions (survive disconnects, Celery), resume after a blocked step, a
mission history page, webhook-triggered redeploys, mission templates from the
community, missions-in-parallel across servers via the batch pattern.

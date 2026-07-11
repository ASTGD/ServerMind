# Eval-Driven Development & the Dev Door — Engineering Plan

**Status:** ✅ SHIPPED (Phases 0–5), 2026-07-12 · **Author:** AI-engineering pass, 2026-07-11
**Builds on:** [ALLY-EVALS.md](ALLY-EVALS.md) (the existing regression harness).

> **Shipped:** the admin-only Dev Door at `/dev` with three tabs — **Prompt Inspector**
> (dry-run a message, see the exact prompt/output/cost, never executes), **Evals** (run the
> corpus + captured cases offline; capture a bug as a red test in one click), and **Activity**
> (the AI ledger: cost, model ladder, recent calls). Backed by the `app/evals` engine
> (corpus = data, one runner) shared by pytest, the CLI (`python -m app.evals run`), and the
> UI; an LLM `judge()` for soft-quality evals; and a CI eval gate. `is_admin` gates every
> `/api/dev/*` route; dry-run plans but never executes. **Deferred (stretch):** A/B prompt
> variants, and auto-drafting eval cases from ledger failure patterns.

## 1. The goal, in one line

> Make **changing Ally's behavior safe, fast, and measurable** — so any of us can
> reproduce a chat, see exactly what Ally saw and did, turn a failure into a permanent
> test, fix it, and prove it stayed fixed — without touching a customer's server.

Today the harness exists (`tests/test_ally_evals*.py` + `ally_eval_corpus.py`) but there is
**no cockpit** (we debug by reading `command_logs` by hand) and **no closed loop** (a real
failure doesn't automatically become an eval). This plan closes both gaps.

## 2. Principles (non-negotiable)

1. **Eval-driven:** a behavior we care about is a *test*, not a vibe. Fix flow is always
   *reproduce → capture as eval (it fails) → fix → eval passes → ship (CI protects it)*.
2. **One source of truth for evals.** The corpus (data) + a runner (engine) power CI, the
   CLI, and the Dev Door UI alike — never three copies of the logic.
3. **Zero customer impact.** The Dev Door is admin-only; "dry run" **plans but never
   executes** (it calls `plan_commands`, never `connection_manager.execute`).
4. **Observability by default.** Every AI turn can emit a full **trace** (prompt sent, raw
   output, parsed result, tier/tokens/cost/retries). Opt-in, so prod pays nothing.
5. **Prompts change through code + the eval gate, never a live prod editor.** The Dev Door
   *reads* and *tests*; it does not hot-edit the production prompt.
6. **Secrets never leak into evals or traces** — reuse the existing redaction discipline.

## 3. Current state (what we reuse)

| Piece | Exists | Role in this plan |
|---|---|---|
| `ally_eval_corpus.py` (routing, safety, readonly, `Scenario`, `InjectionAttack`) | ✅ | becomes the **golden dataset**, extended over time |
| `test_ally_evals.py` / `_live` / injection / artifacts / reliability / threat | ✅ | become thin wrappers over the new **runner** |
| `plan_commands()` + context builders (`ai_context_service`, `scout`, `live_look`, `skill_service`, memories) | ✅ | reused by the **dry-run** path |
| `ai_usage` ledger + `command_logs` | ✅ | feed the **Activity/observability** view |
| `verify_mission` (LLM-as-judge) | ✅ | generalized into a reusable **judge** |
| admin/role concept | ❌ | add `users.is_admin` (Phase 0) |
| dev cockpit UI | ❌ | build (Phases 2–4) |

## 4. Architecture — the trace is the spine

Everything hinges on one abstraction: for any Ally turn, capture a **Trace**:

```
Trace {
  input:   { message, server_ctx, settings(ally_mode…), which context blocks }
  prompt:  { system, volatile_blocks[] }      # EXACTLY what the model received
  output:  { raw, parsed(plan|answer|artifacts) }
  meta:    { tier, input/output/cache tokens, cost_usd, retries, latency_ms, error? }
}
```

The same Trace object is what the **Inspector shows**, what a **captured eval case** is built
from, what the **eval runner** returns per case, and what **Activity** replays. Build it once.

**Six pillars** (each maps to a phase):

1. **Eval engine** — `Case` model + `runner` → structured `Result`s; corpus is data, runner
   is the engine, pytest/CLI/UI are interfaces.
2. **Judge harness** — reusable `judge(output, rubric) → {pass, reason}` (strong tier,
   calibrated) for soft qualities code can't assert.
3. **Dev Door: Inspector** — dry-run a message → see the full Trace. The flagship.
4. **Dev Door: Eval Runner + Capture** — run the suite in the UI; turn any chat/dry-run into
   a new eval case in one click (the flywheel's human gate).
5. **Observability** — Activity view over the ledger + logs, each row expandable to its Trace.
6. **Metrics + CI gate** — deterministic evals block a regressing PR; behavioral run on
   demand; pass-rate/cost/latency tracked over time.

## 5. Phased delivery (crawl → walk → run)

Each phase ships independently and is useful on its own.

### Phase 0 — Foundations (backend only, no UI)
- `users.is_admin` (bool, default false) + migration + `CurrentAdmin` dependency (403 for
  non-admins). Admin set manually / via the WHMCS-style entitlement path.
- **Refactor**: extract chat context assembly from `terminal.py` into
  `ai_context_service.build_chat_context(server, message, …) → (skill, blocks, settings)`
  so the WS handler **and** the dry-run share one code path (kills duplication, testable).
- **Trace capture**: optional `trace: dict | None` threaded through `llm_service.complete`
  and `plan_commands` (populates system/volatile/raw/tier/tokens/retries; no-op when `None`
  → prod unaffected).
- `dev_service.dry_run(message, server_id, settings)` + `POST /api/dev/dry-run` (admin-only):
  builds real context, calls `plan_commands` with a trace, returns the full Trace. **Never
  executes.**
- **Acceptance:** admin POSTs message+server → gets `{prompt, raw, parsed, meta}`, zero SSH
  execution; non-admin → 403; suite green.

### Phase 1 — Eval engine (backend)
- `app/evals/`: `Case` (id, category, input, context, `expects` predicate, provenance),
  `runner.run(cases, live=False) → Results`, structured `Result` (pass, expected, got, trace).
- Port the existing corpus + tests to run **through** the runner (pytest becomes a thin
  wrapper; CI behavior identical, engine now shared).
- CLI: `python -m app.evals run [--category X] [--live]` → a category pass-rate table.
- **Acceptance:** CLI reproduces current pytest results + prints pass-rate by category;
  deterministic set runs fully offline.

### Phase 2 — Dev Door: the Inspector (flagship UI)
- Admin-only `/dev` route + nav item (hidden unless `is_admin`).
- **Playground:** message box · server picker · settings (ally_mode) · **Dry run** →
  expandable panels: **full prompt** (system + each context block), **raw output**, **parsed**
  (plan/answer/artifacts), **meta** (tier · tokens · cost · retries · latency).
- **Acceptance:** reproduce this session's "empty `### DISK` snapshot" diagnosis in the UI in
  ~5 seconds instead of digging through logs.

### Phase 3 — Dev Door: Eval Runner + Case Capture (the flywheel)
- Run the suite from the UI → results table by category; drill into any failure
  (input · expected · got · Trace).
- **Capture as eval case:** from a dry-run or a real chat, one click → a new `Case` with
  proposed assertions, secret-scrubbed, saved for review (a `dev_eval_cases` table or a
  written corpus file behind a human "approve").
- **Acceptance:** a failing chat → one click → new eval case (red) → prompt fix → green;
  it can never silently regress again.

### Phase 4 — Judge harness + soft-quality evals + Observability
- Reusable `ai_service.judge(output, rubric) → {pass, reason}` (high tier), **calibrated**
  with known-good/known-bad cases so the judge itself is tested.
- Soft-quality evals: *specific-not-vague*, *doer-not-advisor (in prose)*, *right tone*,
  *artifact-when-tabular*.
- **Activity** page: recent AI calls (ledger + logs), each expandable to its Trace; filter by
  error/tier/cost.
- **Acceptance:** a "did Ally run a command instead of advising?" judge eval runs green on
  the current build; Activity shows a live turn's full Trace.

### Phase 5 — Metrics, CI gate, and process (later)
- Deterministic evals = a **required CI check** on every PR; behavioral evals gated
  (key + budget + explicit trigger), run before shipping a prompt change.
- Store pass-rate / cost / latency over time (a small table) → a trend the Dev Door charts.
- (Stretch) **A/B prompt variants** against the eval set; **auto-draft** candidate eval cases
  from ledger patterns ("Ally keeps failing when users say X"), always human-reviewed.

## 6. The team workflow this unlocks (the flywheel)

```
real usage / a report
   → reproduce in the Inspector (see the Trace)
   → Capture as eval case            (it fails — red)
   → fix the prompt / code
   → run evals                       (green)
   → ship  → CI gate protects it forever
```

This is exactly the loop we ran by hand this session (the doer fix, the "judicious" false
positive, the empty-snapshot bug) — the Dev Door makes it a one-click, minutes-long routine
instead of an afternoon of manual log-reading.

## 7. Risks & guardrails

| Risk | Guardrail |
|---|---|
| A customer reaches `/dev` or the dry-run API | `is_admin` checked on **every** dev route + endpoint; nav hidden; server-side 403 |
| Dry-run accidentally executes on a real box | dry-run calls `plan_commands` **only**; wired away from `connection_manager.execute`; a test asserts no execution path is reachable |
| Behavioral evals burn money | gated by key + a budget cap + explicit trigger; never in the default CI path |
| Secrets leak into a captured case or a Trace | reuse redaction (`redactSecrets` discipline); scrub server names/paths/creds before persist |
| Live prompt-editing footgun | Dev Door is **read + test only**; prompt changes go through code + the eval gate |
| Trace capture slows prod | fully opt-in (`trace=None` by default) — the prod path is byte-identical |

## 8. Recommended first step

**Phase 0 + Phase 2** (foundations + the Inspector). Phase 0 is the enabling plumbing
(admin flag, shared context builder, trace, dry-run endpoint); Phase 2 turns it into the
single most valuable tool — *see exactly what Ally sees and does, safely*. That alone pays
for the whole effort. Phases 1/3/4 (the runner, capture, judge) then build the closed loop.

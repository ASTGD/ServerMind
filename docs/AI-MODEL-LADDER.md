# Smart Model Ladder — the right-sized brain per task

> **Status: SHIPPED (2026-07-05).** "Smart Model Ladder" is the product/marketing name.
> Ally uses a stronger model for high-stakes judgment, the default for normal work, and a
> cheaper/faster model for trivial parts — highest accuracy where it matters, lowest cost
> where it doesn't — and it can **decide for itself, up front**, when a request needs a
> bigger brain.

## The idea

Not every AI call needs the same brain. Summarising command output in plain English is
easy; deciding whether a hacked server is *truly* clean is not. The ladder gives each
call the right-sized model:

| Tier | Model (Anthropic) | Used for |
|---|---|---|
| **high** ⬆ | `claude-opus-4-8` | Mission **verification gate**; a **stuck** mission's next step |
| **default** | `claude-sonnet-5` | Chat planning, mission steps, fleet chat, script generation |
| **low** ⬇ | `claude-haiku-4-5-20251001` | Plain-English **explanations**, NL→cron **schedule parsing** |

Three ways the ladder is applied:

1. **Static per-call-site** — each AI call declares its tier (`verify_mission` → high,
   `explain_output` / `parse_schedule` → low). The judgment call gets the best brain; the
   trivial parse gets the cheap one.
2. **Reactive escalation (in missions)** — when a mission is *struggling* (the verifier
   bounced it back, or the last two real steps both failed), the loop hands the **next**
   step a stronger brain, then drops back to default once it's moving again. Bounded by
   design (`ai_service.mission_step_tier`, pure + unit-tested); missions are short, so
   escalation can't run away.
3. **Proactive self-escalation ("Ally decides up front")** — the default model plans, but
   the planning contract has an optional `need_stronger` flag. When Ally itself judges a
   request genuinely HARD or high-stakes (a destructive/irreversible change, a security
   incident, a subtle diagnosis) and isn't fully confident, it sets `need_stronger: true`
   and keeps the draft minimal; the planner then **re-plans ONCE on the high tier** before
   anything runs. This is Ally recognising "this one's hard — let me think harder" *before*
   acting, not just reacting to a failure. It fires for both chat plans (`plan_commands`)
   and mission steps (`plan_mission_step`), is a single bounded hop, and only happens when
   a stronger tier actually exists (`llm_service.has_stronger_tier()` — so a BYO/other
   provider never pays for an identical re-plan). The system prompt stresses it's rare and
   deliberate, never "just to be safe" on routine work.

Any step or plan that ran on a stronger model — reactive or proactive — shows a small
**"stronger model"** badge in the UI, so you can see when Ally reached for more firepower.

## How it's built (small + safe)

- `llm_service.complete(..., tier="low"|"default"|"high")` — after resolving the provider
  model, `_tier_model()` swaps in the ladder model. **Anthropic provider only**, gated by
  `settings.ENABLE_MODEL_LADDER` (default on). For any bring-your-own-key user on another
  provider, the tier is a **no-op** — they keep their one configured model, so callers can
  always pass a tier safely. Models are env-overridable (`AI_MODEL_LOW`, `AI_MODEL_HIGH`).
- No new metering needed: the `ai_usage` ledger already records the exact model + tokens +
  cost per call, so the ladder is visible in the ledger for free.

## Why the ladder, not the native "advisor tool"

We researched Anthropic's beta **advisor tool** (`advisor_20260301`) — a faster executor
model consulting a stronger advisor model mid-generation. It's elegant, but a poor fit
*for us right now*:

- It's **Anthropic-API-only beta** — it can't live in our multi-provider `llm_service`
  (OpenAI/Gemini/BYO users couldn't use it).
- It needs a **model-driven tool-use loop** (executor decides when to consult, with
  `pause_turn` resumes). Ally's AI calls are single-shot **structured JSON** driven by
  **our** Python — which is exactly what gives us the per-command safety validation,
  approval gating, and read-only verification. Adopting the native tool would mean
  rewriting the mission engine into a model-driven loop and risking that control.
- It only does the **"up"** step; the ladder also **saves money on the easy parts**.

The ladder captures the same core value (a stronger brain for the hard part) while fitting
our architecture, staying provider-agnostic, and adding downgrades. The native advisor
tool remains a good candidate for a *future* purpose-built, model-driven surface (e.g. a
deep-diagnosis agent), where it would fit properly. Full research notes are in the git
history of this file's first commit.

## Verified live (2026-07-05)

One session's `ai_usage` ledger showed the whole ladder end-to-end:

| feature | model | calls |
|---|---|---|
| chat | `claude-haiku-4-5-20251001` (low — explanations) | 2 |
| chat | `claude-sonnet-5` (default — planning) | 4 |
| mission | `claude-opus-4-8` (high — the verify gate) | 1 |
| mission | `claude-sonnet-5` (default — steps) | 7 |

The Haiku explanations cost ~$0.0014/call vs ~$0.017 on Sonnet (~12× cheaper on trivial
work); the Opus verify was one $0.042 call at the single highest-stakes moment (confirming
a mission's goal is truly met). A clean TestServer2 health mission completed → the Opus
verifier confirmed it → green "Verified".

## Follow-ups

- Route the **hosted gateway** (`servermind` provider) tiers too (needs the gateway to
  accept a tier/model hint).
- Consider escalating **hard chat plans** (e.g. a destructive or ambiguous request) to
  high, and **complex script generation** — measure first.
- Revisit the native advisor tool for a future model-driven agent surface.

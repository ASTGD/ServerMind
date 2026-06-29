# Update 20 — Multi-provider AI (bring your own key)

> ServerMind's AI was hard-wired to Anthropic (Claude). It now works with the
> customer's choice of provider, so they can bring a key from whichever AI they trust —
> the foundation for the self-hosted edition's "paste your own key" setup (see
> [SELF-HOSTED-LICENSING.md §7](SELF-HOSTED-LICENSING.md)) and useful in the hosted
> edition too.

## What changed

- **New `app/services/llm_service.py`** — one `complete(system, user)` call routed to
  the configured provider. Anthropic goes through the `anthropic` SDK; OpenAI, Gemini,
  and any OpenAI-compatible endpoint (Mistral, Groq, DeepSeek, a local model…) go
  through the `openai` SDK pointed at the right base URL. SDKs are imported lazily, so
  the default Anthropic path needs nothing extra installed.
- **`ai_service`** (chat plan, script generation, explain output, schedule parsing) now
  calls `llm_service.complete()` instead of the Anthropic client directly — the prompts
  are unchanged.
- **Config (`.env`):** `AI_PROVIDER` (`anthropic` | `openai` | `gemini` |
  `openai_compatible`), `AI_API_KEY`, `AI_MODEL`, `AI_BASE_URL`. Empty values fall back
  to the existing `ANTHROPIC_*` settings, so current setups keep working with zero
  changes. Added `openai` to `requirements.txt`.

## Verified

Routing unit-tested for Anthropic + OpenAI (mocked SDKs), plus the resolve/fallback
logic and the no-key error. 64 tests pass; backend imports clean. (No live key on hand,
so this is mock-verified end to end — real keys per provider need a live smoke test.)

## Settings UI (shipped — Update 20.1)

Pick the provider + paste the key + choose a model from **Settings → AI provider** (no
`.env` editing). The key is encrypted (AES-256-GCM) and stored instance-wide in a new
`app_settings` table (migration 016); the live override is applied immediately and
re-loaded on startup, falling back to `.env`. A **Test** button sends a tiny prompt to
confirm the key + model work. Endpoints: `GET`/`PUT /api/settings/ai`, `POST
/api/settings/ai/test`. (Currently any authenticated user can change it — tighten to an
owner/admin role for multi-user instances.)

## Next

- The same provider/key step inside the **self-hosted setup wizard**.
- The optional hosted **"ServerMind AI" subscription** gateway (option B in
  [SELF-HOSTED-LICENSING.md §7](SELF-HOSTED-LICENSING.md)).

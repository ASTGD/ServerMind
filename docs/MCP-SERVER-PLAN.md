# ServerAlly MCP Server — implementation plan

> **Status: PLAN (2026-07-17).** Approved by the PM: *"go with MCP + Ally subscription,
> customer can choose."*
>
> This is **Layer 2(a)** of [PRICING-V3.md](PRICING-V3.md) — the "bring your own AI" lane.
> Read PRICING-V3 first: it explains *why* this exists and what it must never become.
>
> **Durable record.** All decisions below are final unless explicitly revisited in a
> dated entry. Do not re-litigate them from memory.

---

## 1. What this is, in one paragraph

A **remote MCP server** at `https://app.serverally.<tld>/mcp` that lets a customer connect
their **own** AI client — Claude (web/Desktop/mobile/Code), ChatGPT, Cursor, VS Code,
Windsurf — and manage their ServerAlly assets by conversation. **They authenticate once
in a browser (OAuth), and their own AI subscription pays for every token. Our AI cost is
zero.**

## 2. Why we're building it

From [PRICING-V3.md](PRICING-V3.md) §2 and [PRICING-METRIC-RESEARCH.md](PRICING-METRIC-RESEARCH.md):

1. **It neutralises Ploi's only real cost advantage.** Ploi hosts no LLM at all; the
   customer's Claude subscription pays. That is why Ploi offers "unlimited AI" inside a
   €13 flat plan with no meter. This closes that gap.
2. **It is our pressure valve against our worst financial risk.** We cannot predict what a
   customer's AI costs us. The heaviest users are the most technical → most likely to own
   Claude already → most able to choose this lane. *The customers we can't afford are the
   ones who don't need our AI.*
3. **Our buyer plausibly wants it.** Corrected positioning (PRICING-V3 §4): the *payer* is
   a semi-technical agency/dev/MSP, not a non-technical blogger.
4. **Zero marginal cost forever.** No inference, no meter, no Cursor-style pricing risk.

## 3. Non-goals — read this before designing anything

**🚫 This is NOT a remote shell.** No `run_command`, `exec`, or arbitrary-shell tool in
v1. Not because the customer lacks shell (they own the server; they can SSH), but because
of what changes when an AI drives:

> **Over MCP, the customer's AI does the reasoning and we are just an API.** Every safety
> asset we built this year — skills, the verification gate, mission runbooks, injection
> defence, self-footprint recognition, the `vendor/` false-positive lesson — lives in
> *Ally's loop*, which MCP bypasses entirely. A raw shell tool would leave only
> `safety_service`'s blocklist standing, while an AI we do not control issues commands
> with our stored root credentials at machine speed.

**Ploi's MCP is also bounded** — "deploy sites, inspect logs, manage databases", not a
shell. That is the precedent and it is the right one.

**🚫 Not free.** MCP is a Layer 1 platform feature (paid tiers). It is *AI* that is free
in this lane, not the platform.

**🚫 Never returns a credential.** No tool may return `encrypted_cred`, a decrypted
secret, a password, an SSH key, `fingerprint`, or a claim link — by construction, and
enforced by test (mirroring `test_user_detail_never_exposes_a_credential`).

**Deferred, not rejected:** a guarded `run_command` behind a per-server opt-in +
`safety_service.validate()` + full audit. Revisit only on real customer demand, as its own
dated decision.

## 4. Architecture

```
Claude / ChatGPT / Cursor
        │  Streamable HTTP + OAuth bearer
        ▼
  POST /mcp                     ← FastMCP mounted on our existing FastAPI
        │
        ├─ auth: resolve bearer → User          (new: app/mcp/auth.py)
        ├─ Rule 7: team_service.get_access(...) (REUSED — unchanged)
        ├─ tool → existing service layer        (REUSED — no new business logic)
        └─ audit_service.audit("mcp.<tool>")    (REUSED)

  /.well-known/oauth-protected-resource   ← new OAuth 2.1 AS
  /.well-known/oauth-authorization-server    (app/routers/oauth.py)
  /oauth/register  /oauth/authorize  /oauth/token
```

**Principle: the MCP server contains no business logic.** Every tool is a thin adapter
over an existing service (`hosting_service`, `playbook_service`, `security_service`,
`fleet_service`, `metrics_service`, `file_service`). Access control is the *existing*
`team_service` primitives. If a tool needs new logic, that logic belongs in the service
layer where the rest of the product can use it too.

## 5. Authentication — the hard part

**80% of this project is OAuth, not MCP.** We have `python-jose` + JWT bearer login and
**no authorization server**. Anthropic's docs state it plainly: *"Authentication is the
most common source of partner questions."*

### 5.1 Chosen mechanism: `oauth_dcr`

Anthropic supports: `oauth_dcr`, `oauth_cimd`, `oauth_anthropic_creds`,
`custom_connection`, `static_headers` (beta), `none`.

**Decision: `oauth_dcr`** — OAuth 2.0 + Dynamic Client Registration (RFC 7591). It is
*"supported out of the box"*, needs no email exchange with Anthropic, and works for a
custom connector added by URL.

**Rejected:**
- `static_headers` — beta, and the credential is *organisation-shared, entered by an
  admin*. Wrong shape for per-customer identity in multi-tenant SaaS.
- `none` — unthinkable; this reaches production servers.
- `oauth_anthropic_creds` / `oauth_cimd` — both still need a full AS; DCR is the one
  Anthropic auto-negotiates. **Revisit CIMD if we submit to the public directory** —
  Anthropic warns DCR registers a new client on every fresh connection, which bloats the
  client table at directory scale.

### 5.2 Exact requirements (from Anthropic's connector auth reference)

| Requirement | Detail |
|---|---|
| Transport | **Streamable HTTP** (legacy HTTP+SSE deprecated) |
| Unauthenticated response | **`401`** + `WWW-Authenticate: Bearer resource_metadata="https://…/.well-known/oauth-protected-resource"` — **a 200 with the header is NOT honoured** |
| Protected resource metadata | RFC 9728. `resource` **must match the MCP URL exactly as the user types it**, including path. `authorization_servers` lists our issuer (first entry wins; no fallback) |
| AS metadata | RFC 8414 (or OIDC Discovery) at `/.well-known/…`, reachable from Anthropic egress |
| DCR | `registration_endpoint`, **`application/json`** (RFC 7591) |
| PKCE | **S256 mandatory** on every request; must advertise `"code_challenge_methods_supported": ["S256"]` |
| Token endpoint | **`application/x-www-form-urlencoded`** — a JSON-only parser returns 415 and breaks the flow. *Different parser from `/register`.* |
| Refresh | Rotate refresh tokens (Claude registers as a **public client**); return **`invalid_grant`** (not `invalid_request`) when a refresh token dies |
| Redirect URIs | `https://claude.ai/api/mcp/auth_callback` (hosted surfaces) **and** loopback for Claude Code — accept `http://localhost/callback` + `http://127.0.0.1/callback` **ignoring the port** (RFC 8252 §7.3) |
| Latency budget | **10s** discovery/registration/token, **30s** refresh — exceeding it fails the connection |
| Egress allowlist | Anthropic calls from **`160.79.104.0/21`** — a WAF in front of the AS breaks the flow even if `/mcp` is reachable |

### 5.3 Consent screen

A real browser page: *"Claude wants to access your ServerAlly account — N servers. It will
be able to: read status and metrics, run playbooks, manage sites. It will never see your
credentials."* Approve/Deny, revocable from Settings (per Ploi's model). Tokens are
**per-user**, scoped to that user's own `accessible_servers`.

### 5.4 Library

Add **`authlib`** (the standard Python OAuth AS). Do **not** hand-roll OAuth 2.1 —
PKCE, DCR, rotation and metadata are exactly where hand-rolled auth goes wrong.

## 6. Tool catalogue (v1)

Every tool: scoped to the caller's `accessible_servers`, Rule-7 checked, audit-logged,
credential-free, **0 AI actions** (deterministic — no model call).

### Read (Phase 2)
| Tool | Service |
|---|---|
| `list_servers` | `team_service.accessible_servers` |
| `get_server` | server detail + status |
| `get_metrics` | `metrics_service` (CPU/RAM/disk, latest + history) |
| `get_fleet_health` | `fleet_service.analyze_fleet` — scores + findings |
| `list_sites` | `hosting_service` / `cyberpanel_cli` |
| `get_security_scan` | latest `security_scans` |
| `get_threat_scan` | latest `threat_scans` |
| `list_playbooks` | `playbook_service` |
| `list_missions` / `get_mission` | `mission_service` (incl. transcript + result) |
| `list_files` / `read_file` | `file_service` — **client-side redaction is not available here**, so `read_file` must run the server-side secret filter and refuse binaries |

### Bounded writes (Phase 3)
| Tool | Notes |
|---|---|
| `run_playbook` | Returns `run_id` immediately — **must not block** (§7) |
| `get_playbook_run` | Poll status/output |
| `run_security_scan` / `run_threat_scan` | Read-only probes by construction |
| `create_site`, `issue_ssl`, `create_database` | CyberPanel CLI ops |
| `run_backup` | Existing backup job only — no ad-hoc definitions |

**Not exposed in v1:** `run_command`, restore-from-backup (destructive), credential
mutation, team/billing management, anything that deletes.

## 7. Platform constraints (design around these)

| Constraint | Value | Consequence |
|---|---|---|
| claude.ai/Desktop tool timeout | **300s (5 min)** | A mission or install runs far longer → **every long op is start + poll**, never a blocking call |
| Claude.ai/Desktop result size | **~150,000 chars** | Truncate + paginate logs, file reads, scan output |
| Claude Code result size | **25,000 tokens** | Same |

## 8. Metering & plan gating

- **MCP calls cost 0 actions.** They are deterministic — no model call, no ledger row.
  This is the entire point of Layer 2(a).
- **They still consume real infra** (SSH, scans) → the existing per-minute rate limit
  applies. Note PRICING-V3 §8: it is per-server today and should become per-user too.
- **Gating:** paid tiers only (MCP is a Layer 1 platform feature). Ploi gates at "Pro and
  up"; final tier is an open number (PRICING-V3 §6).
- **Audit:** every tool call → `audit_service.audit("mcp.<tool>")`, surfaced in the
  operator console.

## 9. Phases

| # | Scope | Acceptance criteria | Est. |
|---|---|---|---|
| **0** | **Spike** — FastMCP mounted on FastAPI, one authless `list_servers`, validated with **MCP Inspector** | Inspector lists + calls the tool locally | 1–2 d |
| **1** | **OAuth 2.1 AS** (`authlib`): metadata, DCR, authorize + consent, token, PKCE S256, refresh rotation, the 401 handshake | **A real Claude account connects** via Settings → Connectors → URL → approve. Also `claude mcp add` from Claude Code (loopback redirect). Token refresh survives expiry | 5–8 d |
| **2** | **Read tools** + Rule-7 scoping + audit + credential-free tests | Claude answers *"which of my servers need attention?"* from real data; a second user's servers are invisible | 3–4 d |
| **3** | **Bounded write tools**, start+poll for long ops | Claude runs a playbook end-to-end via poll; a 6-minute op does not hit the 5-min timeout | 3–4 d |
| **4** | **UI + gating** — Settings → "Connect your AI" (URL, copy button, connected clients, **revoke**), plan gate, docs page | A customer can connect and revoke without support | 2–3 d |
| **5** | **Live verification + hardening** — real Claude against real servers, egress allowlist, latency budget, rate-limit check | The §11 checklist passes end to end | 2–3 d |

**Total ≈ 3–4 weeks.** Phase 1 is the risk; Phases 2–3 are thin adapters over services
that already exist and are already tested.

## 10. Security model

1. **Rule 7 is not re-implemented** — every tool resolves access through `team_service`.
   A viewer can never execute, exactly as in the app.
2. **No credential ever crosses the boundary** — enforced by a payload test, not by intent.
3. **Tokens are per-user**, browser-consented, revocable, refresh-rotated. No long-lived
   secrets in config files.
4. **Blast radius is bounded by the tool catalogue**, not by trusting the client's AI.
   That is why §3 forbids a shell.
5. **Prompt injection:** a compromised server's log/file content flows into the
   *customer's* AI, not ours. We cannot protect their model — so `read_file`/`get_logs`
   must be honest about provenance and never auto-escalate. This is a genuine limitation
   of the lane and belongs in the customer-facing doc.
6. **Every call audited**, attributable to a user + client.

## 11. Live verification checklist (Phase 5)

- [ ] Connect from **claude.ai** (Settings → Connectors → URL → approve)
- [ ] Connect from **Claude Code** (`claude mcp add --transport http …` → `/mcp`)
- [ ] Connect from **ChatGPT** (Settings → Connectors) — validates we're not Claude-specific
- [ ] **Revoke** from ServerAlly Settings → the client immediately loses access
- [ ] **Token refresh** works after expiry (Claude refreshes reactively on 401)
- [ ] A second user's servers are **invisible** (Rule 7 across the boundary)
- [ ] A **viewer** cannot invoke a write tool
- [ ] **No credential** in any tool payload (automated)
- [ ] A **6-minute playbook** completes via start+poll without a timeout
- [ ] A **150k+ char** log read truncates cleanly rather than failing
- [ ] MCP calls record **0 actions** in `ai_usage`
- [ ] Rate limit still applies to MCP-driven SSH work

## 12. Risks

| Risk | Mitigation |
|---|---|
| **OAuth is fiddly and undertested by us** | `authlib`, MCP Inspector for auth flows, and a real Claude connection as the Phase-1 gate. Budget the full 5–8 days |
| **DCR client bloat** | Fine for custom connectors; switch to CIMD before any directory submission |
| **Serves developers, not our core buyer** | Accepted deliberately — that is the point (PRICING-V3 §4) |
| **Cannibalisation:** everyone picks BYO, we become "just a panel" | That is Ploi's entire business at €13 with **~100% margin**. An acceptable outcome, not a failure |
| **We can't protect the customer's AI from injection** | Documented honestly (§10.5); bounded tools limit what a fooled AI can do |
| **Scope creep into a shell** | §3 is a hard rule; adding `run_command` requires its own dated decision |

## 13. Explicitly deferred

- `run_command` / shell (§3)
- Public MCP **directory** submission (needs CIMD + Anthropic review)
- MCP **prompts** and **resources** (tools only in v1)
- An `ally_ask` tool that proxies our own Ally — it would reintroduce our AI cost and
  defeat the lane's purpose

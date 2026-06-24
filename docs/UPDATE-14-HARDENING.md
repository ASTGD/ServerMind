# Update 14 — Production Hardening · Build Spec

> Status: **COMPLETE** (14.1–14.8 + 14.3b). Goal: make ServerMind safe for untrusted, multi-tenant signup.
> **Backward-compatible** — every gate is behind a config flag defaulting to today's
> behavior. Closes CLAUDE.md security rule **#8** (rate limiting); rule **#6** (SSH
> host-key verification) is tracked as an optional follow-up.

## Dependencies
- prod: `slowapi>=0.1.9` (HTTP rate limiting), `pyotp>=2.9.0` (TOTP, workstream 14.3)
- dev/test: `pytest>=8`, `pytest-asyncio>=0.23`, `httpx>=0.27`, `pytest-cov` (14.8)
- async Redis via the existing `redis==5.0.4` (`redis.asyncio`) — no new dep
- frontend: `qrcode.react` (14.3)
- bundled quick fix: pin `bcrypt==4.0.1` (or bump passlib) to silence the `__about__` startup log noise

## Config additions (`app/config.py`)
| Setting | Default | Purpose |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `True` | master switch |
| `LOGIN_RATE_LIMIT` | `"5/minute"` | per-IP login |
| `REGISTER_RATE_LIMIT` | `"3/minute"` | per-IP register |
| `COMMAND_RATE_PER_MIN` | `30` | per user+server (WS exec) — rule #8 |
| `REQUIRE_EMAIL_VERIFICATION` | `False` | gate sensitive ops when true (14.4) |
| `WS_TICKET_TTL_SECONDS` | `30` | single-use WS ticket (14.6) |
| `EMAIL_VERIFICATION_TOKEN_HOURS` | `24` | verify-link expiry (14.4) |
| `APP_BASE_URL` | `""` | builds verify links (14.4) |

## Migrations
- `011_add_user_token_version.py` — `users.token_version INTEGER NOT NULL DEFAULT 0`
- `012_create_audit_logs.py` — audit_logs table (14.5)

2FA & email verification need no columns (`totp_secret`/`totp_enabled`/`is_verified` exist;
the verify link is a signed JWT).

```sql
-- 012
audit_logs(
  id UUID PK DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(id) ON DELETE SET NULL,
  action VARCHAR(64) NOT NULL,        -- 'auth.login','server.create','team.role_change'
  target_type VARCHAR(32),
  target_id VARCHAR(64),
  metadata JSONB,
  ip VARCHAR(64),
  user_agent VARCHAR(255),
  created_at TIMESTAMP DEFAULT now()
);
CREATE INDEX ix_audit_user_created ON audit_logs(user_id, created_at DESC);
CREATE INDEX ix_audit_action ON audit_logs(action);
```

## Shared infrastructure
- `app/services/redis_service.py` — `get_redis()` async singleton from `REDIS_URL`; fail-open if unavailable.
- `app/services/rate_limit_service.py` — slowapi `Limiter` (Redis storage, key = client IP) + `async check_command_rate(user_id, server_id) -> bool` (Redis INCR on `rl:cmd:{u}:{s}`, 60 s window; False when over `COMMAND_RATE_PER_MIN`). Fail-open if Redis is down.
- Token claims — `auth_service.create_access_token(user_id, token_version)` / `create_refresh_token(...)` add `"tv"`. `dependencies/auth.py` rejects when `payload.get("tv", 0) != user.token_version` (default 0 ⇒ pre-existing tokens stay valid until they expire — non-breaking).

## Workstreams
- **14.1 Rate limiting** [S] — slowapi middleware + 429 handler; decorate `/login`,`/register`; WS exec calls `check_command_rate` (chat + playbook-run; terminal PTY exempt).
- **14.2 Token revocation** [S] — `logout` bumps `token_version` (kills all that user's tokens). Password-change session-invalidation (bump + reissue tokens) is a fast-follow once the frontend stores the reissued tokens.
- **14.3 2FA (TOTP)** [M] — `totp_service` (pyotp, secret encrypted via `crypto_service`); `POST /2fa/setup|verify`, `DELETE /2fa`; `login` gains optional `totp_code` (401 `"TOTP code required"` when enabled and missing). Settings UI w/ QR.
- **14.4 Email verification** [M] — signed verify-JWT, `email_service.send_verification_email`; `register` sets `is_verified=false` when flag on; `POST /verify-email`,`/resend-verification`; `require_verified` dependency on server-create + WS exec.
- **14.5 Audit log** [M] — `audit_logs` + `audit()` helper; instrument auth/server/team/settings actions; `GET /api/audit`.
- **14.6 WS auth ticket** [M] — `POST /api/auth/ws-ticket` (Redis single-use, 30 s); WS accepts `?ticket=`; `?token=` kept as deprecated fallback.
- **14.7 Hard-fail weak secrets** [S] — prod boot raises on default/short `ENCRYPTION_KEY`/`SECRET_KEY` or `ALLOWED_ORIGINS='*'`.
- **14.8 Tests + CI** [M] — pytest harness (Postgres + Redis), GitHub Actions.

## New endpoints
```
POST   /api/auth/2fa/setup            (14.3)
POST   /api/auth/2fa/verify           (14.3)
DELETE /api/auth/2fa                  (14.3)
POST   /api/auth/verify-email         (14.4)
POST   /api/auth/resend-verification  (14.4)
POST   /api/auth/ws-ticket            (14.6)
GET    /api/audit                     (14.5)
# changed: /login (+totp_code, rate-limited), /register (rate-limited), /logout (bumps tv)
```

## Test matrix
| File | Cases |
|---|---|
| test_safety.py | each Linux+Windows blocked pattern; confirm patterns; benign passes |
| test_auth.py | register/login/refresh; bad password; unknown-email timing; malformed token → 401; tv invalidation after logout |
| test_2fa.py | setup→verify enables; login w/o code → 401; valid/invalid; disable |
| test_email_verify.py | flag on → unverified blocked; verify flips; expired token 400 |
| test_ratelimit.py | 6th login → 429; 31st command/min → blocked |
| test_rbac.py | viewer never executes (HTTP+WS); owner/admin gates; accessible_servers scoping |
| test_execute_stream.py | non-zero exit → CommandError; stderr merged |
| test_ws_ticket.py | valid once; reuse/expiry rejected |
| test_audit.py | sensitive actions write one row; scoping |

## CI — `.github/workflows/ci.yml`
Services `postgres:16` + `redis:7`; steps: install → `alembic upgrade head` → `pytest --cov` (backend); `npm ci && tsc --noEmit && npm run build` (frontend). Gate PRs on green.

## Build order (~3–4 days)
1. Shared infra (config, redis, token_version migration + claims + dep check) **[done in pass 1]**
2. 14.7 weak-key hard-fail **[pass 1]**
3. 14.2 revocation (logout bump) **[pass 1]**
4. 14.1 rate limiting **[pass 1]**
5. 14.6 WS ticket → 6. 14.3 2FA → 7. 14.4 email verify → 8. 14.5 audit → 9. 14.8 tests + CI

## Rollout
Flags off → on per environment, in order: hard-fail keys → rate limit → WS ticket → 2FA (opt-in) → `REQUIRE_EMAIL_VERIFICATION` last (after SMTP verified in prod).

---

## 14.3 — Shipped (2FA / TOTP)
Built via a design workflow → implement → 4-lens adversarial-review workflow (verified each finding). **Shipped:** `totp_service` (pyotp, AES-GCM-encrypted secret); `POST /2fa/setup` (pending secret), `POST /2fa/verify` (activates), `DELETE /2fa` (requires a code); login gate (single `401 "TOTP code required"`); `valid_window=1`; per-user failed-attempt lockout (`totp:fail:{uid}`, 10/900s) on **login, verify, and disable**; Settings QR enroll/disable UI; login TOTP field. Review fixes applied: throttle on verify/disable (not just login), invalid-code returns **400 not 401** (a 401 trips the global interceptor → logout), `LOGIN_RATE_LIMIT` raised to 10/min (2FA login is a 2-request flow), stale code cleared on retry.

**14.3b recovery codes (shipped):** 10 one-time codes (SHA-256-hashed at rest, migration 012) generated on enable and shown **once**; accepted at login and for disable (a wrong recovery code counts toward the lockout); `POST /api/auth/2fa/recovery-codes` regenerates them (requires a current TOTP code). Settings shows them in a save-once panel with copy.

**Deferred follow-ups (tracked, accepted risk):**
- **TOTP replay** — a valid code is reusable within its ~90s window (no single-use timestep cache). Mitigation: record the last consumed timestep per user in Redis. Deferred to avoid added state on the hot login path.
- **`token_version` bump on enable/disable** — enabling 2FA does not invalidate other live sessions / pre-2FA refresh tokens (would require token re-issue to avoid logging out the current session).
- **Per-IP login limit behind a proxy** — keys off the proxy IP until `X-Forwarded-For` is trusted (the per-user TOTP lockout is the real control).

---

## 14.8 — Shipped (tests + CI)
**52 pytest tests**, no external services (`fakeredis` for Redis, no DB) — `pip install -r requirements-dev.txt && pytest`:
- `test_safety.py` — Linux + Windows blocklist, confirm patterns, plan priority (blocked > confirm), `highest_risk`.
- `test_totp.py` — secret/verify (empty/None/undecryptable → `False`, never raises), encrypted-at-rest, provisioning URI, recovery-code generation + hash normalization.
- `test_auth_service.py` — JWT `tv` (token_version) claim, refresh type, garbage → `None`, password hash/verify.
- `test_rate_limit.py` — WS command cap, per-user TOTP lockout, **fail-open** on Redis outage.

CI (`.github/workflows/ci.yml`): backend `pytest` + frontend `tsc --noEmit` + `npm run build`, on push to `main` and every PR.

**🔒 Security fix surfaced by these tests:** the Windows blocklist path patterns were over-escaped (`C:\\\\` → the regex required a *double* backslash), so real single-backslash commands — `Remove-Item C:\Windows`, `del /f /s /q C:\Windows`, `rd /s /q C:\` — were **not blocked**. Fixed and covered by `test_safety`.

**Follow-up (not this pass):** DB-backed integration tests (httpx + Postgres fixtures + a Postgres service in CI) for the RBAC "viewer can never execute" invariant and the auth/2FA endpoints end-to-end.

---

## 14.5 — Shipped (audit log)
New `audit_logs` table (migration 013) + `audit_service.audit()` — best-effort (never raises into the caller; rolls back on failure), captures IP (honours `X-Forwarded-For`) + user-agent. `meta` holds only non-sensitive context — never secrets/codes.

**Instrumented events:** `auth.login` / `logout` / `register` / `password_change` / `2fa_enabled` / `2fa_disabled` / `2fa_recovery_regenerated`; `server.create` / `server.delete`; `team.invite` / `team.role_change` / `team.remove`.

`GET /api/audit` returns the user's own events (newest first, ≤200). Settings shows a **Recent security activity** list (action, IP, relative time).

**Follow-up:** admin/team-wide audit view (currently each user sees only their own events); retention/pruning of old rows.

---

## 14.4 — Shipped (email verification)
Config flag `REQUIRE_EMAIL_VERIFICATION` (default **off** — existing behavior unchanged). When on: `register` sets `is_verified=False` and emails a signed verify-JWT link (`notification_service` SMTP, best-effort); `POST /api/auth/verify-email {token}` confirms; `POST /api/auth/resend-verification` re-sends. A `require_verified` dependency **403s server-create and WS command exec** until verified. Frontend: a public `/verify-email` page + a global banner (with resend) shown whenever `user.is_verified` is false. `APP_BASE_URL` sets the link's frontend origin (falls back to the request origin).

---

## ✅ Update 14 complete
All hardening workstreams shipped and CI-green: rate limiting, token revocation, 2FA + recovery codes, WS tickets, weak-key hard-fail, audit log, email verification, and a pytest suite + CI. Two real bugs were caught and fixed along the way (the unblocked Windows destructive commands; the force-logout on a mistyped 2FA code). Remaining follow-ups are documented inline above (TOTP replay cache, token_version bump on 2FA change, admin-wide audit view, DB-backed RBAC integration tests).

# Update 14 — Production Hardening · Build Spec

> Status: in progress. Goal: make ServerMind safe for untrusted, multi-tenant signup.
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

# ServerAlly — Security Review

Scope: authentication, session/token handling, access control, credential
encryption, and command-execution safety. Reviewed at the end of Phase 13.

> **Status update (2026-07-06):** items 1, 2, 3, 5, and 8 below were fixed by the
> subsequent hardening pass (`docs/archive/UPDATE-14-HARDENING.md`) and verified
> against the current code — see the ✅ notes inline. Item 4 also has real
> verification code now (gated by `REQUIRE_EMAIL_VERIFICATION`), it just isn't
> flipped on for the current single-tenant dev deployment. New residual gaps found
> during that same code check are listed at the bottom.

## ✅ Verified strong

- **Credential encryption** — server/DB credentials stored AES-256-GCM
  (`crypto_service`); never returned by the API (`ServerOut` excludes
  `encrypted_cred`; backups expose only a `has_db_cred` boolean). DB-backup
  passwords are injected via `MYSQL_PWD`/`PGPASSWORD` env, never on the argv.
- **Password storage** — bcrypt via passlib.
- **JWT** — HS256 signed, expiry enforced, `type` (access/refresh) checked at
  every consumer (HTTP deps, refresh endpoint, and now WebSocket).
- **Access control** — every server-scoped endpoint resolves through
  `team_service.get_access`; a **viewer can never execute** even if granted
  `can_execute` (role override, unit-tested against Postgres). Owner/admin gate
  for server config changes.
- **Command safety** — `safety_service` blocklist (Linux + Windows) runs before
  any AI command; security-audit probes are read-only; backup/restore commands
  are `shlex`-quoted; suggested "fix" commands are shown, never auto-run.

## 🔧 Hardened in this pass

| Fix | File |
|---|---|
| Password min-length (8) on register **and** change-password | `schemas/user.py`, `routers/auth.py` |
| Login timing equalized (dummy bcrypt verify when email unknown) → no user enumeration | `routers/auth.py` |
| WebSocket auth now requires an **access** token (rejects refresh tokens) | `websocket/terminal.py` |
| Malformed-`sub` tokens return 401, not 500 (UUID parse guarded) | `dependencies/auth.py`, `routers/auth.py` |
| Production startup warns on default/weak `SECRET_KEY`/`ENCRYPTION_KEY` and `ALLOWED_ORIGINS='*'` | `main.py` |
| `.env.prod` / `.env.*` git-ignored (keeps `.env.example`) — prevents committing secrets | `.gitignore` |

## ⚠️ Known gaps & recommendations (prioritised)

1. ✅ **Rate limiting — RESOLVED.** `slowapi` is wired (`app/services/rate_limit_service.py`,
   `Limiter(key_func=get_remote_address, ...)`); `@limiter.limit(settings.REGISTER_RATE_LIMIT)`
   and `@limiter.limit(settings.LOGIN_RATE_LIMIT)` decorate register/login in `routers/auth.py`.
2. ✅ **Token revocation — RESOLVED.** `users.token_version` is bumped on logout
   (`current_user.token_version += 1`) and checked against the JWT's `tv` claim on refresh
   (`routers/auth.py`) — every outstanding token from before a logout is invalidated.
3. ✅ **SSH host-key verification — RESOLVED.** `ssh_service._get_client` takes an
   `expected_fingerprint`, compares it on every connect/reconnect, and raises
   `HostKeyMismatch` on a mismatch (threaded through `execute`, `execute_stream`, `open_shell`).
4. **Email verification (MEDIUM for public signup) — code exists, not yet turned on.**
   `is_verified=not settings.REQUIRE_EMAIL_VERIFICATION` at registration, plus a real
   verify-token flow (`routers/auth.py`) — this is a **config flip**, not a missing feature;
   flip `REQUIRE_EMAIL_VERIFICATION=true` before opening public signups.
5. ✅ **2FA — RESOLVED.** `totp_service` + enable/verify/recovery-code endpoints are built
   and wired into login (`routers/auth.py`, checked in login when `user.totp_enabled`).
   Residual gap: `token_version` is **not** bumped when 2FA is toggled on/off, so other live
   sessions/refresh tokens aren't force-invalidated by that specific event (logout still works).
6. **Panel/WinRM TLS (LOW/MEDIUM) — still open, by design.** Hosting + WinRM use
   `verify=False` / `server_cert_validation='ignore'` (self-signed panels are common). Offer a
   per-server "strict TLS" opt-in for properly-certificated hosts.
7. **Encryption-key strength (LOW — mitigated).** A short `ENCRYPTION_KEY` is
   null-padded. Docs + the new startup warning cover it; consider hard-failing in
   production if it isn't 64 hex chars.
8. ✅ **WebSocket token in query string — RESOLVED.** `POST /api/auth/ws-ticket` issues a
   short-lived, single-use, Redis-backed ticket (`WS_TICKET_TTL_SECONDS`) instead of the raw JWT.
9. **passlib/bcrypt log noise (cosmetic) — still present.** The "error reading bcrypt
   version" line still appears (seen throughout normal dev use). Pin `bcrypt<4.1` or bump
   passlib to silence; hashing is unaffected.

**New residual gaps** (found verifying the above against current code, 2026-07-06):
10. **Rate-limit key source (LOW until behind a proxy).** `slowapi`'s `key_func=get_remote_address`
    reads the raw connecting IP; there's a code comment noting a trusted `X-Forwarded-For` needs
    configuring once ServerAlly sits behind a reverse proxy in production (see `DEPLOY.md`).
11. **Audit log is self-service only (LOW).** `GET /api/audit` returns only the requesting
    user's own events — there's no admin/team-wide audit view, and no retention/pruning policy
    for the `audit_logs` table.
12. **TOTP replay window (LOW — accepted risk).** A valid TOTP code can be reused within its
    ~30–90s window; no single-use timestep cache in Redis. Noted, not fixed.

None of the open items are exploitable-by-default given the current ownership
scoping. Before a public, multi-tenant launch: flip `REQUIRE_EMAIL_VERIFICATION`,
decide on the panel/WinRM TLS opt-in, and configure the trusted-proxy IP source (#10).

# ServerMind — Security Review

Scope: authentication, session/token handling, access control, credential
encryption, and command-execution safety. Reviewed at the end of Phase 13.

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

1. **Rate limiting (HIGH — do before public launch).** CLAUDE.md rule 8 asks for
   30 commands/min/user/server, and login needs brute-force protection. Not yet
   implemented. Recommend `slowapi` + the existing Redis: ~5 login attempts/min/IP
   and 30 command-exec/min/user.
2. **Token revocation (MEDIUM).** `logout` is client-side only; tokens stay valid
   until expiry. Add a Redis denylist (jti) or a `token_version` column bumped on
   logout/password-change.
3. **SSH host-key verification (MEDIUM).** Connections use `AutoAddPolicy`
   (trust-on-first-use) and store a fingerprint, but reconnects don't verify
   against it (CLAUDE.md rule 6). Enforce the stored fingerprint on reconnect.
4. **Email verification (MEDIUM for public signup).** Registration sets
   `is_verified=True` (Phase-1 decision). Enable real verification before opening
   public signups.
5. **2FA (MEDIUM).** `totp_secret`/`totp_enabled` columns exist; the
   enable/verify endpoints are not built yet.
6. **Panel/WinRM TLS (LOW/MEDIUM).** Hosting + WinRM use `verify=False` /
   `server_cert_validation='ignore'` (self-signed panels are common). Offer a
   per-server "strict TLS" opt-in for properly-certificated hosts.
7. **Encryption-key strength (LOW — mitigated).** A short `ENCRYPTION_KEY` is
   null-padded. Docs + the new startup warning cover it; consider hard-failing in
   production if it isn't 64 hex chars.
8. **WebSocket token in query string (LOW).** Browser WebSockets can't set
   headers, so the JWT rides in the URL (may appear in proxy logs). Consider
   short-lived single-use WS tickets.
9. **passlib/bcrypt log noise (cosmetic).** A harmless "error reading bcrypt
   version" line appears on first hash. Pin `bcrypt<4.1` or bump passlib to
   silence; hashing is unaffected.

None of the open items are exploitable-by-default given the current ownership
scoping, but **rate limiting and token revocation should land before a public,
multi-tenant launch.**

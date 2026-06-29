# ServerAlly — Production Deployment Runbook

Deploys the full stack (FastAPI backend + built React frontend) with Docker
Compose, behind a CyberPanel / OpenLiteSpeed reverse proxy that terminates SSL.

```
Browser ──HTTPS──▶ CyberPanel OLS (Let's Encrypt) ──▶ 127.0.0.1:8080 (frontend nginx)
                                                          ├─ static SPA
                                                          ├─ /api/  ─▶ backend:8000
                                                          └─ /ws/   ─▶ backend:8000
Backend ──▶ Postgres (Supabase)   ──▶ Redis (Upstash)
```

> **Two ways to ship ServerAlly.** This runbook is the **hosted (SaaS)** path — *we*
> run it for customers. There's also a **self-hosted, licensed** path where customers
> install it on their own VPS and activate a license (we never touch their data) — see
> [docs/SELF-HOSTED-LICENSING.md](docs/SELF-HOSTED-LICENSING.md). Both use the same Docker
> packaging below; the self-hosted edition adds a license check + a one-command installer.

---

## 1. Prerequisites

- A VPS with **Docker** + **Docker Compose v2** and **CyberPanel** installed.
- A domain/subdomain pointed at the VPS (e.g. `app.example.com`).
- Managed **PostgreSQL** (Supabase free tier) and **Redis** (Upstash free tier),
  or use the bundled `selfhost` profile (see §6).
- An **Anthropic API key**.

---

## 2. Provision datastores

**Supabase** → create a project → copy the connection string and convert it to the
asyncpg driver:

```
DATABASE_URL=postgresql+asyncpg://USER:PASSWORD@HOST:5432/postgres
```

**Upstash** → create a Redis database → copy the `rediss://` URL:

```
REDIS_URL=rediss://default:PASSWORD@HOST:6379
```

---

## 3. Get the code & create `.env.prod`

```bash
git clone <your-repo> servermind && cd servermind
cp .env.example .env.prod
```

Edit `.env.prod`. **Generate fresh secrets** (do NOT reuse dev values):

```bash
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(32))"
python3 -c "import secrets; print('ENCRYPTION_KEY=' + secrets.token_hex(32))"
```

Minimum production values:

```bash
APP_ENV=production
SECRET_KEY=<generated>
ENCRYPTION_KEY=<generated>          # NEVER change this after servers are saved — it decrypts stored credentials
ENABLE_SCHEDULER=true
EXECUTION_BACKEND=celery            # run playbook/AI-chat execution on the worker (durable); "inline" runs it in the web process
SENTRY_DSN=                         # optional (see §7)

DATABASE_URL=postgresql+asyncpg://...   # Supabase
REDIS_URL=rediss://...                  # Upstash

ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514

ALLOWED_ORIGINS=["https://app.example.com"]   # JSON array; include every public origin

# Email (alerts) — optional
SMTP_USER=...
SMTP_PASSWORD=...
EMAIL_FROM=noreply@example.com

# Frontend build args (baked into the bundle — must be your PUBLIC https/wss URLs)
VITE_API_URL=https://app.example.com
VITE_WS_URL=wss://app.example.com
VITE_APP_NAME=ServerAlly
VITE_APP_TAGLINE=Your AI companion to manage, automate, and secure any server — without the expertise.
```

> `.env.prod` is git-ignored. Keep it off version control.

---

## 4. Build & start

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

This builds the images, runs `alembic upgrade head` on the backend, seeds the
official playbooks, starts the scheduler, brings up the **Celery worker**, and
serves the SPA on `127.0.0.1:8080`.

Check status:

```bash
docker compose -f docker-compose.prod.yml ps
curl -s http://127.0.0.1:8080/health      # {"status":"ok","app":"ServerAlly"}
```

### Durable execution worker
The stack includes a `worker` service (Celery) that runs playbook and AI-chat
command execution off the web process, so a run survives client disconnects and
web restarts, can be reconnected to, and can be cancelled (Update 15). It is
active when `EXECUTION_BACKEND=celery` (the backend enqueues to it); with `inline`
the worker idles harmlessly and execution runs in the web process.

```bash
docker compose -f docker-compose.prod.yml logs -f worker   # "celery@… ready" + tasks: run_playbook, run_chat
```

The worker runs with `ENABLE_SCHEDULER=false` — only the backend runs the
scheduler, so scheduled jobs never fire twice. Add throughput with
`--scale worker=N`.

---

## 5. CyberPanel reverse proxy + SSL

1. **CyberPanel → Websites → Create Website** for `app.example.com`.
2. **Websites → Manage → Rewrite Rules** (or **vHost Conf**) — proxy to the
   frontend container:

   ```
   RewriteEngine On
   RewriteRule ^/(.*)$ http://127.0.0.1:8080/$1 [P,L]
   ```

   For WebSockets, ensure the OLS proxy context allows upgrades (CyberPanel's
   "WebSocket Proxy" panel: URI `/ws/`, backend `127.0.0.1:8080`).
3. **SSL → Manage SSL → Issue** (Let's Encrypt) for `app.example.com`. CyberPanel
   auto-renews.
4. Force HTTPS redirect (CyberPanel SSL panel toggle).

Visit `https://app.example.com` — the login screen should load.

---

## 6. (Alternative) Self-hosted Postgres + Redis

Skip §2 and instead set in `.env.prod`:

```bash
DATABASE_URL=postgresql+asyncpg://servermind:STRONGPASS@postgres:5432/servermind
REDIS_URL=redis://redis:6379/0
POSTGRES_USER=servermind
POSTGRES_PASSWORD=STRONGPASS
POSTGRES_DB=servermind
```

Then bring the stack up with the datastores:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml --profile selfhost up -d --build
```

---

## 7. Sentry (optional)

Create a project at sentry.io, copy the DSN into `SENTRY_DSN` in `.env.prod`,
then `docker compose ... up -d` to restart the backend. Errors and 10% of traces
are reported, tagged with `APP_ENV` and `APP_VERSION`.

---

## 8. Smoke tests

After deploy, verify each platform path:

- [ ] `GET /health` returns ok (via the public domain)
- [ ] Register a user, log in, set language
- [ ] **Linux/SSH:** add a server (password + key), Test connection, Detect OS,
      view live metrics, run an AI Chat command, open the Terminal
- [ ] **Windows/WinRM:** add a `winrm` server (port 5985), Test, Detect OS, run a
      PowerShell command via AI Chat (Terminal is SSH-only by design)
- [ ] **Hosting:** add a `hosting` account (CyberPanel/cPanel/Plesk), Test, open
      the Hosting tab, list websites
- [ ] Run a Playbook; generate + run a Script
- [ ] Create a Scheduled task; confirm it fires
- [ ] Run a Security scan; run a Backup, then Restore
- [ ] Invite a teammate, accept the invite, confirm a viewer cannot execute
- [ ] WebSocket terminal/chat stream works through the proxy (wss)

---

## 9. Operations

```bash
# Logs
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs -f frontend

# Apply new migrations (also runs automatically on backend start)
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head

# Deploy an update
git pull
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build

# Restart / stop
docker compose -f docker-compose.prod.yml restart backend
docker compose -f docker-compose.prod.yml down
```

### Scaling note
The backend runs as a **single process** so the in-process APScheduler (scheduled
tasks, metrics, backups) fires exactly once. To run multiple web workers, keep
`ENABLE_SCHEDULER=true` on **one** dedicated backend and set it to `false` on the
others, then load-balance across them. The `worker` service already runs with
`ENABLE_SCHEDULER=false`; scale it with `--scale worker=N` for more execution
throughput.

### Backups of ServerAlly itself
Back up the Postgres database regularly (Supabase has automatic backups; for
self-host, `pg_dump`). The `ENCRYPTION_KEY` is required to decrypt stored server
credentials — store it in a password manager. Losing it means re-adding every
server's credentials.

# ServerMind — Local Dev Operations

Day-to-day guide for running ServerMind on this machine.
(For production deployment, see `DEPLOY.md`. For credentials, see your exported PDF.)

---

## Services & ports

| Service | Port | URL | Notes |
|---|---|---|---|
| Frontend (Vite) | **5190** | http://localhost:5190 · http://192.168.1.136:5190 (LAN) | Dedicated port; 5173 is used by another local project |
| Backend (FastAPI) | **8888** | http://localhost:8888 · /docs · /health | uvicorn with auto-reload; 8000 is used by another local project |
| PostgreSQL | **5432** | localhost:5432 | Docker container `servermind_postgres` (data in a named volume) |
| Redis | 6379 | localhost:6379 | Optional today (scheduler is in-process); a shared redis on 6379 is fine |

> **LAN IP `192.168.1.136` can change** after a router reboot. Re-check with `ipconfig getifaddr en0`.

---

## ▶️ Start (in this order)

Order matters: **DB → backend → frontend**. The backend connects to Postgres and runs migrations on startup, so the DB must be up first.

**Terminal 1 — Database**
```bash
cd /Users/shafin/Documents/ServerMind
docker compose up -d postgres
```

**Terminal 2 — Backend** (wait until Postgres is healthy)
```bash
cd /Users/shafin/Documents/ServerMind/backend
source venv/bin/activate
uvicorn main:app --reload --port 8888
```

**Terminal 3 — Frontend**
```bash
cd /Users/shafin/Documents/ServerMind/frontend
npm run dev
```

Then open **http://localhost:5190**. Leave Terminals 2 & 3 running (both hot-reload on code changes).

### Durable execution (optional — Update 15)
By default playbook runs execute in the backend process (`EXECUTION_BACKEND=inline`, no worker needed). To use the durable Celery path, set `EXECUTION_BACKEND=celery` in `.env` and run a worker in a 4th terminal (needs Redis up):
```bash
cd /Users/shafin/Documents/ServerMind/backend && source venv/bin/activate
celery -A app.celery_app worker --loglevel=info
```
See `docs/UPDATE-15-EXECUTION.md`.

---

## ⏹️ Stop

```bash
# Frontend / Backend: press Ctrl-C in their terminal tab
# Database (keeps data):
docker compose stop postgres
# Database (remove container, keeps data volume):
docker compose down
```

To stop a server whose terminal you've lost:
```bash
lsof -nP -iTCP:8888 -sTCP:LISTEN | awk 'NR>1{print $2}' | xargs kill   # backend
lsof -nP -iTCP:5190 -sTCP:LISTEN | awk 'NR>1{print $2}' | xargs kill   # frontend
```

---

## 🔍 Status checks

```bash
docker ps --format '{{.Names}}  {{.Status}}' | grep servermind      # is the DB up?
curl -s http://localhost:8888/health                                # {"status":"ok",...}
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5190/     # 200 = frontend up
```

---

## 🛠️ Database tasks

```bash
cd backend && source venv/bin/activate

alembic upgrade head           # apply all migrations (runs automatically on backend start too)
alembic current                # show current migration revision
alembic downgrade -1           # roll back one migration
alembic revision --autogenerate -m "describe change"   # create a new migration after model edits
```

Open a psql shell into the container:
```bash
docker exec -it servermind_postgres psql -U servermind -d servermind
```

---

## 🚑 Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Browser shows a **Laravel/Vite welcome page** | Opened port 5173 (another project) | Use **http://localhost:5190** |
| `npm run dev` says **port 5190 in use** | A stale Vite is still running | `lsof -nP -iTCP:5190 -sTCP:LISTEN` → `kill <PID>`, then retry |
| App loads but **every API call fails / login spins** | Backend not running, or started before DB was ready | Ensure Terminal 1 (DB) is healthy, then (re)start Terminal 2 |
| Backend exits with **connection refused / asyncpg** error | Postgres isn't up yet | `docker compose up -d postgres`, wait a few seconds, restart backend |
| **AI Chat / Script Generator** errors or does nothing | `ANTHROPIC_API_KEY` is blank in `.env` | Add your key to `.env`; backend auto-reloads |
| Another LAN device **can't reach 192.168.1.136:5190** | macOS firewall blocking Node, or IP changed | Allow Node in System Settings → Network → Firewall; re-check IP with `ipconfig getifaddr en0` |
| WebSocket (Terminal/Chat) **won't connect** | Backend down, or opened over a host the proxy doesn't cover | Confirm backend up; the app derives ws:// from the page origin via the Vite proxy |

---

## 📌 Gotchas / notes

- **`backend/.env` is a symlink** to the root `.env` — edit only the root file.
- **Never change `ENCRYPTION_KEY`** once servers are saved — it decrypts their stored credentials.
- **Postgres data** lives in the `postgres_data` Docker volume and survives `docker compose down`. To wipe it (destructive): `docker compose down -v`.
- **Frontend env is build/boot-time** — after editing `VITE_*` vars in `.env`, restart `npm run dev`.
- The interactive API docs at **/docs** are available in dev only (hidden when `APP_ENV=production`).

# Update 23 — "Installed" tab per server

> "I ran WordPress on TS3, closed the window, and lost the post-install info." Now every
> server has an **Installed** tab that re-shows what ServerAlly installed (with the access
> card) and can live-scan the box for everything that's actually running.

## Two sources

- **Installed by ServerAlly (from records):** the latest successful playbook run per
  (playbook, access URL), with its access card re-derived from the playbook's
  `access_info` + that run's inputs — `GET /api/servers/{id}/installed`. No server access
  needed; works even if the box is offline.
- **Detected on the server (live scan):** a read-only SSH probe for OS, web servers,
  databases, runtimes, Docker containers, control panels and listening ports —
  `POST /api/servers/{id}/installed/scan` (execute-gated; Linux/SSH only).

## Secrets are masked

Install inputs (`variables_used`) and access-card fields are masked when the variable name
looks credential-ish (`PASS`/`PASSWORD`/`PWD`/`SECRET`/`TOKEN`/`KEY`/`CRED`): the view
shows `••••••`, and an access-card field (e.g. `password`) that references a secret var is
dropped entirely. We never re-display a stored credential.

> ✅ **Encrypted at rest (Update 23.1):** secret-named install inputs (`DB_PASS`,
> `ADMIN_PASSWORD`, …) are encrypted with the same AES-256-GCM used for SSH credentials
> (`app/services/secret_vars.py`) *before* they're written to `playbook_runs.variables_used`,
> and existing rows were backfilled (migration `017`). Non-secret inputs stay plaintext; the
> view still masks secrets. Net result: **all credentials are encrypted at rest** — a clean
> security line for the self-hosted edition.

## Reuse

`AccessCard` + `CopyButton` were extracted from `RunPlaybookModal` into a shared
`components/playbooks/AccessCard.tsx`, now used by both the run modal and the Installed tab.

## Verified (live on TS3)

Recovered the WordPress access card (`https://example.com/wp-admin/install.php` + note) the
user had lost; Install details showed `DB_PASS` masked to `••••••`; the live scan returned
Debian 12, nginx 1.22.1, mysql/mariadb 10.11.14, php 8.2.31, python 3.11.2, ports
22/80/3306 — which also confirmed the Tier 2 multi-distro WordPress genuinely installed on
Debian. Frontend build clean; 70 backend tests pass.

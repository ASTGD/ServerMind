# Update 23 — "Installed" tab per server

> "I ran WordPress on TS3, closed the window, and lost the post-install info." Now every
> server has an **Installed** tab that re-shows what ServerMind installed (with the access
> card) and can live-scan the box for everything that's actually running.

## Two sources

- **Installed by ServerMind (from records):** the latest successful playbook run per
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

> ⚠️ **Related finding:** `playbook_runs.variables_used` currently **stores** those secrets
> in plaintext (e.g. `DB_PASS`, `ADMIN_PASSWORD`). This view masks them on display, but the
> storage should also stop persisting them in plaintext (it violates the "never store
> credentials in plaintext" rule). Flagged as a follow-up.

## Reuse

`AccessCard` + `CopyButton` were extracted from `RunPlaybookModal` into a shared
`components/playbooks/AccessCard.tsx`, now used by both the run modal and the Installed tab.

## Verified (live on TS3)

Recovered the WordPress access card (`https://example.com/wp-admin/install.php` + note) the
user had lost; Install details showed `DB_PASS` masked to `••••••`; the live scan returned
Debian 12, nginx 1.22.1, mysql/mariadb 10.11.14, php 8.2.31, python 3.11.2, ports
22/80/3306 — which also confirmed the Tier 2 multi-distro WordPress genuinely installed on
Debian. Frontend build clean; 70 backend tests pass.

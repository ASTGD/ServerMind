# ServerAlly — Verified Feature Inventory (code-checked)

**Repo:** `/Users/shafin/Documents/ServerMind` · **Date:** 2026-07-25
**Method:** read `backend/app/routers/*.py`, `backend/app/services/*.py`, `backend/app/mcp/*.py`,
`backend/app/workers/*.py`, `backend/app/skills/*.md`, `backend/app/websocket/*.py`,
`frontend/src/routes/*.tsx`, `frontend/src/App.tsx`, playbook seed data in
`backend/app/services/playbook_service.py`, migrations in `backend/alembic/versions/`.
CLAUDE.md claims were treated as *hypotheses* and confirmed (or corrected) against code.

**Legend:** **FULL** = a real, usable, end-to-end feature. **PARTIAL** = exists but materially
narrower than the category name implies. **NONE** = not present in code (planned/documented ≠ present).

**Headline honesty note:** ServerAlly is an **AI operations layer over servers**, not a
control panel. It is strong at *diagnose / fix / audit / automate by conversation* and weak at
the *structured, per-site lifecycle management* (sites, domains, DNS, runtime versions, deploy
pipelines, queue workers) that Ploi / RunCloud / Forge / SpinupWP treat as their core product.

---

## 1. Server connection & management — **FULL** (multi-protocol), with one untested leg

| Protocol | Status | Proof |
|---|---|---|
| SSH (Linux/Unix) | FULL, live-proven | `backend/app/services/ssh_service.py`, `connection_manager.py:31` |
| WinRM (Windows Server) | Built, **never live-validated** (mock-tested only) | `backend/app/services/winrm_service.py`, `connection_manager.py:39`; `docs/CONTINUE-HERE.md` §1.1 |
| RDP (Windows desktop) | FULL as an *asset type* + live in-browser desktop via guacd | `backend/app/services/rdp_service.py`, `backend/app/websocket/rdp_tunnel.py`, `backend/app/routers/rdp.py` |
| Hosting panels (API) | PARTIAL — see §4 | `backend/app/services/hosting_service.py` |

- **Router:** `backend/app/routers/servers.py` — list/create/get/update/delete, `POST /{id}/test`,
  `POST /{id}/trust-key` (SSH fingerprint TOFU), `POST /{id}/detect`, `GET /{id}/metrics`.
- **OS detection:** `metrics_service.detect_os()` — distro/version/arch, and it *also detects an
  installed control panel* and writes `server.panel_type` (`routers/servers.py:119,325`).
- **Credentials:** AES-256-GCM at rest (`crypto_service.py`), never returned in API responses.
- **Asset categories:** Bare Metal · VPS · Hosting · Windows (WinRM) · Windows (RDP) · Cloud
  (migration `026_add_server_category.py`, `frontend/src/lib/assetCategories.tsx`).
- **Installed-software inventory:** live read-only SSH probe (web server, DB, PHP/Node/Python/
  Docker versions, containers, panel, listening ports) — `backend/app/services/installed_service.py`,
  page `frontend/src/routes/Installed.tsx`.

**Gap:** no agent/daemon on the server (pure agentless SSH/WinRM). No bulk "provision this OS
image" step — you bring an existing box.

---

## 2. Server PROVISIONING (blank VPS → working web stack) — **PARTIAL**

**What genuinely exists:** 50 seeded, one-click playbooks (`playbook_service.py`, `OFFICIAL_PLAYBOOKS`,
seeded on startup) executed over SSH/WinRM with live streamed output, a pre-flight guard
(root + clean-box + supported-OS + RAM), a multi-distro shim (`_DISTRO`, apt|dnf, ufw|firewalld,
SELinux), an OS guard (`supported_os_for` / `os_matches`), a readiness pre-check
(`check_readiness`), and a post-install "access card" (`access_info`, migration 010).
Runner: `backend/app/workers/playbook_tasks.py` (Celery/Redis) + `routers/playbooks.py`
(incl. `POST /{id}/run-multi` = run one playbook across many servers).

**Can it take a blank VPS to a working web stack?** Yes, for a *first* stack:
- `lemp-stack` / `lamp-stack` install nginx|apache + MariaDB + PHP-FPM + extensions.
- `wordpress` goes further and is the closest thing to real provisioning: creates the DB + DB user,
  downloads WP, writes `wp-config.php`, **writes an nginx vhost** for `{{DOMAIN}}`, opens the
  firewall, `nginx -t`, then runs `certbot --nginx` for SSL (`playbook_service.py:231+`).

**Why it is still PARTIAL vs a control panel:**
- It is **one-shot scripting, not lifecycle management**. There is **no `sites` table, no site
  model, no vhost manager** for plain (non-panel) servers — grep confirms none. After the
  WordPress playbook runs, ServerAlly has no structured record of that site, no way to edit its
  vhost, change its docroot, add a second site on the same box through UI, or delete it.
- No system-user isolation per site, no PHP-FPM pool per site, no per-site nginx template library.
- Control-panel playbooks (CyberPanel, HestiaCP, aaPanel, CloudPanel, Webmin, Virtualmin,
  cPanel/WHM, Plesk, DirectAdmin) exist — i.e. we can *install a competitor's control panel* —
  but per the code comments these run official vendor installers and are `bash -n`-checked, **not
  run end-to-end**; only CyberPanel is live-proven.
- RHEL/AlmaLinux path of the `_DISTRO` layer is written but **never smoke-tested** (`CONTINUE-HERE.md` §1.4).

**Full seeded playbook list (50)** — `backend/app/services/playbook_service.py`:

*Linux · setup (7):* `swap-file` Create and Enable Swap File · `set-timezone` Set Server Timezone ·
`docker` Docker + Docker Compose · `nodejs-pm2` Node.js LTS + PM2 · `python-env` Python 3 + pip +
virtualenv · `lemp-stack` LEMP Stack (Nginx + MySQL + PHP) · `lamp-stack` LAMP Stack (Apache + MySQL + PHP)

*Linux · security (6):* `ufw-setup` UFW Firewall Setup · `initial-hardening` Initial Server Security
Hardening · `fail2ban` Fail2Ban Install + Config · `ssh-key-auth` Enforce SSH Key Authentication Only ·
`letsencrypt` Certbot + Let's Encrypt SSL · `security-audit` Security Audit Report

*Linux · backup (4):* `mysql-backup-local` MySQL Auto Backup (local cron) · `postgres-backup`
PostgreSQL Auto Backup · `mysql-backup-s3` MySQL Auto Backup to S3 · `rclone-setup` Rclone Cloud Sync Setup

*Linux · deployment (9):* `wordpress` WordPress (Nginx + MySQL + PHP) · `portainer` Portainer ·
`uptime-kuma` Uptime Kuma · `ghost-cms` Ghost CMS · `nextcloud` Nextcloud · `gitea` Gitea ·
`n8n` n8n · `vaultwarden` Vaultwarden · `nodejs-app-github` Deploy Node.js App from GitHub

*Linux · control-panel (9):* `cyberpanel` CyberPanel (OpenLiteSpeed) · `hestiacp` HestiaCP ·
`aapanel` aaPanel · `cloudpanel` CloudPanel · `webmin` Webmin · `virtualmin` Virtualmin (GPL) ·
`cpanel-whm` cPanel / WHM · `plesk` Plesk · `directadmin` DirectAdmin

*Linux · monitoring (3):* `netdata` Netdata Real-time Monitoring · `prometheus-grafana`
Prometheus + Grafana Stack · `disk-alert` Disk Usage Email Alert

*Linux · maintenance (3):* `full-update` Full System Update + Cleanup · `clean-logs` Clear Old Logs +
Temp Files · `find-large-files` Large Files Report

*Windows · setup (5):* `win-chocolatey` Install Chocolatey · `win-openssh` Enable OpenSSH Server ·
`win-iis` Install IIS Web Server · `win-nodejs` Install Node.js LTS + PM2 (Windows) · `win-docker`
Install Docker Engine (Windows Server)

*Windows · security (4):* `win-firewall` Configure Windows Firewall Rules · `win-updates` Enable
Automatic Windows Updates · `win-rdp-secure` Harden RDP Access · `win-audit` Windows Security Audit Report

> CLAUDE.md lists `win-wordpress-iis`, `win-sqlserver-express`, `win-aspnet` — **these are NOT seeded.**
> Doc is stale; code has 9 Windows playbooks, not 12.

Also: **AI script generator** (`routers/scripts.py` → `ai_service.generate_script`) produces custom
bash/PowerShell on demand, saved to `user_scripts` and runnable — `frontend/src/routes/ScriptGenerator.tsx`,
`MyScripts.tsx`.

---

## 3. Cloud provider integrations — **PARTIAL (import only, never create)**

`backend/app/services/cloud_service.py`, `routers/cloud_accounts.py`, migration `027_create_cloud_accounts.py`.

- **5 providers:** AWS (boto3/EC2), DigitalOcean, Hetzner, GCP, Azure — `SUPPORTED_PROVIDERS` line 29.
- **Flow:** connect account by API key (verified *before* saving) → `GET /{id}/instances` discover →
  `POST /{id}/import` re-fetches live and imports selected instances as assets (dedupe via
  `servers.cloud_instance_id`, respects the plan server cap).
- Credentials stored AES-256-GCM as a provider-shaped JSON blob.

**Hard limits:**
- **No provisioning.** There is no create/destroy/resize/reboot/snapshot call anywhere — only
  `verify()` and `list_instances()` per adapter. We cannot spin up a droplet/EC2 from ServerAlly.
- A cloud API never hands over a login, so import only *prefills* rows — the user must supply one
  SSH username + key/password for the batch.
- Import happy-path is **live-unverified** for all 5 providers (only reject/error paths tested).

---

## 4. Website / site management — **PARTIAL, and only on CyberPanel**

- **CyberPanel (live-proven):** `backend/app/services/cyberpanel_cli.py` drives the `cyberpanel` CLI
  over the SSH channel — `list_websites`, `create_website`, `delete_website`, `issue_ssl`,
  `list_databases`, `create_database`. Create is **verified in code** (confirms the domain actually
  appears in `listWebsitesJson` before reporting success). UI: `frontend/src/routes/Hosting.tsx`
  (Websites / Databases / Email tabs). API: `routers/hosting.py`.
- **cPanel adapter** (UAPI): list domains, list/create DB, list/create email — reaches real cpsrvd,
  blocked on a license, happy path unverified.
- **Plesk adapter:** server info, list/create domains — mock-tested only.
- **DirectAdmin adapter:** list sites/DBs/email + create — mock-tested only, comments say write ops unverified.
- **CyberPanel HTTP API** is deliberately *verify-only* (`verifyConn`); everything real goes through the CLI.

**Missing entirely (all major competitors have these):**
- Any site abstraction for **plain servers** — no vhost create/edit, no docroot change, no
  subdomain/alias management, no per-site system user, no "clone to staging", no site list UI.
- No domain/alias/redirect management, no `.htaccess`/nginx-config editor UI (files can be edited
  via the file manager, but that is raw editing, not managed config).
- Email management exists only as thin cPanel/DirectAdmin passthrough; nothing for plain servers.

---

## 5. Deployment (git deploy, auto-deploy, zero-downtime, staging) — **PARTIAL / weak**

What exists:
- **`github-deploy` Ally mission skill** (`backend/app/skills/github-deploy.md`, `mode: mission`,
  budget 25) — Ally clones a repo, detects the stack, builds, runs, secures, verifies it, and
  "leaves a clean redeploy path". Adaptive and impressive, but it is a *conversation*, not a pipeline.
- **`nodejs-app-github` playbook** — `git clone` (or `git pull` if the dir exists) → `npm install
  --production` → `pm2 delete && pm2 start` → `pm2 save`. Re-runnable, so it is a manual redeploy
  button. **`pm2 delete` before `start` means it is explicitly NOT zero-downtime.**
- **`migrate-website` mission skill** — cross-server site migration (files + DB) using the mission
  engine's `transfer` action; source is read-only. Live-proven per the decisions log.

**NOT present (verified by grep across `backend/app`):**
- No inbound deploy webhook / no `POST /deploy` endpoint / no GitHub App or OAuth integration —
  nothing listens for a push. `webhook` in the codebase is only *outbound* alert delivery
  (`notification_service.py`).
- No deploy scripts stored per site, no deploy history/rollback, no atomic-release/symlink deploys,
  no zero-downtime reload, no build-command config, no environment-variable manager.
- No staging environment / clone-site feature.

This is one of the biggest structural gaps versus Ploi/Forge/RunCloud.

---

## 6. Runtime / version management (PHP, Node, Python) — **NONE**

- Versions are **detected and reported only** — `installed_service.py:140-143` echoes
  `php/node/python/docker` versions; the `_DISTRO` layer detects the running PHP-FPM service/socket
  at install time (`playbook_service.py:154`).
- Grep for `php_version|change php|switch php|nvm` across `backend/app` + `frontend/src` returns
  **nothing but those two detection lines.** There is no endpoint, service, or UI to install a PHP
  version, switch a site's PHP version, edit `php.ini` / FPM pool settings, or manage Node/Python
  versions. Ally could do it conversationally by running commands, but there is no product feature.

---

## 7. SSL certificates — **PARTIAL**

- `letsencrypt` playbook (certbot + cert issuance) and the `wordpress` playbook's inline
  `certbot --nginx ... --redirect`.
- **CyberPanel:** `POST /api/servers/{id}/hosting/websites/{domain}/ssl` → `cyberpanel_cli.issue_ssl`
  (live-proven) + MCP tool `serverally_issue_ssl`.
- **`domain-ssl` mission skill** (recipe) — checks DNS first, then issues a free cert, and honestly
  refuses if DNS is not pointed. **`ssl-troubles` diagnostic skill** — expiry/renewal/config triage.

**Missing:** no certificate inventory or expiry dashboard, no auto-renew monitoring or expiry alerts,
no custom/uploaded certificate management, no wildcard/DNS-01 flow, no per-site SSL toggle for plain
servers. Certbot's own cron does the renewing; ServerAlly does not watch it.

---

## 8. DNS management — **NONE**

Grep for `cloudflare|dns record|nameserver|route53|dns_service` across `backend/app` and
`frontend/src` returns exactly one hit: `config.py:139` "Cloudflare R2" (object storage, unrelated).

Ally *reads* DNS (`dig`/`host`) inside skills (`domain-ssl.md`, `email-deliverability.md`) to check
whether a domain points here and to inspect SPF/DKIM/DMARC — but ServerAlly cannot create, edit, or
delete a DNS record anywhere. "Cloudflare API: manage DNS" is still an unchecked backlog item in CLAUDE.md.

---

## 9. Databases — **PARTIAL**

- **CyberPanel:** create + list databases via CLI (`cyberpanel_cli.create_database` / `list_databases`);
  cPanel/DirectAdmin adapters list+create; MCP tool `serverally_create_database` (takes the password
  as input and **never returns it**).
- **Playbooks** install MariaDB/MySQL and PostgreSQL as part of stacks; `wordpress` creates a DB + user + grants.
- **Backups** support `mysql` (mysqldump) and `postgres` (pg_dump) job types — §15.
- **`mysql-performance` skill** — slow-query/OOM/connection/buffer-pool triage runbook.

**Missing:** no database browser/query UI, no user/permission management UI, no import/export
(SQL upload/download) feature, no remote-access management, nothing at all for plain (non-panel)
servers beyond what Ally types into a shell.

---

## 10. Email — **PARTIAL (thin panel passthrough) / mostly NONE**

- `GET/POST /api/servers/{id}/hosting/email` — cPanel and DirectAdmin adapters only
  (`hosting_service.py:188-193, 301-313`). CyberPanel and Plesk adapters do **not** implement email.
- Hosting page has an Email tab (`frontend/src/routes/Hosting.tsx`).
- **`email-deliverability` skill** — SPF/DKIM/DMARC + mail-log diagnosis (read-only advice).
- Outbound app email (SMTP) exists for alerts/digests/invites — `notification_service.py`.

**Missing:** no mailbox management for plain servers, no forwarders/autoresponders/quotas UI, no
webmail, no mail-server install playbook, no DKIM key generation.

---

## 11. Cron / scheduled tasks — **FULL**

- `backend/app/services/scheduler_service.py` (APScheduler `AsyncIOScheduler`, `CronTrigger.from_crontab`,
  jobs reloaded from DB on startup), `routers/scheduler.py`:
  list/create/update/delete/toggle/**run-now**, plus `POST /api/parse-schedule` →
  `ai_service.parse_schedule` (natural language → cron, with a live preview in the UI).
- Task types: `command` | `playbook` | `user_script` (`scheduled_tasks`, migration 005).
- UI: `frontend/src/routes/Scheduler.tsx`.

**Nuance:** schedules run **from ServerAlly's scheduler**, not by writing crontab entries on the
server. That is arguably better (visible, editable, logged) but means ServerAlly must be up, and
existing server-side crontabs are not imported or managed. `ENABLE_SCHEDULER` gates the whole
scheduler so horizontally-scaled web nodes don't double-fire.

---

## 12. Queue workers / daemons / supervisor — **NONE**

- No supervisor/systemd-unit management anywhere. Grep for `supervisor|supervisord|queue worker|
  systemd unit` in `backend/app` returns only PM2 usage inside two playbooks and unrelated matches
  in `security_service`/`threat_service`.
- PM2 appears only as: `nodejs-pm2` (install PM2), `nodejs-app-github` (`pm2 start/save`),
  `win-nodejs`. No worker list, no restart/scale/stop controls, no worker health, no log tailing,
  no Laravel Horizon / queue:work equivalent.
- CLAUDE.md's documented `POST /api/servers/{id}/services/{name}/start|stop|restart` endpoints are
  **NOT implemented** — `routers/servers.py` has no services routes. Ally can restart a service by
  running a command; there is no service-management feature.

---

## 13. Firewall & security hardening — **PARTIAL → strong via AI, weak via UI**

- **Playbooks:** `ufw-setup`, `initial-hardening`, `fail2ban`, `ssh-key-auth`, `win-firewall`,
  `win-updates`, `win-rdp-secure`.
- **`harden-server` mission skill** (recipe, budget 25) — firewall + fail2ban + safe SSH hardening +
  auto security updates, with an explicit never-lock-you-out protocol and approval on every
  access-affecting step.
- **Safety layer:** `backend/app/services/safety_service.py` — Linux + Windows absolute blocklists,
  confirm-patterns, and a default-deny `is_read_only_command` classifier used by the mission
  verification gate and Ally's work record.

**Missing:** no firewall *rule manager* UI (no port list, no add/remove rule, no per-server rule
state), no fail2ban jail viewer/unban, no SSH key manager (deploy keys / authorized_keys UI),
no 2FA-for-SSH, no IP allowlist management. It is script-and-conversation hardening, not managed state.

---

## 14. Security scanning, malware / threat detection, incident response — **FULL (and a genuine differentiator)**

- **Security audit:** `backend/app/services/security_service.py` — 19 Linux checks (ssh_root_login,
  ssh_password_auth, ssh_empty_passwords, ssh_max_auth_tries, ssh_port, firewall_active, fail2ban,
  pending_updates, unattended_upgrades, empty_password_accounts, uid0_accounts, sudo_nopasswd,
  password_policy, world_writable, suid_binaries, sensitive_perms, listening_ports, mac_enabled,
  reboot_required) + 5 Windows checks (win_firewall, win_defender, win_rdp_nla, win_smb1, win_uac).
  Score 0-100 + A-F grade, all probes read-only, single-script sectioned battery.
  API `GET/POST /api/servers/{id}/security[/scan]`; UI `frontend/src/routes/Security.tsx`.
- **Threat / malware detection:** `backend/app/services/threat_service.py` (migration 023) — read-only
  IOC bundle: webshell signatures, PHP in `wp-content/uploads`, processes from `/tmp`/`/dev/shm`/deleted
  exe, rogue cron & systemd persistence, non-root UID-0 accounts, world-writable SUID, WordPress core
  checksum verification. Verdict `clean|suspicious|at_risk|compromised`. Scope covers whole account
  homes (CyberPanel child-domain layout), vendor/node_modules pruned, every probe time-bounded and
  fail-open, with a tested READ-ONLY guarantee (no probe may contain a mutating verb).
- **Proactive worker:** `backend/app/workers/threat_worker.py` — every 12 h across all SSH servers,
  in-app + email alert **only when a verdict newly worsens**.
- **Incident response:** `security-incident.md` (first response) and `security-incident-response.md`
  (mission, budget 40) — findings ledger, evidence preservation (copy, never delete), containment,
  clean with approval, harden, honest handover; explicit vendor-library protection (BUG-002 fix) and
  self-footprint recognition so ServerAlly's own SSH session isn't flagged as an intruder.
- **Incident narrative reports:** `POST /api/missions/{id}/incident-report` (Opus-tier synthesis of
  the durable mission transcript) and `POST /api/servers/{id}/report` (whole-server aggregate),
  with PDF / Markdown / copy export — `frontend/src/routes/ReportView.tsx`, `ServerReportView.tsx`.

**Missing:** no antivirus/ClamAV integration, no file-integrity monitoring (FIM) baseline/daemon, no
CVE/package vulnerability scanning, no compliance reporting (PCI/CIS benchmark), no WAF.

---

## 15. Backups & restore — **PARTIAL (local destination only)**

`backend/app/services/backup_service.py`, `routers/backups.py`, migration `008_create_backups.py`,
UI `frontend/src/routes/Backups.tsx`.

- Types: `files` (tar.gz), `mysql` (mysqldump), `postgres` (pg_dump) — gzipped.
- Retention (keep-N prune of oldest), optional cron schedule via APScheduler (`schedule_backup`),
  run-now, run history, **restore** (tar -x / mysql / psql, from a chosen run or latest successful).
- DB passwords AES-256-GCM at rest, passed via `MYSQL_PWD`/`PGPASSWORD`, never on argv; commands `shlex`-quoted.
- **`setup-backups` mission skill** (recipe, budget 30) — finds docroots + DBs, writes the script,
  schedules it, and (the part everyone skips) **proves a restore works**.

**The gap that matters:** `Backup.dest_dir` defaults to `/var/backups/servermind` — backups land
**on the same server**. There is **no offsite destination in the feature** (no S3/R2/B2/Dropbox/
Google Drive target, no encryption-at-rest of the archive, no download-to-browser). Offsite exists
only as one-shot playbooks that write their own cron scripts (`mysql-backup-s3`, `rclone-setup`),
outside the managed backup system. Competitors' selling point is exactly off-server backups.
Also: no full-server/image snapshot, no per-site backup unit, no point-in-time restore.

---

## 16. Monitoring, metrics, alerting, uptime — **PARTIAL**

- **Metrics:** `metrics_service.py` collects CPU, RAM (total/used), disk (total/used), load 1/5/15
  (null on Windows), uptime — via one `/proc`+`df` script on Linux, CIM on Windows.
  Worker `metrics_worker.py` runs **every 5 minutes**, 7-day retention, marks servers online/offline
  with a consecutive-strike rule; RDP assets get a reachability-only path.
- **History API:** `GET /api/servers/{id}/metrics/history` (up to 168 h). Charts in
  `frontend/src/components/monitoring/*` + `ServerOverview.tsx`.
- **Alerts:** `alerts` table + `alert_worker.py` with a 1-hour cooldown. Channels: **email, webhook,
  Slack** (`notification_service.py`). **Metrics allowed: `cpu`, `ram`, `disk` only**
  (`routers/monitoring.py:53`). Conditions gt/gte/lt/lte, threshold 0-100.
- **Proactive fleet intelligence:** `fleet_service.py` — deterministic (zero AI cost) per-server
  health score 0-100 + grade + ranked findings with one-click actions; `GET /api/fleet/health`,
  Dashboard panel.
- **Fleet-health email digest:** `digest_service.py` + `digest_worker.py`, daily 08:00 UTC job,
  per-user cadence off/weekly/daily (migration 025).

**Missing:**
- **No uptime monitoring.** No HTTP/HTTPS site checks, no port checks, no ping, no response-time
  tracking, no status page, no downtime history/SLA. A server is "offline" only if the 5-minute
  metrics SSH fails.
- **No offline alert channel** — you cannot create an alert rule on "server went down"; alert
  metrics are hard-limited to cpu/ram/disk. Offline only surfaces in the fleet panel/digest.
- No per-process or per-service monitoring, no network I/O / disk I/O / inode metrics, no
  per-partition disk (root filesystem only), no custom metrics, no >7-day retention, no
  1-second/real-time streaming metrics (CLAUDE.md's `WS /ws/metrics/{id}` is **not implemented**).

---

## 17. Logs & log viewing — **PARTIAL**

- **`GET /api/activity`** + `frontend/src/routes/Logs.tsx` — a unified feed of *ServerAlly's own*
  activity: AI command runs (with plan, commands, output, status, risk) and playbook runs.
  This is an action/audit log, not server logs.
- **`GET /api/audit`** (`routers/audit.py`) — self-service security-activity log
  (also surfaced in Settings). **No admin/team-wide audit view, no retention/pruning.**
- **Missions page + reports** (`routes/Missions.tsx`, `Reports.tsx`) — full durable mission
  transcripts with expandable steps.
- **MCP activity feed** — migration 035, `mcp_activity_service.py`, live drawer in the top bar.

**Missing:** no server log viewer — no tailing of nginx/apache/php-fpm/mysql/syslog/journald in the
UI, no log search, no error-log aggregation per site, no log rotation management. Ally can `tail` a
log inside a conversation and the file manager can open a log file, but there is no log feature.

---

## 18. File management — **FULL (Linux/SSH only)**

`backend/app/services/file_service.py` (Paramiko SFTP, `ThreadPoolExecutor`, 2 MB read cap, binary
detection), `routers/files.py`: list, read, write, mkdir, delete, rename, **upload** (multipart),
**download** (octet-stream). Plus `file_service.transfer_between` — server→server SFTP streaming
(512 MB cap, never overwrites) used by cross-server missions.

UI: `frontend/src/routes/FileManager.tsx` — breadcrumb navigation, file table, **Monaco editor**,
"Ask Ally about this file" with **client-side secret redaction** before anything reaches the prompt
(`frontend/src/lib/redactSecrets.ts`).

MCP: `serverally_list_files` + `serverally_read_file` (server-side secret redaction + binary refusal).

**Gap:** SFTP means **SSH only** — no file manager for WinRM/RDP/hosting-panel assets. No archive
extract/compress, no chmod/chown UI, no multi-file/bulk operations, no search.

---

## 19. Terminal / SSH access — **FULL (Linux/SSH only)**

`backend/app/websocket/terminal.py` → `WS /ws/terminal/{server_id}` — real interactive PTY with
resize, session persistence/snapshot replay (`terminal_session_service.py`), xterm.js front end
(`frontend/src/components/terminal/*`, launcher button in the top bar, multi-session store
`terminalStore.ts`).

**Explicitly SSH-only** (`terminal.py:183-185`): WinRM and hosting assets have no PTY and fall back
to AI chat, which streams via `execute_stream`. RDP assets get the guacd desktop instead.

**All websocket endpoints that actually exist** (verified): `/ws/terminal/{server_id}` (PTY),
`/ws/chat` (the one Ally socket, per-message server target), `/ws/chat/{server_id}` (pinned alias),
`/ws/batch` (run one instruction across many servers), `/ws/playbook-run/{server_id}`,
`/ws/rdp` (guacd tunnel). There is **no** `/ws/metrics`.

**Gap:** no web terminal for Windows, no session recording/audit of terminal keystrokes, no shared/
collaborative sessions.

---

## 20. AI capabilities — **FULL, and the strongest area by far**

- **Chat / planning:** `ai_service.plan_commands` — JSON plan contract (intent, clarification,
  plan summary, commands with per-command risk + confirmation, post-execution message, follow-ups),
  a "DOER not advisor" rule (Ally runs read-only commands itself), `clarification_options` answer
  chips, multilingual (8 launch languages, `users.preferred_language`), markdown-formatted replies.
- **Safety pipeline:** every AI-proposed command passes `safety_service` (OS-aware blocklist +
  confirm patterns) before execution; role check (`can_execute`) on every execution path.
- **Missions (agentic loop):** plan step → run → observe → repeat, per-step safety validation,
  mid-mission approvals, Stop, per-skill budget (10-40), a `wait` action for long jobs, a `transfer`
  action for cross-server file moves, an executable roster spanning the whole fleet.
  **Durable + resumable** (`missions` table, migration 024, `mission_service.py`, orphan recovery on
  startup) and **detached** (`websocket/mission_runner.py` — a mission outlives the socket; multiple
  concurrent missions fan out to a per-connection hub with id-scoped approve/stop).
- **Verification gate:** `ai_service.verify_mission` on the HIGH model tier — an independent verifier
  gathers *read-only* proof (read-only is enforced by `is_read_only_command`, default-deny) and the
  mission finishes honestly `verified:false` rather than a false green. Verifier checks page
  **content**, not just HTTP status.
- **Structured result card:** `sanitize_mission_result` → headline + Found / Did / Left-for-you
  (migration 032).
- **Skills — 16 packaged expert runbooks** (`backend/app/skills/`): `wordpress-rescue`,
  `server-slow-triage`, `disk-cleanup`, `mysql-performance`, `ssl-troubles`, `nginx-errors`,
  `docker-troubles`, `security-incident`, `email-deliverability`, `security-incident-response`
  (mission, 40), `github-deploy` (mission, 25), `cyberpanel-host-website` (mission, 25),
  `migrate-website` (mission, 40), `harden-server` (mission, 25), `setup-backups` (mission, 30),
  `domain-ssl` (mission, 20). Routing is keyword-first (free) with a model-as-router menu fallback
  so paraphrases and non-English messages still hit the right skill.
- **Recipes:** mission-mode skills promoted into a browsable one-click gallery with typed variables
  — `routers/recipes.py`, `frontend/src/components/recipes/`.
- **Memory:** `ally_memories` (migration 020) — Ally saves facts/preferences/lessons, secret-filtered,
  capped, user-visible and deletable (`routers/memories.py`, Settings card + per-server widget).
  Plus a **code-level work record**: recent mutating commands surfaced from `command_logs` and
  auto-saved memory notes for high-risk successful changes (`ai_context_service._actions_done`,
  `memory_service.record_action`) — no model cooperation required.
- **Context:** `live_look_service` (fixed read-only SSH snapshot on problem reports),
  `scout_service` (read-only SFTP recon before file/cross-server jobs), server profile + fleet health
  + installed inventory + page context, all framed as *data, not instructions*.
- **Injection defence:** every attacker-controllable channel (live look, files, history, mission
  transcript, tool output) is explicitly framed as data; guarded by deterministic tests
  (`tests/test_ally_injection_evals.py`) and live sentinel attacks.
- **Smart Model Ladder:** `llm_service.complete(tier=low|default|high)` — Haiku for trivial,
  Sonnet default, Opus for the verifier; plus reactive escalation (struggling mission) and
  **proactive self-escalation** (`need_stronger` flag → one high-tier re-plan).
- **Multi-provider:** anthropic (default), openai, gemini, OpenAI-compatible, plus a hosted gateway
  provider (`llm_service.py:46-48, 108-109`); retry on empty/transient responses; prompt caching
  with a stable prefix / volatile tail split and cache-aware cost telemetry.
- **Artifacts:** Ally can emit tables and charts that render as Workspace panels (`split_artifacts`).
- **Dev Door** (`/dev`, admin-only, migration 030/031): prompt inspector (dry-run the exact prompt
  the live chat would build), eval runner + capture-as-eval flywheel, LLM judge, AI usage ledger,
  provider A/B — `routers/dev.py`, `services/dev_service.py`, `app/evals/`.

**Gaps:** no voice, no image/screenshot input, no autonomous unattended remediation (deliberate —
detect-and-ask by design), no anomaly detection on metrics, no auto-healing of crashed services
(both still unchecked backlog items).

---

## 21. Teams, roles, permissions — **FULL**

`backend/app/services/team_service.py` + `routers/team.py` + `dependencies/access.py`,
migration `009_create_team_tables.py`, UI `frontend/src/routes/Team.tsx` + `AcceptInvite.tsx`.

- Roles: **owner / admin / operator / viewer**. Email-bound invite tokens with an acceptance flow.
- Per-server access grants (`server_access.can_execute`, `can_view_logs`).
- Enforcement on every execution path (websocket terminal/chat/playbook-run, files write/mkdir/
  delete/rename/upload, backups create/run/restore, security scan, scheduler create); server
  update/delete require owner/admin. **A viewer can never execute even if granted `can_execute`**
  (role override, unit-tested).
- Read endpoints are team-aware via `accessible_servers`; MCP tools are scoped to the bearer's own
  accessible servers.

**Gaps:** no custom roles/granular permission matrix, no SSO/SAML/SCIM, no organizations/workspaces
(a "team" is one owner's circle), no per-action approval workflow, no team-wide audit view.

---

## 22. White-label / agency / client-facing features — **NONE**

Grep for `white.?label|agency|branding|client portal|reseller` across `backend/app` and
`frontend/src` returns exactly one hit — a code comment in `entitlements.py:32` noting room for an
"Agency tier later".

Nothing exists: no custom logo/domain/colors, no client-facing portal or read-only client access,
no per-client grouping/tagging of servers beyond free-text tags, no branded reports (reports carry
ServerAlly's own presentation), no reseller/sub-account model, no client billing. CLAUDE.md still
lists "White-label for agencies" as an unchecked backlog item.

---

## 23. Billing & plan limits — **PARTIAL, and currently NOT enforced**

- **Plan map:** `backend/app/services/entitlements.py` — `free` = 30 actions/mo + 2 servers;
  `pro` = 1000 actions/mo + 15 servers. Every feature ships on every plan by design (no feature flags).
- **Metering:** `metering_service.py` + `ai_usage` ledger (migration 019, extended by 021/022) —
  per-call model, tokens (incl. cache read/write), cost estimate, feature, skill. `GET /api/usage/me`
  + Settings "Ally usage" card + Dashboard `SubscriptionCard`.
- **Enforcement flag:** `ENFORCE_PLAN_LIMITS: bool = False` (`backend/app/config.py:29`). **Today
  every user has effectively unlimited servers and unlimited AI actions.** When on, it arms exactly
  two choke points: `metering_service.gate` (AI) and `servers_gate` (server create → 402).
- **WHMCS integration:** `routers/entitlements.py` — `POST /api/admin/entitlements/set`,
  `POST /reconcile` (nightly drift correction with an empty-list refusal + blast-radius 409 guard +
  admin exclusion), `GET /ping`, `GET /{email}`, all behind an `X-Entitlement-Key` shared secret.
  PHP module in `whmcs/serverally/` (`serverally.php`, `hooks.php`) — lints clean and has been
  driven against the real endpoint via a stub harness, but has **never run inside a real WHMCS**.
- **Claim flow:** provisioned users get a one-time claim link (`/claim`, `routes/Claim.tsx`).
- **Admin console:** `routers/dev.py` → `/api/dev/admin/*` (overview, users, user detail, entitlement
  log) — **read-only by design and tested to have no write routes and to never expose a credential**.
- **MCP plan gate:** `mcp_enabled_for` restricts MCP to paid tiers when `ENFORCE_PLAN_LIMITS` is on.

**Missing:** no payment provider integration in the app (deliberate — WHMCS owns money), no
in-app checkout/invoices/receipts, no trial logic, no usage-overage handling, no bonus-action grants
(the `action_grants` table is planned, not built), no dunning. Pricing v3 (two layers: platform
per-server + choice of AI) is **designed only** — `docs/PRICING-V3.md`; the code still implements v2.

---

## 24. API / CLI / MCP / integrations — **PARTIAL (MCP is FULL and a real differentiator)**

- **MCP server — FULL and live-proven.** Remote Streamable-HTTP MCP at `/mcp` (FastMCP mounted on
  FastAPI) with a **full OAuth 2.1 Authorization Server** (PKCE-S256, dynamic client registration,
  RFC 8414 metadata, hashed codes+tokens, refresh rotation, per-IP rate limiting) —
  `backend/app/mcp/{server,http_auth,oauth_provider}.py`, `routers/mcp_oauth.py`, migration 034.
  Verified working with a real Claude Desktop client against production.
  **22 tools:** *read (14)* `list_servers`, `get_fleet_health`, `get_server`, `get_metrics`,
  `get_security_scan`, `get_threat_scan`, `list_playbooks`, `list_missions`, `get_mission`,
  `list_sites`, `list_files`, `read_file`, `get_playbook_run`, `list_backups`; *write (7)*
  `run_security_scan`, `run_threat_scan`, `run_playbook`, `run_backup`, `create_site`, `issue_ssl`,
  `create_database`; *admin (1)* `run_command` (arbitrary shell, floored by the absolute blocklist +
  Rule-7 execute + audit).
  **3 additive consent scopes:** `mcp:read` (Read-only, default) / `mcp:write` (Full access) /
  `mcp:admin` (Full power). Credential-free by construction (strict field whitelists, tested).
  Costs **0 AI actions** — the customer's own AI does the thinking.
  Management UI: Settings → "Connected applications" (`routers/mcp_admin.py`, revoke a grant).
- **REST API:** exists and is JWT-authenticated, and `/docs` is served outside production — but
  there is **no public API product**: no user-generated API keys, no documented public API surface,
  no per-key scopes or rate limits. CLAUDE.md's "API access for users" is still unchecked.
- **Outbound integrations:** email (SMTP), generic webhook, Slack incoming webhook — alerts only
  (`notification_service.py`).

**Missing:** no CLI (`servermind run ...` is still a backlog item), no Slack/Telegram bot, no Zapier/
n8n/Make integration, no GitHub App, no Cloudflare/Route53, no PagerDuty/Datadog/Grafana export,
no inbound webhooks of any kind.

---

## 25. Mobile app / desktop app — **NONE**

Grep for `electron|react-native|capacitor|tauri` finds only transitive `package-lock.json` noise
(`electron-to-chromium` is a browserslist dependency; `react-native` is an unused optional field in
a lockfile entry). There is no mobile app, no desktop app, no PWA manifest, and no dedicated mobile
UI beyond Tailwind responsiveness. Both remain unchecked backlog items in CLAUDE.md.

---

## 26. Notable things we have that competitors likely do NOT

1. **A genuine agentic ops loop.** Missions plan→run→observe→repeat with per-step safety validation,
   mid-mission approvals, budgets, durability (survives a restart, resumable), and **detached
   execution** (survives the browser closing) — `websocket/mission_runner.py`, `mission_service.py`.
   No control panel has anything of this shape.
2. **An adversarial verification gate.** Ally is not trusted when it says "done": an independent
   HIGH-tier verifier must gather *read-only* proof, with read-only enforced in code, and it checks
   page **content** not just a 200. A mission can finish honestly "unverified" — `ai_service.verify_mission`.
3. **16 packaged expert runbooks (skills)** with deterministic + model-router matching across 8
   languages — a diagnostic *procedure* library, not a script library.
4. **Proactive malware/threat monitoring with guided incident response**, tuned against real
   compromises, with a hard read-only guarantee on the scanner and a reversible-first cleanup runbook.
5. **AI-written incident narratives and whole-server reports** generated from the durable mission
   transcript (not from chat memory), exportable to PDF/Markdown — a deliverable an agency can hand
   to a client or to management (`explain_incident`, `explain_server_report`).
6. **A production MCP server with full OAuth 2.1** — the customer connects Claude/ChatGPT to their
   fleet and pays for their own AI. Ploi has a bounded MCP; a full AS + 22 tools + 3 consent tiers
   incl. a guarded shell is well ahead.
7. **Cross-server missions with a native `transfer` action** — "back up the site on A and move it to
   B" as one instruction, with SFTP↔SFTP streaming through the backend.
8. **Long-term memory + a code-level work record** — Ally remembers what it did (including
   quarantine paths) without relying on the model to volunteer it.
9. **Smart Model Ladder** — per-task model tiering plus proactive self-escalation on hard/high-stakes
   requests, with a full cost ledger behind it.
10. **The Dev Door eval flywheel** — dry-run the exact production prompt, a 105+ case eval corpus in
    CI, capture-a-bug-as-a-test in one click, an LLM judge, and a cost/model observability tab.
    This is internal, but it is why behaviour changes can ship safely.
11. **Multilingual by design** — AI plans, explanations, and UI in 8 languages
    (`frontend/src/i18n/locales/`), which the incumbents do not do.
12. **Live in-browser RDP** via a hand-rolled Python guacd tunnel (`websocket/rdp_tunnel.py`) —
    Windows desktops beside Linux boxes in one console.
13. **Panel-agnostic breadth** — SSH + WinRM + RDP + 4 panel adapters + 5 cloud providers in one
    tool; competitors are Linux/SSH-only.
14. **Deterministic fleet intelligence + email digest at zero AI cost** — health scoring and the
    proactive digest are pure code, so they scale without a token bill.

---

## Cross-cutting corrections to CLAUDE.md (doc is stale in places)

| CLAUDE.md claims | Reality in code |
|---|---|
| 3 Windows app-deployment playbooks (`win-wordpress-iis`, `win-sqlserver-express`, `win-aspnet`) | **Not seeded.** 9 Windows playbooks total, none for app deployment. |
| `POST /api/servers/{id}/services/{name}/start\|stop\|restart` | **Not implemented** in `routers/servers.py`. |
| `WS /ws/metrics/{server_id}` (1 s live metrics) | **Not implemented.** Metrics are a 5-minute poll. |
| `GET/POST /api/scripts/{id}/run\|fork\|publish` | **Not implemented** — `routers/scripts.py` has generate/CRUD only (running goes through the chat WS). |
| "Dark/light toggle not built" (`docs/CONTINUE-HERE.md`, 2026-07-16) | **Built** 2026-07-22 — `frontend/src/store/themeStore.ts` (light/dark/system, persisted). |
| Backlog "GitHub: deploy from repo" marked shipped | True *as an AI mission*; there is no deploy pipeline, webhook, or redeploy history. |

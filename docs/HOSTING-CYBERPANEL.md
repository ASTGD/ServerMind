# Hosting Mode — CyberPanel (live findings, 2026-07-04)

> Validated against a real CyberPanel install (Ubuntu 24.04, the one Ally installed
> on TestServer4). This corrects assumptions the mock-only Phase-7 adapter made.

## The big finding

CyberPanel's **adminUser/adminPass HTTP API** (`https://<host>:8090/api/*`) is a
**cloud / remote-management surface only**. From the live `api/urls.py`, the real
endpoints are:

```
verifyConn, loginAPI, getUserInfo, changeUserPassAPI,
submitUserCreation, submitUserDeletion,
listPackage, changePackageAPI, fetchSSHKey,
remoteTransfer, fetchAccountsFromRemoteServer, FetchRemoteTransferStatus,
cancelRemoteTransfer, cyberPanelVersion, runAWSBackups,
submitWebsiteStatus, addFirewallRule, deleteFirewallRule,
ai-scanner/*, scanner/*
```

It does **NOT** expose website listing/creation, database creation, or SSL issuance.
Those live in the `websiteFunctions` app (`submitWebsiteCreation`, `fetchWebsitesList`)
as **session + CSRF web endpoints**, not the token-style API.

So our Phase-7 adapter was wrong on two counts:

| Adapter assumed | Reality |
|---|---|
| `test_connection` → `/api/verifyLogin` | endpoint is **`/api/verifyConn`** (returns `{"verifyConn": 1}`) |
| `list_websites` → `/api/fetchWebsites` | **does not exist** → HTTP 404 |
| `create_website` → `/api/createWebsite` | **does not exist** on this API |
| `issue_ssl` → `/api/issueSSL` | **does not exist** on this API |
| `create_database` → `/api/createDatabase` | **does not exist** on this API |

Live test after the `verifyConn` fix: connection test returns **HTTP 403** (not 404) —
the endpoint is correct; CyberPanel additionally requires **API access enabled for the
admin user** (CyberPanel → Users → API Access) and often the caller IP whitelisted.

## The reliable path: the `cyberpanel` CLI over SSH

`/usr/bin/cyberpanel` is installed and is the authoritative automation surface:

```
cyberpanel createWebsite --package Default --owner admin \
  --domainName example.com --email admin@example.com --php 8.1
cyberpanel createDatabase --databaseWebsite example.com \
  --dbName ex_db --dbUsername ex_user --dbPassword ****
cyberpanel issueSSL --domainName example.com
cyberpanel deleteWebsite --domainName example.com
# also: createUser, changePackage, listWebsitesJson, ...
```

This covers far more than the HTTP API, needs no API-access/IP-whitelist dance, and
uses the SSH channel ServerAlly **already has** (and that missions already drive).

## What changed now (this commit)

- `CyberPanelAdapter.test_connection` → `verifyConn` (real endpoint; parses
  `verifyConn`). `_post` maps 404 to a clear "no such endpoint" error.
- `list_websites` / `create_website` / `delete_website` / `issue_ssl` /
  `create_database` no longer hit non-existent endpoints — they raise a clear,
  honest `HostingError` pointing to the SSH/CLI path. The Hosting tab shows that
  message instead of a cryptic HTTP 404.

## H1 — SHIPPED (2026-07-04): CyberPanel operations via CLI-over-SSH

Built and **verified live** on the TestServer4 CyberPanel:

- **`cyberpanel_cli` service** runs `cyberpanel <function>` over the SSH channel the
  server already has (`connection_manager.execute`). Function names + flags were read
  from the live CLI, not guessed: `createWebsite --package … --owner … --domainName …
  --email … --php …`, `listWebsitesJson` (→ JSON), `deleteWebsite`, `issueSSL`,
  `createDatabase`, `listDatabasesJson`. Args are `shlex`-quoted.
- **A CyberPanel server is an SSH server with `panel_type='cyberpanel'`.** OS-detect
  now sets `panel_type` when it finds `/usr/bin/cyberpanel` (or `/usr/local/CyberCP`),
  so the **Hosting tab appears on the SSH box** and its actions run the CLI. No new
  credential storage — reuses the SSH creds. `hosting_service` routes CyberPanel ops
  to `cyberpanel_cli` when `connection_type=='ssh'` (verify-only API path otherwise).
- **Verify-after-create (important):** CyberPanel's `createWebsite` can print
  `{"success": 1}` to stdout while actually FAILING (it logs `Websites matching query
  does not exist` and skips creation — happens when creates run in rapid succession or
  on a domain with residual state). So `create_website` **confirms the domain is
  really in `listWebsitesJson`** before reporting success; otherwise it raises an
  honest error ("reported success but … was not actually created — try again"). The
  strict `_parse_status` also raises on `{"success": 0}` (even with `errorMessage:
  "None"`) instead of treating it as success.

Live proof: created `appdemo.serverally.org` + `diag2.serverally.org` through the app
(CLI-over-SSH), both appear Active in the Hosting tab. Rapid back-to-back browser
creates hit CyberPanel's internal race and were surfaced honestly by the verify guard.

### "Host a WordPress site" mission — SHIPPED (2026-07-04)
The `cyberpanel-host-website` skill (`mode: mission`, `backend/app/skills/`) is a
runbook Ally follows to host a full WordPress site via the CLI over SSH:
createWebsite → verify in list → `installWordPress` (admin password generated ON the
server to a root-only file, never shown in chat) → DNS check → issueSSL (skipped +
honest next-step if DNS doesn't point here) → curl-verify the site actually serves
WordPress (Host header, no DNS needed) → hand over.

Live-proven: "Host a WordPress site at blog.serverally.org, title 'ServerAlly Blog'"
→ mission ran the whole runbook and `blog.serverally.org` is live (independently
curl-verified from the dev machine: homepage 200 serving wp-content, wp-login 200,
`generator = WordPress`). Ally adapted past a plugin warning, correctly skipped SSL
(DNS not pointed yet), and left the password in `/root/wp_creds_<domain>.txt`.

`installWordPress` creates its own DB — no `createDatabase` needed. CLI signature:
`installWordPress --domainName X --email Y --userName U --password P --siteTitle "T" [--path p]`.

### H1 follow-ups (still open)
- Databases/Email/SSL buttons in the Hosting UI (service methods exist; wire them).
- Optional single retry-after-delay on the create race (weigh vs. orphan risk).

## H2 (next) — cPanel / Plesk, same pattern

Apply the H1 pattern (panel API for identity/verify, **CLI-over-SSH for actions**,
verify-after-write) to the other panels: cPanel has `whmapi1`/`uapi` CLIs + WP
Toolkit; Plesk has the `plesk bin` CLIs. Validate each live before trusting write ops.

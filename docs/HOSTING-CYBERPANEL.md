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

## H1 (next) — CyberPanel operations via CLI-over-SSH

The right design, confirmed by this test:

1. A CyberPanel "server" should carry **SSH access** (not just the panel password).
   Reframe hosting-mode: panel API for identity/verify, **CLI-over-SSH for actions**.
2. Add a **hosting actions engine**: `create_website`, `issue_ssl`, `create_database`,
   `install_wordpress`, `list_websites` — each a `cyberpanel …` CLI invocation, run
   through the existing SSH executor with the same safety validation.
3. Ally plans these as normal steps/missions (verify the site over HTTP after — no
   shell needed to confirm). "Host a full website" then becomes one mission:
   create site → DB → WordPress → SSL → verify URL.
4. cPanel/Plesk: revisit their adapters the same way (cPanel has `whmapi1`/`uapi`
   CLIs + WP Toolkit; validate live before trusting write ops).

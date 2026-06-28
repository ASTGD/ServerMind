# Risk 3 — Server identity verification (SSH host-key pinning)

> From the PM security audit: ServerMind connected to servers without verifying their
> identity (Paramiko `AutoAddPolicy` accepts any host key). If a server's host key
> changed — rebuilt, IP reused, or a man-in-the-middle — it would connect anyway. For
> a tool that stores credentials and runs commands as root, that was the last
> launch-blocker. Fixed with trust-on-first-use (TOFU) host-key pinning.

## How it works
- **Capture & pin (TOFU):** on the first successful connect to an SSH server, its
  host-key fingerprint (OpenSSH `SHA256:…`) is captured and stored in
  `servers.fingerprint`. Done in the router's test / add paths (which have a DB
  session); `ssh_service.pop_captured_fingerprint` exposes what was observed.
- **Verify on every connect:** `ssh_service._get_client` compares the presented
  fingerprint against the pinned one on each fresh connect. A mismatch raises
  `HostKeyMismatch` and the connection is **refused** — covering test, AI chat,
  playbook runs, and metrics alike (threaded via `connection_manager` from
  `server.fingerprint`).
- **Surface it:** a mismatch sets the server status to `host_changed`. The status pill
  shows "Identity changed" (red), the server card shows a warning popover, and the
  server page shows a banner explaining the two possibilities (rebuilt vs. intercepted).
- **Recover:** `POST /api/servers/{id}/trust-key` (the "Trust new key" button) clears
  the pinned fingerprint and re-pins on a fresh connect — for a legitimately rebuilt
  server. Requires manage rights and is audited (`server.trust_key`, old→new fingerprint).

## Verified (live VPS)
- First connect pins the real `SHA256:…`.
- A correct fingerprint matches and connects.
- A wrong fingerprint is **refused** (`host_key_changed=true`, connection blocked).
- `trust-key` clears and re-pins to the real key and reconnects.
- All existing SSH servers were backfilled with their current fingerprint.
- 58 tests pass; frontend build clean.

## Notes
- WinRM / hosting connections don't use SSH host keys; this applies to
  `connection_type='ssh'`.
- Servers added before this change get pinned on their next successful connect (or via
  the Test button); an unreachable server simply pins later.
- A host-key mismatch is surfaced as `host_changed` from **every** status path — the
  Test button *and* the background metrics worker — so a reinstalled server reads
  "Identity changed" (with the Trust-new-key recovery) rather than a misleading
  "offline".

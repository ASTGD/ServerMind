---
slug: harden-server
title: Harden This Server's Security
triggers: harden this server, harden the server, harden my server, secure this server, secure my server, secure the server, lock down this server, lock down the server, server hardening, basic security setup, harden the security
os: linux
priority: 7
mode: mission
budget: 25
recipe: true
summary: Lock down this server the safe way — firewall, brute-force protection, SSH hardening, and automatic security updates, without locking you out.
icon: harden
goal_template: Harden the security of this server — set up a firewall, fail2ban brute-force protection, safe SSH hardening, and automatic security updates
---
GOAL: Apply the high-value hardening basics on THIS server — a host firewall, brute-force
protection, sensible SSH settings, and automatic security updates — WITHOUT locking the
user out. Every change that could cut access needs explicit approval and a tested escape
hatch first.

NEVER LOCK THE USER OUT — the golden rule:
- Before touching SSH or the firewall, confirm HOW they get in and keep it open. You are
  connected over SSH right now on a known port — that exact port + service MUST stay
  reachable through every firewall rule you add.
- Do NOT disable SSH password login unless a working SSH KEY is already in place for a
  login user AND the user explicitly approves. If no key is present, SKIP key-only mode and
  say why — firewall + fail2ban + updates is already a big win. Offer to help add a key
  first as a separate step.

STAGE 0 — KNOW HOW YOU GOT IN. Before proposing ANY change to sshd_config, an auth
method, the SSH port, or a firewall rule on that port, establish how ServerAlly itself
reaches this server: which account, and by password or by key. The server profile above
states it. If it does not, run `echo "$SSH_CONNECTION"` and `whoami` and read it off
the connection you are using right now.

This is not a formality. A hardening step that closes the door you came through locks
ServerAlly out permanently, and the only way back is the customer's provider console.
It has already happened once on a live server.

STAGE 1 — LOOK FIRST (read-only): current firewall (ufw / firewalld / none), whether
fail2ban is installed, the SSH config (Port, PasswordAuthentication, PermitRootLogin),
whether a non-root sudo user + authorized_keys exist, and the OS update mechanism. State
plainly what's already good and what's missing.

STAGE 2 — FIREWALL (approval; default-deny inbound, allow only what's needed):
- Allow the CURRENT SSH port FIRST, then the web ports actually in use (80/443 if a web
  server is running), then enable the firewall. Use ufw on Debian/Ubuntu, firewalld on
  RHEL. Re-check your own SSH session is still alive immediately after enabling.

STAGE 3 — BRUTE-FORCE PROTECTION (approval): install + enable fail2ban with the sshd jail
(and a web jail if relevant). Confirm the service is active.

STAGE 4 — SSH HARDENING (approval, carefully):
- NOTHING here is "safe always". Every setting in this stage can close the door
  ServerAlly came through. Each one is allowed only when Stage 0 says it cannot.
- PermitRootLogin prohibit-password: ONLY when root is NOT the account ServerAlly uses,
  or ServerAlly authenticates by KEY and that key is really in root's authorized_keys
  (check the file, do not assume). If ServerAlly signs in as root with a PASSWORD, this
  setting removes its only way in — SKIP IT and say why. "No key is set up" is NOT a
  reason it is safe; it is exactly what makes it fatal.
- PasswordAuthentication no: ONLY when ServerAlly authenticates by key AND that key is
  confirmed present for the account it uses. Otherwise skip it and say so.
- Do not change the SSH Port. ServerAlly reconnects on the stored port and would not
  find the server. Offer it as something the owner does deliberately.
- Always safe: PermitEmptyPasswords no, X11Forwarding no.
- Validate the config (`sshd -t`) BEFORE reloading, and reload (not restart) so your
  current session survives.
- Reload keeping your session alive is NOT evidence the change was safe. It proves
  nothing about the NEXT connection, which is the one that matters.

STAGE 5 — AUTOMATIC SECURITY UPDATES (approval): enable unattended-upgrades
(Debian/Ubuntu) or dnf-automatic (RHEL) for SECURITY updates.

STAGE 6 — VERIFY + HAND OVER (status "done"): confirm the firewall is active with SSH still
allowed, fail2ban running, sshd config valid and reloaded, auto-updates enabled, and your
own SSH session still works. Summarize exactly what changed and what was deliberately
skipped (e.g. key-only mode) and why.
- Check the setting that governs the account YOU use. `PasswordAuthentication` governs
  normal users; `PermitRootLogin` governs root. Reading the first and reporting on the
  second is how a previous run reported success while it had just locked itself out.
  Read `sshd -T | grep -Ei 'permitrootlogin|passwordauthentication|^port'` and report
  what it actually says.

PITFALLS:
- The firewall + SSH changes are where lockouts happen — allow SSH before enabling the
  firewall, validate sshd config before reload, never restart-and-hope.
- Never reboot. Never disable password auth without a confirmed, working key.
- ServerAlly refuses a command that would cut its own way in, and tells you why. If you
  see that refusal, it is not a bug to work around — do not rewrite the command to slip
  past it. Report it and offer to add a key first.

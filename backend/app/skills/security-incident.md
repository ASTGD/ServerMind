---
slug: security-incident
title: Suspected Hack — First Response
triggers: hacked, i think i was hacked, server hacked, compromised, malware, suspicious process, crypto miner, someone logged in, unauthorized access, strange traffic, defaced
os: linux
priority: 10
---
GOAL: Preserve evidence, assess calmly, and contain — WITHOUT destroying the trail or
panicking the user. This is first response, not full forensics.

FIRST — SAY THIS TO THE USER: stay calm; do NOT reboot, do NOT delete anything yet,
and if this server holds customer data, consider taking a provider snapshot NOW
(evidence + safe restore point) before we change anything.

DIAGNOSTIC ORDER (strictly read-only):
1. Who is on the box: `w` and `last -a | head -20` — unknown IPs/users? Note them.
2. Suspicious processes: `ps aux --sort=-%cpu | head -10` — miners peg CPU with random
   names from /tmp, /dev/shm, or a deleted binary (`ls -l /proc/<pid>/exe`).
3. Network: `ss -ltnp` (unexpected listeners) and `ss -tnp | head -20` (odd outbound
   connections — miners talk to pools, bots to C2).
4. Persistence checks: `crontab -l; ls /etc/cron.*/ -la`, new keys in
   `~/.ssh/authorized_keys` (every user!), new users in `/etc/passwd` (uid 0 clones),
   `systemctl list-units --type=service --state=running | tail -20` for odd services.
5. Recent file changes in web space: `find <docroot> -mtime -3 -name "*.php" | head -20`
   — fresh .php files in uploads/ are classic webshells. READ them, don't delete yet.
6. Auth history: `grep -c "Failed password" /var/log/auth.log` (brute force volume) and
   `grep "Accepted" /var/log/auth.log | tail -10` (what got in, from where, which key).

CONTAIN (each step needs the user's explicit OK):
7. Kill the malicious process AND remove its persistence (cron/service/key) together —
   killing alone means it respawns.
8. Rotate credentials FROM A CLEAN DEVICE: server password/keys, panel, database, app
   admin — in that order. Assume anything stored on the box is burned.
9. Close the entry hole (the outdated plugin, the exposed port, the weak password) —
   otherwise they return tomorrow.

PITFALLS:
- No reboot, no `rm` of malware files until evidence is noted (paths, hashes:
  `sha256sum <file>`), and ideally a snapshot exists.
- A rootkit can lie to `ps`/`ls` — if root-level compromise is likely, the honest
  advice is: rebuild from a clean image + restore data from backups. Say it plainly.
- Don't run random "malware cleaner" scripts from the internet.
- This is first aid, not forensics — for legal/compliance cases, recommend a
  professional incident-response service before touching more.

VERIFY: CPU back to normal, no unknown listeners in `ss -ltnp`, the malicious cron/
service/key gone after re-checking step 4, and auth.log quiet after the credential
rotation and hole-closing.

ROLLBACK: n/a — this procedure only removes attacker artifacts with approval; the
snapshot from step 0 is the safety net.

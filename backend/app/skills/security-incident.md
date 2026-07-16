---
slug: security-incident
title: Suspected Hack — First Response
triggers: hacked, i think i was hacked, server hacked, compromised, malware, virus, viruses, infected, injected, malicious code, malicious file, webshell, suspicious process, crypto miner, someone logged in, unauthorized access, strange traffic, defaced
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
5. Web space — run these as TWO separate commands, and EXCLUDE the noise that buries the
   real signal (framework/cache .php regenerate constantly and vendored trees are huge,
   so they drown out webshells and truncate your findings):
   a. Recently modified: `find <docroot> -type f -name "*.php" -mtime -7
      -not -path "*/storage/framework/*" -not -path "*/cache/*" -not -path "*/vendor/*"
      -not -path "*/node_modules/*" | head -40` — fresh .php in uploads/ or wp-content/
      is a classic webshell.
   b. Signatures — as its OWN command so matches aren't buried in a big file list, and
      EXCLUDE dependency trees (they are third-party library code, full of legitimate
      base64/eval and huge — they produce hundreds of false hits):
      `grep -RislE 'eval\(|base64_decode|gzinflate|str_rot13|assert\(|shell_exec|passthru'
      <docroot> --include="*.php" -not -path "*/vendor/*" -not -path "*/node_modules/*"
      2>/dev/null | head -30` (add the site's known spam keywords when hunting a known
      campaign, e.g. gambling terms).
   READ each hit before judging — a match alone is NOT proof. A single token
   (`base64_decode`, `eval(`, `assert(`, `gzinflate`) is used all over legitimate code —
   WordPress core, image decoders, template engines, error-page renderers. Real malware
   needs a STRONG signal: a long obfuscated/packed blob AND/OR user input (`$_GET`/`$_POST`/
   `$_REQUEST`/`$_COOKIE`) flowing straight into execution. Confirm that before you treat a
   file as a shell. Never judge a file as malware because a sibling in the same folder
   matched. Don't delete yet.
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
- NEVER treat a `vendor/` or `node_modules/` file as malware because it matched a
  signature grep — it is installed third-party library code. Legit packages (image
  decoders using `base64_decode`, error-page renderers, a `.php` file that holds only
  SVG/HTML template markup) trip a naive grep constantly. If a dependency file is truly
  in doubt, verify it against the package manifest (`composer.lock` / `package-lock.json`)
  or restore the whole tree cleanly (`composer install` / `npm ci`) — do NOT hand-remove
  individual library files, and do NOT move a whole directory because one file in it hit.
- On WordPress/Laravel sites, `storage/framework/views` and `cache` .php files change
  constantly — always EXCLUDE them from "recently modified" scans, or they bury the real
  webshells and truncate the findings you can actually see. Run the signature grep as its
  own command so its hits aren't drowned out by a long file listing.
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

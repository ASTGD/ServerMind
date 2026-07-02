---
slug: disk-cleanup
title: Disk Full — Safe Cleanup
triggers: disk full, disk is full, no space left, out of disk, free up space, disk space, low on disk, clean up disk, 100% disk, storage full
os: linux
priority: 8
---
GOAL: Recover disk space safely — find what's big first, delete only what is provably
safe, and never touch user data without asking.

DIAGNOSTIC ORDER (read-only first):
1. Which filesystem is full: `df -h` — root? /var? a separate /home? Fix the right one.
2. Inodes too: `df -i` — "No space left" with free GB = inode exhaustion (millions of
   tiny files, usually sessions/cache/mail queue).
3. Find the big directories, top-down:
   `du -xh --max-depth=2 /var 2>/dev/null | sort -rh | head -12` (repeat for the full mount).
4. The usual suspects, in order of safe-to-free:
   - Journald logs: `journalctl --disk-usage` → `journalctl --vacuum-size=200M` (safe).
   - Rotated/old logs: `find /var/log -name "*.gz" -o -name "*.[0-9]"` → deletable.
   - Package cache: `apt clean` / `dnf clean all` (safe).
   - Old kernels (Ubuntu/Debian): `apt autoremove --purge` (keeps the running one).
   - Docker, if present: `docker system df` first — then `docker image prune -a` ONLY
     after telling the user unused images will be re-downloaded on next use.
   - Huge single files: `find / -xdev -size +500M -exec ls -lh {} \; 2>/dev/null` —
     NAME them to the user before touching anything.
5. A log currently growing fast? Identify the writer (`lsof +D /var/log | head`) and fix
   the cause (log level, logrotate), not just the symptom.

PITFALLS:
- NEVER delete: databases' data dirs (/var/lib/mysql, /var/lib/postgresql), anything in
  /home or a site's docroot, or files you can't identify — ask the user instead.
- Don't truncate an open log with rm (the space won't free while held); use
  `truncate -s 0 <file>` for a live log.
- Deleted-but-held space: `lsof +L1 | head` shows processes holding deleted files —
  restarting THAT service frees the space.
- If MySQL crashed from a full disk, free space FIRST, then start it.

VERIFY: `df -h` before → after; state how much was freed and from where.

ROLLBACK: none for deletions — which is exactly why everything above lists, names,
and confirms before removing. Anything uncertain: move to /root/quarantine/ instead
of deleting, and say so.

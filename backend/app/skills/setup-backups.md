---
slug: setup-backups
title: Set Up Automatic Backups
triggers: set up backups, setup backups, set up automatic backups, setup automatic backups, automatic backups, schedule backups, configure backups, back up this server automatically, set up a backup, nightly backups, automatic nightly backups
os: linux
priority: 7
mode: mission
budget: 30
recipe: true
summary: Schedule nightly backups of this server's files and databases — with a restore that's actually tested, not just hoped for.
icon: backup
variables: keep_days:optional:7
goal_template: Set up automatic nightly backups on this server for its websites and databases, keep {{keep_days}} days of history, and prove a restore actually works
---
GOAL: Put reliable, scheduled backups on THIS server — files + databases — with retention,
and (the part everyone skips) PROVE a restore actually works. A backup you've never
restored is a guess, not a backup.

STAGE 1 — WHAT TO BACK UP (read-only): find the web document roots and the databases in use
(MySQL/MariaDB, PostgreSQL). Choose a backup destination on a SEPARATE path from the data
(at least not inside a document root). Check free disk space — refuse to schedule backups
that would fill the disk, and say so.

STAGE 2 — BACKUP SCRIPT (approval to write it): create ONE backup script under /root or
/usr/local/bin that: dumps each database (mysqldump / pg_dump, password via env or a
defaults file — never on argv or in chat), tars the document roots, timestamps the output,
and PRUNES anything older than {{keep_days}} days. Make it idempotent and safe to re-run.

STAGE 3 — RUN IT ONCE (approval): run the script once now and confirm it produced
non-empty, timestamped archives in the destination.

STAGE 4 — VERIFY A RESTORE (the whole point): restore the just-made backup into a
DISPOSABLE location (a temp dir / a scratch database) — NEVER over the live site or DB —
and confirm the data is intact (the SQL imports cleanly, the files extract, row counts look
sane). Then clean up the scratch copy. If the restore fails, the backup is NOT trustworthy
— say so and fix it before finishing.

STAGE 5 — SCHEDULE IT (approval): add a cron entry (e.g. nightly ~02:00) to run the script.
Confirm the cron is installed and will run.

STAGE 6 — HAND OVER (status "done"): summarize what's backed up, where, how long it's kept,
the schedule, and — importantly — that the restore was TESTED and worked. Recommend also
copying backups OFF this server (another host / object storage), since a backup on the same
box won't survive the box dying; offer to help set that up next.

PITFALLS:
- A backup is only real once a restore is proven — never skip STAGE 4.
- Never restore over live data during the test. Keep DB passwords out of argv and chat.
- Don't fill the disk: check free space first and prune old backups.
- Never reboot.

---
slug: mysql-performance
title: MySQL/MariaDB Slow — Performance Triage
triggers: mysql slow, mysql is slow, database slow, database is slow, slow queries, slow query, queries are slow, mysql queries, mariadb slow, db performance, mysql high cpu, mysql memory, mysql keeps crashing, database keeps crashing, too many connections
os: linux
priority: 6
---
GOAL: Find why the database is slow or unstable — evidence from the DB itself, then one
targeted change at a time.

DIAGNOSTIC ORDER (read-only first):
1. Is it even the DB? `systemctl status mysql mariadb` + uptime of the process — a DB
   restarting in a loop looks "slow" from the app. `journalctl -u mysql -n 30 --no-pager`.
2. Crashed recently? Check for OOM kills: `dmesg -T | grep -iE "killed process.*(mysqld|mariadbd)"`
   — the #1 cause on small VPSes (buffer pool too big for the RAM).
3. Live picture: `mysqladmin status processlist` or SQL `SHOW FULL PROCESSLIST;` —
   look for many queries in "Sending data"/"Copying to tmp table", or LOCK waits.
4. Connections: `SHOW STATUS LIKE 'Threads_connected'; SHOW VARIABLES LIKE 'max_connections';`
   — "Too many connections" = app leaking connections or pool too small, rarely a DB bug.
5. Slow queries: `SHOW VARIABLES LIKE 'slow_query_log%';` — if off, enable it
   (long_query_time=1) for a while, then read the log and name the top offending query.
6. Memory sizing sanity: buffer pool vs server RAM —
   `SHOW VARIABLES LIKE 'innodb_buffer_pool_size';` vs `free -h`. Rule of thumb on a
   shared web+DB box: pool ≈ 25–40% of RAM; DB-only box: 60–70%.
7. Disk: `df -h` (full disk = weird errors) and I/O wait (`vmstat 1 3`, 'wa' column).

PITFALLS:
- ONE config change at a time, each with a .bak of the config file and a measured
  before/after — never paste a "tuning template" wholesale.
- Never kill a long-running query blindly — check what it is first; killing a big
  UPDATE mid-way causes a long rollback that's WORSE.
- Don't disable the binlog/fsync settings for speed on production data.
- A missing index is fixed with EXPLAIN + CREATE INDEX (online), not more RAM.

VERIFY: re-run the slow operation or watch `SHOW GLOBAL STATUS LIKE 'Slow_queries';`
stop climbing; confirm no OOM kills after the change; app response time improved.

ROLLBACK: restore the config .bak and restart the service; DROP any index you added if
it didn't help. State each change and its undo command explicitly.

---
slug: server-slow-triage
title: Server Slow — Systematic Triage
triggers: server is slow, server slow, very slow, running slow, high cpu, cpu is high, high load, load average, ram full, memory full, out of memory, oom, laggy, everything is slow, high memory usage
os: linux
priority: 8
---
GOAL: Find WHICH resource is the bottleneck (CPU / RAM / disk I/O / network) and WHAT
process causes it — measure first, never restart things blindly.

DIAGNOSTIC ORDER (all read-only):
1. The 10-second picture: `uptime` (load vs core count — load 4 on 1 core is drowning,
   on 8 cores is idle; get cores with `nproc`), then `free -h`, then `df -h`.
2. Top offenders: `ps aux --sort=-%cpu | head -8` and `ps aux --sort=-%mem | head -8`.
   Name the actual processes to the user in plain words (e.g. "MySQL is using 80% of RAM").
3. CPU pegged but load low → a busy app loop. Load high but CPU idle → processes stuck
   waiting on DISK: check `iostat -xz 1 3` (util% near 100 = disk-bound) or, without
   sysstat, `vmstat 1 5` (high 'wa' column = I/O wait).
4. RAM: distinguish "used" from "cached" — Linux uses free RAM as cache (healthy).
   Real pressure = low 'available' in `free -h` + swap in use (`vmstat 1 3`, si/so > 0).
5. OOM check: `dmesg -T | grep -i "out of memory" | tail -5` — if the kernel has been
   killing processes, that's the smoking gun.
6. Network flood: `ss -s` for connection counts; a huge TIME-WAIT/ESTAB count on a web
   server suggests traffic spike or abuse — check the access log rate:
   `tail -1000 /var/log/nginx/access.log | awk '{print $1}' | sort | uniq -c | sort -rn | head -5`.
7. Only after identifying the culprit, propose ONE targeted fix (restart the runaway
   service, tune the config, add swap) — not a shotgun of restarts.

PITFALLS:
- Never reboot as a "fix" — the evidence disappears and the cause returns.
- Don't kill -9 databases; use their service stop (data safety).
- A one-time spike (backup job, cron, update) is normal — check `ps` timestamps and
  crontab before treating it as a problem.
- Adding swap on a disk that's already I/O-bound makes things WORSE.

VERIFY: after the fix, re-run `uptime`, `free -h`, and the ps top-lists; numbers should
visibly improve. Tell the user the before → after numbers.

ROLLBACK: any config tuned gets a .bak copy first; a restarted service can be watched
with `journalctl -u <svc> -f` for a minute to confirm it stays healthy.

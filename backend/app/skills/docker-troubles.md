---
slug: docker-troubles
title: Docker Containers — Crash/Restart Triage
triggers: container keeps restarting, container crashed, docker not working, container exited, docker error, container won't start, docker restart loop, container down, docker compose not working
os: linux
priority: 5
---
GOAL: Find why a container exits/restarts using Docker's own evidence (status, logs,
exit codes) — never just re-run it harder.

DIAGNOSTIC ORDER (read-only first):
1. The fleet view: `docker ps -a` — note STATUS ("Restarting (1) 10s ago", "Exited (137)").
2. The container's story: `docker logs --tail 50 <name>` — the crash reason is almost
   always in the last lines.
3. Exit codes decode: 137 = killed (OOM or docker stop), 139 = segfault, 1/2 = app
   error (read the logs), 126/127 = bad command/entrypoint.
4. OOM specifically: `docker inspect <name> --format '{{.State.OOMKilled}}'` — true
   means the container hit its memory limit (or the host ran out): check limits in
   compose (`mem_limit`) and host `free -h`.
5. Config/env problems: `docker inspect <name>` for env, mounts, ports. A missing
   mounted file or a busy host port ("address already in use" — find it with
   `ss -ltnp | grep :<port>`) stops a container at boot.
6. Compose projects: run compose commands from the project directory;
   `docker compose ps` + `docker compose logs --tail 50 <svc>`.
7. Disk: `docker system df` + `df -h` — a full disk breaks pulls, builds, and logs.
8. Daemon-level: `journalctl -u docker -n 30 --no-pager` when ALL containers misbehave.

PITFALLS:
- `docker system prune -a` deletes images/volumes users may need — list what it would
  remove and confirm before running; NEVER prune volumes without explicit approval
  (volumes = data).
- Don't `docker rm -f` a database container as a fix — its volume mapping matters more
  than the container; verify the volume before touching it.
- restart:always hides crashes — after fixing, watch `docker ps` for a stable minute.
- Changing the image tag ("latest") can silently upgrade the app — pin versions when
  redeploying.

VERIFY: `docker ps` shows the container Up (not "Restarting") for at least a minute,
its `docker logs --tail 10` look healthy, and the service answers on its port
(`curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:<port>/`).

ROLLBACK: compose changes keep a .bak of the yml; a container recreated from the same
image+volume returns to the previous state with `docker compose up -d <svc>`.

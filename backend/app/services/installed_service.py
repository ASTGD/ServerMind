"""What's installed on a server — from our own install history (records) and from a live
read-only scan of the box. Secrets in stored install inputs are always masked here; we
never re-display a credential a user typed during an install."""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook import Playbook, PlaybookRun
from app.models.server import Server
from app.services import connection_manager

# A variable is treated as a secret (and masked) when its NAME looks credential-ish.
_SECRET_RE = re.compile(r"(PASS|PASSWORD|PWD|SECRET|TOKEN|KEY|CRED)", re.IGNORECASE)
_MASK = "••••••"


def _is_secret(name: str) -> bool:
    return bool(_SECRET_RE.search(name or ""))


def mask_variables(variables: dict | None) -> dict:
    """Install inputs with secret-named values masked — never expose stored credentials."""
    return {k: (_MASK if _is_secret(k) else str(v)) for k, v in (variables or {}).items()}


def _fill(template: str | None, host: str | None, variables: dict | None) -> str | None:
    """Substitute {{HOST}} and {{VAR}} in one access-card field. If the field references a
    SECRET variable, return None — we never render a stored password/secret."""
    if not template:
        return None
    out = template.replace("{{HOST}}", host or "")
    for key, value in (variables or {}).items():
        placeholder = "{{" + key + "}}"
        if placeholder in out:
            if _is_secret(key):
                return None  # field would expose a secret — drop it
            out = out.replace(placeholder, str(value))
    return out or None


def resolve_access_card(
    access_info: dict | None, host: str | None, variables: dict | None
) -> dict | None:
    """Resolve a playbook's ``access_info`` template into a concrete card (secrets masked)."""
    if not access_info:
        return None
    card = {
        "name": access_info.get("name"),
        "url": _fill(access_info.get("url"), host, variables),
        "username": _fill(access_info.get("username"), host, variables),
        "password": _fill(access_info.get("password"), host, variables),  # None if secret
        "note": access_info.get("note"),
    }
    if not (card["url"] or card["username"] or card["note"]):
        return None
    return card


async def installed_from_records(db: AsyncSession, server: Server) -> list[dict]:
    """What ServerMind has installed on this server, from our own run history: the latest
    SUCCESSFUL run per (playbook, access URL), newest first, each with a resolved card."""
    rows = (
        await db.execute(
            select(PlaybookRun, Playbook)
            .join(Playbook, Playbook.id == PlaybookRun.playbook_id)
            .where(PlaybookRun.server_id == server.id, PlaybookRun.status == "success")
            .order_by(
                PlaybookRun.completed_at.desc().nullslast(),
                PlaybookRun.started_at.desc(),
            )
        )
    ).all()

    seen: set[tuple] = set()
    items: list[dict] = []
    for run, pb in rows:
        card = resolve_access_card(pb.access_info, server.host, run.variables_used)
        key = (pb.slug, (card or {}).get("url") or "")
        if key in seen:
            continue
        seen.add(key)
        when = run.completed_at or run.started_at
        items.append(
            {
                "run_id": str(run.id),
                "playbook_slug": pb.slug,
                "playbook_title": pb.title,
                "category": pb.category,
                "installed_at": when.isoformat() if when else None,
                "access": card,
                "variables": mask_variables(run.variables_used),
            }
        )
    return items


# Read-only probe: detect common web stacks, databases, runtimes, containers, panels and
# listening ports. Emits ``key=value`` lines parsed by ``parse_scan``. POSIX sh only.
_DETECT_SCRIPT = r'''
echo "os=$( . /etc/os-release 2>/dev/null; printf '%s' "${PRETTY_NAME:-Linux}" )"
command -v nginx   >/dev/null 2>&1 && echo "web=nginx $(nginx -v 2>&1 | sed 's#.*/##')"
command -v apache2 >/dev/null 2>&1 && echo "web=apache $(apache2 -v 2>/dev/null | sed -n 's#.*Apache/##p' | awk '{print $1}')"
command -v httpd   >/dev/null 2>&1 && echo "web=apache $(httpd -v 2>/dev/null | sed -n 's#.*Apache/##p' | awk '{print $1}')"
command -v mysql   >/dev/null 2>&1 && echo "db=mysql/mariadb $(mysql --version 2>/dev/null | sed -n 's/.*Distrib \([0-9.]*\).*/\1/p')"
command -v psql    >/dev/null 2>&1 && echo "db=postgres $(psql --version 2>/dev/null | awk '{print $3}')"
command -v php     >/dev/null 2>&1 && echo "runtime=php $(php -r 'echo PHP_VERSION;' 2>/dev/null)"
command -v node    >/dev/null 2>&1 && echo "runtime=node $(node -v 2>/dev/null | tr -d v)"
command -v python3 >/dev/null 2>&1 && echo "runtime=python $(python3 -V 2>&1 | awk '{print $2}')"
command -v docker  >/dev/null 2>&1 && echo "runtime=docker $(docker --version 2>/dev/null | sed -n 's/Docker version \([0-9.]*\).*/\1/p')"
command -v docker  >/dev/null 2>&1 && docker ps --format '{{.Names}} ({{.Image}})' 2>/dev/null | while IFS= read -r c; do [ -n "$c" ] && echo "container=$c"; done
for e in /usr/local/cpanel:cPanel /usr/local/CyberCP:CyberPanel /usr/local/hestia:HestiaCP /usr/local/directadmin:DirectAdmin /opt/psa:Plesk /www/server/panel:aaPanel /home/clp:CloudPanel /etc/webmin:Webmin; do d="${e%%:*}"; n="${e##*:}"; [ -e "$d" ] && echo "panel=$n"; done
ss -tln 2>/dev/null | awk 'NR>1{n=split($4,a,":"); print a[n]}' | sort -un | while read -r p; do [ -n "$p" ] && echo "port=$p"; done
'''


def parse_scan(output: str) -> dict:
    """Turn the detect script's ``key=value`` lines into a structured inventory."""
    res: dict = {
        "os": None,
        "web_servers": [],
        "databases": [],
        "runtimes": [],
        "containers": [],
        "panels": [],
        "ports": [],
    }
    bucket = {
        "web": "web_servers",
        "db": "databases",
        "runtime": "runtimes",
        "container": "containers",
        "panel": "panels",
        "port": "ports",
    }
    for line in (output or "").splitlines():
        line = line.strip()
        key, sep, val = line.partition("=")
        val = val.strip()
        if not sep or not val:
            continue
        if key == "os":
            res["os"] = val
        elif key in bucket:
            res[bucket[key]].append(val)
    res["ports"] = sorted(
        {p for p in res["ports"]}, key=lambda x: int(x) if x.isdigit() else 1 << 30
    )
    return res


async def scan_server(server: Server) -> dict:
    """Live read-only inventory of a Linux (SSH) server."""
    if server.connection_type != "ssh":
        return {"supported": False, **parse_scan("")}
    out, _, _ = await connection_manager.execute(server, _DETECT_SCRIPT)
    return {"supported": True, **parse_scan(out)}

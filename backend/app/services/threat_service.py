"""Threat scan — read-only indicators-of-compromise (IOC) detection.

Distinct from ``security_service`` (which scores hardening posture): this looks for
signs a server is ACTIVELY compromised — webshells, tampered WordPress core, miner
processes, persistence (rogue cron/systemd), backdoor accounts, rootkit hooks.

Design (matches Live Look / security audit discipline):
- **Fixed, read-only probe bundle** — the commands are authored here, never
  AI-chosen, and only observe (grep/find/ps/stat). Nothing is changed or removed.
- **One SSH round trip** — all sections run in a single sentinel-delimited script.
- **Low false-positive by construction** — internet-facing servers always have
  failed logins and open ports; those are NOT flagged. We key on real IOCs, and
  remediation is always the user's call (fix commands are display-only).

Verdict: ``clean`` | ``suspicious`` (medium) | ``at_risk`` (high) | ``compromised``
(critical). Best-effort: connection failure → a failed result, never raises.
"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.models.server import Server
from app.services import connection_manager

logger = logging.getLogger(__name__)

_SECTION_RE = re.compile(r"^__SMTHREAT__([a-zA-Z0-9_]+)__$", re.MULTILINE)


def _marker(section_id: str) -> str:
    return f"__SMTHREAT__{section_id}__"


@dataclass
class Section:
    id: str
    command: str
    #: How affordable this probe is, which decides how often it may run.
    #:
    #: Measured on a 20-site server holding 11,800 PHP files: the six local probes cost
    #: **137 ms warm, 697 ms cold in total** — cheaper than the metrics round trip we
    #: already make every 5 minutes. The original 12-hour interval came from an
    #: assumption ("heavier than metrics") that measurement disproved, and it meant a
    #: webshell could sit undetected for half a day.
    #:
    #: `slow` is for a probe whose cost is NOT bounded by local disk: `wpcore` shells out
    #: to wp-cli per site, which talks to api.wordpress.org (up to 12 sites x 25 s). That
    #: one stays on the long cycle.
    #:
    #: Defaults to "fast" so a new probe is caught by the affordability test below rather
    #: than quietly making the frequent sweep expensive.
    tier: str = "fast"


@dataclass
class Check:
    id: str
    title: str
    section: str
    evaluate: Callable[[str], dict]


def _finding(check: Check, *, severity: str, detail: str | None = None,
             recommendation: str | None = None, evidence: str | None = None) -> dict:
    return {
        "id": check.id, "title": check.title, "severity": severity,
        "detail": detail, "recommendation": recommendation, "evidence": evidence,
    }


def _lines(raw: str, limit: int = 15) -> list[str]:
    out = [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]
    return out[:limit]


# ── Read-only probe sections ──────────────────────────────────────────────────
# Each section is wrapped in a subshell + `|| true` by the builder, so a missing
# path never aborts the scan.
#
# SCOPE (widened 2026-07-15): web content lives in far more places than
# `*/public_html`. CyberPanel puts each child domain at /home/<account>/<domain>/
# (live: /home/desktopit.net/news.rmp.gov.bd), cPanel adds addon-domain dirs, and
# plain nginx/apache use /var/www. Scanning only */public_html silently MISSED whole
# infected sites, so we now scan the account homes wholesale and prune the noise.
_SCAN_ROOTS = r'/home /var/www /usr/local/lsws/*/html'

# Package-manager-owned trees: huge (they dominate the walk) and third-party library
# code we would never clean by hand anyway — a tampered dependency is fixed by
# restoring the tree (composer install / npm ci), not by quarantining a file. Pruning
# them keeps a 90-site box fast and keeps us away from the vendor false positive that
# took a live site offline (BUG-002). NOTE: cache/storage are deliberately NOT pruned —
# webshells really do hide in bootstrap/cache and storage/framework/views, and the
# signatures below are tight enough not to false-positive on cached templates.
_PRUNE_DIRS = ("vendor", "node_modules", ".git", ".svn")
_GREP_PRUNE = " ".join(f"--exclude-dir={d}" for d in _PRUNE_DIRS)
# find(1) equivalent: -name a -o -name b … ) -prune -o
_FIND_PRUNE = r"\( " + " -o ".join(f"-name {d}" for d in _PRUNE_DIRS) + r" \) -prune -o"

# Every SILENT probe must finish well inside ssh_service's 60s channel-read timeout,
# or the whole scan dies with a "could not connect". These caps bound the widened walk.
_T_GREP = 45
_T_FIND = 30
_T_LOCATE = 20
_WP_SITES_MAX = 12   # per-site wp-cli check is slow; cap it and say so when we do
_T_WPSITE = 25

LINUX_SECTIONS: list[Section] = [
    Section("meta", "id -u; hostname; date -u +%Y-%m-%dT%H:%M:%SZ"),
    # High-confidence webshell signatures ONLY — user input flowing straight into
    # code execution / obfuscated eval. Deliberately NOT broad patterns like bare
    # preg_replace/assert (legit WP core + minifiers use those); modified core is
    # caught separately by the wp-cli checksum check.
    Section("webshell", (
        f"_t {_T_GREP} grep -rlEI --include=*.php {_GREP_PRUNE} "
        r"'eval[[:space:]]*\([[:space:]]*(base64_decode|gzinflate|gzuncompress|str_rot13|\$_)|"
        r"(system|passthru|shell_exec|proc_open|popen)[[:space:]]*\([[:space:]]*\$_(GET|POST|REQUEST|COOKIE)|"
        r"assert[[:space:]]*\([[:space:]]*\$_(GET|POST|REQUEST|COOKIE)' "
        + _SCAN_ROOTS + r" 2>/dev/null | head -25"
    )),
    # A .php inside wp-content/uploads is almost always a dropped shell. Matched at ANY
    # depth under the account homes, so a child-domain site is covered too.
    Section("uploads_php", (
        f"_t {_T_FIND} find {_SCAN_ROOTS} {_FIND_PRUNE} "
        r"-type f -name '*.php' -path '*/wp-content/uploads/*' -print 2>/dev/null | head -25"
    )),
    # Processes whose binary lives in a world-writable dir, or a known miner. A bare
    # "(deleted)" exe is NOT flagged — that's the benign case of a running service
    # whose binary was replaced by a package update.
    Section("proc", (
        r"ls -l /proc/*/exe 2>/dev/null | grep -aE '\-> (/tmp/|/dev/shm/|/var/tmp/)' | head -15; "
        r"ps -eo comm= 2>/dev/null | grep -iE '^(xmrig|kdevtmpfsi|kinsing|minerd|cnrig|nanominer)$' | head -10"
    )),
    # Persistence: cron/systemd that pulls & runs code from the internet or /tmp.
    Section("persistence", (
        r"grep -rIElsi 'curl |wget |base64 -d| /tmp/| /dev/shm' /etc/cron.d /etc/cron.hourly /etc/cron.daily /var/spool/cron 2>/dev/null | head -15; "
        r"grep -rIEls 'ExecStart=.*(curl|wget|/tmp/|/dev/shm|base64)' /etc/systemd/system /run/systemd/system 2>/dev/null | head -15"
    )),
    # Backdoor accounts + loader hook. A non-root uid-0 user or a non-empty
    # ld.so.preload is a strong compromise signal. (awk uses single quotes so the
    # embedded double quotes need no escaping.)
    Section("accounts", (
        "awk -F: '$3==0 && $1!=\"root\"{print \"uid0:\"$1}' /etc/passwd; "
        "test -s /etc/ld.so.preload && echo \"ld_preload:$(cat /etc/ld.so.preload)\""
    )),
    # SUID binaries in user-writable locations — privilege-escalation implants.
    Section("suid", r"find /tmp /var/tmp /dev/shm /home -xdev -perm -4000 -type f 2>/dev/null | head -15"),
    # WordPress core integrity via wp-cli checksums. Modified/extra core files =
    # tamper. Placed raw inside a subshell, so normal double-quoting is correct
    # (no backslash escaping). Per-site timeout keeps a slow site from hanging.
    Section("wpcore", (
        'if ! command -v wp >/dev/null 2>&1; then echo NO_WPCLI; else '
        # Locate every WordPress install by its wp-load.php, at any depth under the
        # account homes — a child-domain site never had a */public_html path to match.
        f'sites=$(_t {_T_LOCATE} find {_SCAN_ROOTS} {_FIND_PRUNE} '
        f'-type f -name wp-load.php -print 2>/dev/null | head -{_WP_SITES_MAX + 1}); '
        'n=$(echo "$sites" | grep -c .); '
        # The per-site wp-cli check is slow, so cap it — and SAY SO rather than
        # silently under-reporting coverage.
        f'if [ "$n" -gt {_WP_SITES_MAX} ]; then echo "CAPPED:{_WP_SITES_MAX}"; fi; '
        f'for f in $(echo "$sites" | head -{_WP_SITES_MAX}); do d=$(dirname "$f"); '
        f'o=$(_t {_T_WPSITE} wp core verify-checksums --path="$d" --allow-root 2>&1); '
        # Only ADDED ("should not exist") or MODIFIED ("verify against checksum")
        # core files signal tampering. "doesn\'t exist" (missing) = benign version
        # drift and is ignored.
        't=$(echo "$o" | grep -iE "should not exist|verify against checksum" | head -3 | tr "\\n" " "); '
        'if [ -n "$t" ]; then echo "TAMPER:$d:$t"; else echo "OK:$d"; fi; '
        'done; fi'
    ), tier="slow"),
]

#: The probes cheap enough to run every few minutes — everything except `wpcore`.
FAST_SECTIONS: list[Section] = [s for s in LINUX_SECTIONS if s.tier == "fast"]


# ── Checks (evaluate raw section output → finding) ────────────────────────────

def _c_webshell(raw: str) -> dict:
    hits = _lines(raw)
    if hits:
        return _finding(_CHECKS_BY["webshell"], severity="critical",
                        detail=f"{len(hits)} PHP file(s) contain webshell/obfuscation signatures.",
                        recommendation="Do NOT edit these in place. Isolate the site, preserve a copy for evidence, then restore the site from a known-clean backup and rotate all passwords.",
                        evidence="\n".join(hits))
    return _finding(_CHECKS_BY["webshell"], severity="pass", detail="No webshell signatures in web roots.")


def _c_uploads(raw: str) -> dict:
    hits = _lines(raw)
    if hits:
        return _finding(_CHECKS_BY["uploads_php"], severity="critical",
                        detail=f"{len(hits)} PHP file(s) found under wp-content/uploads — this directory should never contain PHP.",
                        recommendation="These are almost always uploaded backdoors. Preserve for evidence, remove them, and find how they were uploaded (vulnerable plugin?).",
                        evidence="\n".join(hits))
    return _finding(_CHECKS_BY["uploads_php"], severity="pass", detail="No PHP files in uploads directories.")


def _c_proc(raw: str) -> dict:
    hits = _lines(raw)
    if hits:
        return _finding(_CHECKS_BY["proc"], severity="critical",
                        detail="Process(es) running from a temporary directory, a deleted binary, or a known crypto-miner.",
                        recommendation="This is a strong sign of active malware. Do not just kill it — capture the process details first, then investigate persistence and rebuild if confirmed.",
                        evidence="\n".join(hits))
    return _finding(_CHECKS_BY["proc"], severity="pass", detail="No suspicious processes.")


def _c_persistence(raw: str) -> dict:
    hits = _lines(raw)
    if hits:
        return _finding(_CHECKS_BY["persistence"], severity="high",
                        detail="Cron job or systemd unit that downloads and runs code from the internet or a temp directory.",
                        recommendation="Review each entry — attackers use these to survive reboots. Confirm it's legitimate before removing; capture it first if not.",
                        evidence="\n".join(hits))
    return _finding(_CHECKS_BY["persistence"], severity="pass", detail="No suspicious cron/systemd persistence.")


def _c_accounts(raw: str) -> dict:
    hits = _lines(raw)
    if hits:
        return _finding(_CHECKS_BY["accounts"], severity="critical",
                        detail="A non-root account with root privileges, or a code hook in /etc/ld.so.preload.",
                        recommendation="These give an attacker full control. Verify each — if unexpected, treat the server as compromised and rebuild from clean.",
                        evidence="\n".join(hits))
    return _finding(_CHECKS_BY["accounts"], severity="pass", detail="No backdoor root accounts or preload hooks.")


def _c_suid(raw: str) -> dict:
    hits = _lines(raw)
    if hits:
        return _finding(_CHECKS_BY["suid"], severity="high",
                        detail=f"{len(hits)} SUID-root binary(ies) in a user-writable location (/tmp, /home, …).",
                        recommendation="SUID binaries here are a common privilege-escalation implant. Review each; legitimate ones are rare.",
                        evidence="\n".join(hits))
    return _finding(_CHECKS_BY["suid"], severity="pass", detail="No SUID binaries in user-writable locations.")


def _c_wpcore(raw: str) -> dict:
    if "NO_WPCLI" in raw or not raw.strip():
        return _finding(_CHECKS_BY["wpcore"], severity="info",
                        detail="WordPress core integrity not checked (wp-cli not available or no WordPress found).")
    # Checksum mismatches CAN mean an injected backdoor — but they're also common
    # from version drift on new/beta WordPress (wp-cli's checksum manifest lags the
    # release). So this is a LOW "worth a look" signal, NOT an alarm: it does not
    # raise the compromise verdict on its own. The high-confidence compromise
    # detection is the webshell / uploads / process / persistence / account checks.
    lines = _lines(raw, 25)
    # Coverage was capped (more WP sites than we check per scan) — never let that read
    # as "everything is fine"; say it in the detail.
    capped = next((ln for ln in lines if ln.startswith("CAPPED:")), None)
    cap_note = (f" Only the first {capped.split(':', 1)[1]} WordPress sites on this server were"
                " checked (per-scan limit) — the rest were not verified.") if capped else ""
    tampered = [ln for ln in lines if ln.startswith("TAMPER:")]
    if tampered:
        return _finding(_CHECKS_BY["wpcore"], severity="low",
                        detail=f"{len(tampered)} WordPress site(s) have core files that differ from the official checksums. Often this is version drift or a custom build — but occasionally it's an injected file, so it's worth a manual look.{cap_note}",
                        recommendation="Compare against a clean copy of the same WordPress version. If you didn't customise core, re-download it (wp core download --force) after backing up.",
                        evidence="\n".join(t[:400] for t in tampered))
    return _finding(_CHECKS_BY["wpcore"], severity="pass",
                    detail=f"WordPress core files match official checksums (no added/modified files).{cap_note}")


LINUX_CHECKS: list[Check] = [
    Check("webshell", "Webshell signatures in web files", "webshell", _c_webshell),
    Check("uploads_php", "PHP files in uploads directory", "uploads_php", _c_uploads),
    Check("proc", "Malicious / miner processes", "proc", _c_proc),
    Check("persistence", "Suspicious cron / systemd persistence", "persistence", _c_persistence),
    Check("accounts", "Backdoor accounts / loader hooks", "accounts", _c_accounts),
    Check("suid", "SUID binaries in writable paths", "suid", _c_suid),
    Check("wpcore", "WordPress core integrity", "wpcore", _c_wpcore),
]

_CHECKS_BY: dict[str, Check] = {c.id: c for c in LINUX_CHECKS}


# ── Runner ────────────────────────────────────────────────────────────────────

# `timeout` (coreutils) bounds every silent probe so the widened walk can't blow past
# ssh_service's 60s channel-read timeout. If a box somehow lacks it we must NOT return
# nothing — an empty webshell section reads as "clean", i.e. a silent false all-clear on
# a critical check. _t therefore falls back to running the probe UNBOUNDED (fail open).
_TIMEOUT_HELPER = (
    '_t() { if command -v timeout >/dev/null 2>&1; then timeout "$@"; '
    'else shift; "$@"; fi; }'
)


def _build_script(sections: list[Section]) -> str:
    parts = ["export LC_ALL=C", _TIMEOUT_HELPER]
    for s in sections:
        parts.append(f"printf '\\n{_marker(s.id)}\\n'")
        parts.append(f"( {s.command} ) 2>&1 || true")
    return "\n".join(parts)


def _parse_sections(output: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(output))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(output)
        sections[m.group(1)] = output[start:end].strip()
    return sections


_VERDICT_BY_WORST = {"critical": "compromised", "high": "at_risk", "medium": "suspicious"}


def _summarize(findings: list[dict]) -> tuple[str, dict[str, int]]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0, "pass": 0}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    for sev in ("critical", "high", "medium"):
        if counts.get(sev):
            return _VERDICT_BY_WORST[sev], counts
    return "clean", counts


def _failed(started: float, error: str) -> dict:
    return {"verdict": "unknown", "status": "failed", "error": error, "findings": [],
            "counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0, "pass": 0},
            "duration_ms": int((time.monotonic() - started) * 1000)}


async def run_scan(server: Server, *, fast_only: bool = False) -> dict:
    """Run the read-only threat scan. Returns
    ``{verdict, status, error, counts, findings, duration_ms}``. Never raises.

    ``fast_only`` runs just the locally-bounded probes (see ``Section.tier``) so the sweep
    can repeat every few minutes. A skipped probe is **left out of the findings entirely**
    rather than evaluated against empty output — evaluating `wpcore` on nothing reports
    "not checked (wp-cli not available or no WordPress found)", which blames the customer's
    server for a choice we made. Absent is honest; a wrong reason is not.
    """
    started = time.monotonic()
    if (server.shell or "").lower() == "powershell" or (server.os_type or "").lower() == "windows":
        return _failed(started, "Threat scan currently supports Linux/SSH servers only.")
    if server.connection_type not in ("ssh",):
        return _failed(started, "Threat scan needs an SSH connection to the server.")

    sections = FAST_SECTIONS if fast_only else LINUX_SECTIONS
    included = {s.id for s in sections}
    script = _build_script(sections)
    try:
        stdout, _stderr, _exit = await connection_manager.execute(server, script)
    except Exception as exc:  # noqa: BLE001 — transport errors are reported, not raised
        logger.warning("Threat scan failed for server %s: %s", server.id, exc)
        return _failed(started, f"Could not connect to the server: {exc}")

    raw = _parse_sections(stdout or "")
    findings: list[dict] = []
    for check in LINUX_CHECKS:
        if check.section not in included:
            continue
        try:
            findings.append(check.evaluate(raw.get(check.section, "")))
        except Exception as exc:  # noqa: BLE001 — one bad evaluator must not kill the scan
            logger.exception("Threat evaluator '%s' raised", check.id)
            findings.append(_finding(check, severity="info", detail=f"Check failed: {exc}"))

    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "pass": 5}
    findings.sort(key=lambda f: sev_order.get(f["severity"], 9))
    verdict, counts = _summarize(findings)
    return {"verdict": verdict, "status": "completed", "error": None, "counts": counts,
            "findings": findings, "scope": "fast" if fast_only else "full",
            "duration_ms": int((time.monotonic() - started) * 1000)}

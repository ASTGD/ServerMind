"""Safety service — validates AI-generated commands against blocklists."""
from __future__ import annotations

import re
from dataclasses import dataclass

# ── Blocklists ────────────────────────────────────────────────────────────────

# BLOCK = catastrophic, irreversible destruction of the system/disk. Never legitimate,
# so we refuse outright (no approval offered). Written to catch practical VARIANTS, not
# just the one canonical form — the red-team proved literal-only patterns are trivially
# dodged (rm -rf /{bin,..}, dd of=/dev/nvme0, find / -delete, chmod 777 -R /, spaced
# fork bomb all slipped through before). Recursive-delete of a NON-system path is a
# CONFIRM (below), not a block, so legitimate cleanup still works with approval.
_SYS_DIRS = r"(bin|boot|dev|etc|lib|lib32|lib64|proc|root|run|sbin|srv|sys|usr|var)"
_BLOCK_DEV = r"(sd[a-z]|nvme\d|vd[a-z]|xvd[a-z]|hd[a-z]|mmcblk\d|dm-\d|loop\d|disk\d)"
LINUX_BLOCKED = [
    # rm -rf targeting root, /*, --no-preserve-root, or a system directory (incl. brace
    # expansion like /{bin,etc,...}). Flag order (-rf / -fr / -r -f) and extra flags allowed.
    r"\brm\b(?=[^\n]*\s-[a-zA-Z]*r)(?=[^\n]*\s-[a-zA-Z]*f|[^\n]*--force)[^\n]*\s--no-preserve-root",
    r"\brm\b(?=[^\n]*\s-[a-zA-Z]*r)[^\n]*\s/\s*(;|$|&&|\|\|)",         # rm -r ... /
    r"\brm\b(?=[^\n]*\s-[a-zA-Z]*r)[^\n]*\s/\*",                        # rm -r ... /*
    r"\brm\b(?=[^\n]*\s-[a-zA-Z]*r)[^\n]*\s/\{[^}]*" + _SYS_DIRS,       # rm -r ... /{bin,..}
    # rm -r ... /<systemdir>  ITSELF (/var, /var/, /var/*, /var*) — but NOT a deeper
    # path like /var/www/... (that clears a subdir → CONFIRM, not a catastrophic block).
    r"\brm\b(?=[^\n]*\s-[a-zA-Z]*r)[^\n]*\s/" + _SYS_DIRS + r"/?\*?(?=\s|;|\||&|$)",
    # find deleting/exec-rm starting at root
    r"\bfind\s+/\s[^\n]*-delete\b", r"\bfind\s+/\s[^\n]*-exec\s+rm\b",
    # filesystem creation / raw block-device writes (any device, any write path)
    r"\bmkfs\b", r"\bmke2fs\b", r"\bwipefs\b",
    r"\bdd\b[^|\n]*\bof=/dev/" + _BLOCK_DEV,
    r">\s*/dev/" + _BLOCK_DEV,
    r"\btee\b[^|\n]*\s/dev/" + _BLOCK_DEV,
    # fork bomb — whitespace-tolerant (': () { : | : & } ; :' slipped the old regex)
    r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}",
    # recursive world-writable chmod / recursive chown of the whole system root
    r"\bchmod\b[^\n]*\s-[a-zA-Z]*R[a-zA-Z]*[^\n]*\s[0-7]*7[0-7]*\s+/\s*(;|$)",
    r"\bchmod\b[^\n]*\s[0-7]*7[0-7]*\s+-[a-zA-Z]*R[a-zA-Z]*\s+/\s*(;|$)",
    r"\bchown\b[^\n]*\s-[a-zA-Z]*R[a-zA-Z]*[^\n]*\s/\s*(;|$)",
    r"\bmv\s+/\s+\S",                                                    # mv / <dest>
]

WINDOWS_BLOCKED = [
    r"Format-Volume",
    r"Remove-Item\s+C:\\Windows",
    r"Remove-Item\s+C:\\\*",
    r"rd\s+/s\s+/q\s+C:\\",
    r"del\s+/f\s+/s\s+/q\s+C:\\Windows",
    r"Stop-Computer",
    r"Disable-NetAdapter",
    r"Clear-Disk",
    r"Initialize-Disk",
]

# CONFIRM = risky but sometimes legitimate → PAUSE for the user's explicit approval
# (never runs unattended). Bias broad: a recursive delete, a remote-code-execute, a
# data-file wipe, or an SSH-key write should ALWAYS be seen before it runs, even if the
# model labelled it "low risk". Approval is cheap; an unattended destructive command is not.
CONFIRM_PATTERNS = [
    r"apt.*(remove|purge|autoremove)",
    r"(systemctl|service)\s+(stop|disable)",
    r"ufw\s+(disable|reset)",
    r"passwd\s+root",
    r"Uninstall-WindowsFeature",
    r"Stop-Service",
    r"Disable-WindowsOptionalFeature",
    r"Remove-WindowsFeature",
    r"DROP\s+(TABLE|DATABASE)",
    r"crontab\s+-r",
    r"Restart-Computer",
    # Any recursive/forced delete (the catastrophic paths are BLOCKED above; everything
    # else — rm -rf /var/www/*, /home/x, /tmp/build — must be approved, not auto-run).
    r"\brm\b(?=[^\n]*\s-[a-zA-Z]*r)", r"\brm\b[^\n]*--recursive",
    r"\bfind\b[^\n]*\s-delete\b",
    r"\bfind\b[^\n]*\s-exec(dir)?\s+(rm|mv|dd|chmod|chown|shred|truncate|sh|bash)\b",
    r"\bshred\b",
    r"\btruncate\b[^\n]*(-s\s*0|--size(=|\s)0)\b",         # zeroing a file (e.g. a DB data file)
    r"\bdd\b[^|\n]*\bof=/(?!dev/null)\S",                   # dd writing anywhere (devices are BLOCKED)
    r"\bchmod\b[^\n]*\s-[a-zA-Z]*R",                        # any recursive chmod
    r"\bchown\b[^\n]*\s-[a-zA-Z]*R",                        # any recursive chown
    r"authorized_keys",                                     # any touch of an SSH authorized_keys file
    # Remote-code-execution — fetch-and-run in EVERY practical form (the old single
    # `curl|sh` regex missed download-then-run, eval $(curl), base64|sh, bash <(curl)).
    r"(curl|wget|fetch)\b[^\n]*\|\s*(ba|z|c|k|da)?sh\b",
    r"(curl|wget|fetch)\b[^\n]*(-o|-O)\b[^\n]*(&&|;|\|\|)[^\n]*\b(ba|z|c|k|da)?sh\b",
    r"\beval\b[^\n]*\$\(\s*(curl|wget|fetch)\b",
    r"\b(ba|z|c|k|da)?sh\b[^\n]*<\(\s*(curl|wget|fetch)\b",
    r"base64\b[^\n]*\|\s*(ba|z|c|k|da)?sh\b",
    r"(curl|wget|fetch)\b[^\n]*(&&|;)\s*(ba|z|c|k|da)?sh\b",
    r"\bRemove-Item\b[^\n]*-Recurse",                      # PowerShell recursive delete
]


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    status: str          # 'ok' | 'blocked' | 'confirm'
    reason: str | None = None
    pattern: str | None = None


# ── Self-lockout guard (BUG-015) ─────────────────────────────────────────────
#
# The one class of damage ServerAlly can do to itself. A hardening step that closes root
# password login is textbook advice — and on a server ServerAlly reaches AS root WITH a
# password it removes our own way in. It happened: a `harden-server` mission applied
# `PermitRootLogin prohibit-password` to a live server, and because the step used `reload`
# rather than `restart` the session kept working, the step reported SUCCESS, and the
# lockout only surfaced on the next connection. There is no recovery from inside the
# product — it needs the provider's console.
#
# The reasoning that produced it is the interesting part: the model correctly observed
# that no root SSH key existed and treated that as evidence the change was harmless. The
# opposite is true — "no key is set up" is exactly what makes it fatal.
#
# So this REFUSES rather than warns, the same call `firewall_service.lockout_risk` makes
# for the same reason: a warning is something a customer clicks through once, and the cost
# here is a server nobody can reach.
#
# The STORED credential is the right authority. ServerAlly reconnects with whatever is on
# the asset, so if that says "password", disabling password login locks us out no matter
# what keys exist on the box for humans.


@dataclass(frozen=True)
class Access:
    """How ServerAlly itself reaches a server — the facts a lockout depends on."""

    username: str = ""
    auth_type: str = ""      # 'password' | 'key'
    port: int = 22


def access_for(server) -> Access:
    """Read the connection facts off a server row (duck-typed — no model import)."""
    try:
        port = int(getattr(server, "port", 22) or 22)
    except (TypeError, ValueError):
        port = 22
    return Access(
        username=(getattr(server, "username", "") or "").strip(),
        auth_type=(getattr(server, "auth_type", "") or "").strip().lower(),
        port=port,
    )


_ROOT_LOGIN_CLOSED = re.compile(
    r"PermitRootLogin\s+(?:prohibit-password|without-password|forced-commands-only|no)\b",
    re.IGNORECASE)
# The negative lookbehind keeps `KbdInteractiveAuthentication no` — which is harmless and
# appears right beside it in every hardening guide — from matching.
_PASSWORD_LOGIN_CLOSED = re.compile(r"(?<!Kbd)(?<!Interactive)PasswordAuthentication\s+no\b",
                                    re.IGNORECASE)
_KEY_ONLY = re.compile(r"AuthenticationMethods\s+publickey\b", re.IGNORECASE)
_ROOT_ACCOUNT_LOCKED = re.compile(
    r"\b(?:passwd\s+(?:-l|--lock)|usermod\s+(?:-L|--lock))\b[^\n;|&]*\broot\b",
    re.IGNORECASE)
_SSHD_PORT = re.compile(r"\bPort\s+(\d{1,5})\b")
_TOUCHES_SSHD = re.compile(r"sshd?_config|\bsshd\b|\bssh_set\b", re.IGNORECASE)

_ADD_A_KEY = ("Add an SSH key for this account and switch this server to key "
              "authentication in its settings, then it is safe to do.")
_CONSOLE = "the only way back in is your provider's console."


# Ways of LOOKING at a file. An allow-list, because the polarity matters here: something
# unrecognised must be treated as capable of changing the server, not assumed harmless.
_READ_VERBS = re.compile(
    r"^\s*(?:sudo\s+(?:-\S+\s+)*)?"
    r"(?:grep|egrep|fgrep|zgrep|cat|less|more|head|tail|awk|cut|sort|uniq|wc|stat|ls|find"
    r"|sshd|ssh-keygen|echo|printf|test|true)\b",
    re.IGNORECASE)
# Anything that can put bytes somewhere. `sed -n` reads; `sed -i` writes.
_WRITES_SOMEWHERE = re.compile(r">|\btee\b|\bsed\b[^|;&]*\s-i\b|\bdd\b", re.IGNORECASE)


def _only_reads(cmd: str) -> bool:
    """True when every part of the command merely looks at the server.

    Chained commands are split on the separators that start a NEW command (``&&``, ``||``,
    ``;``) and each part must independently be a read — otherwise
    ``grep something && ssh_set PermitRootLogin no`` would pass on the strength of its
    first word. Pipes are left alone: a pipeline's downstream still only reads, and the
    redirect check above covers the ways a pipeline can write.
    """
    if _WRITES_SOMEWHERE.search(cmd):
        return False
    parts = [p for p in re.split(r"&&|\|\||;", cmd) if p.strip()]
    return bool(parts) and all(_READ_VERBS.match(p) for p in parts)


def lockout_risk(cmd: str, access: "Access | None") -> str:
    """Empty string if this command cannot cut ServerAlly's own way in.

    Otherwise the reason it is refused, written for the person who would be locked out.

    Fails OPEN when we do not know how we connect (``access is None``). This guard runs on
    every command, and refusing real work because a caller did not supply the facts would
    be its own kind of damage — so the structural test in `tests/test_ssh_lockout_guard.py`
    is what stops a caller silently omitting them, rather than a refusal at runtime.
    """
    if access is None or not cmd:
        return ""

    # A command that only LOOKS at the server cannot lock anyone out of it. This keeps
    # `grep "PasswordAuthentication no" /etc/ssh/sshd_config` — a normal thing to run while
    # investigating — from being refused.
    #
    # Deliberately NOT `is_read_only_command`. Despite its docstring that classifier is a
    # DENY-list: it returns True for anything without a known mutating token, so it calls
    # `ssh_set PermitRootLogin prohibit-password` read-only and would have waved the exact
    # command from the incident straight through. A security guard must not inherit another
    # classifier's blind spots, so this is an explicit ALLOW-list of ways to look.
    if _only_reads(cmd):
        return ""

    by_password = access.auth_type == "password"
    as_root = access.username.lower() == "root"

    if by_password and as_root and _ROOT_LOGIN_CLOSED.search(cmd):
        return ("ServerAlly signs in to this server as root with a password, and that "
                "setting turns root password login off — it would lock ServerAlly out, and "
                + _CONSOLE + " " + _ADD_A_KEY)

    if by_password and _PASSWORD_LOGIN_CLOSED.search(cmd):
        return ("ServerAlly signs in to this server with a password, and that setting turns "
                "password logins off — it would lock ServerAlly out, and " + _CONSOLE + " "
                + _ADD_A_KEY)

    if by_password and _KEY_ONLY.search(cmd):
        return ("That setting requires an SSH key to sign in, but ServerAlly signs in to "
                "this server with a password — it would lock ServerAlly out. " + _ADD_A_KEY)

    if as_root and _ROOT_ACCOUNT_LOCKED.search(cmd):
        return ("That locks the root account's password, and root is the account ServerAlly "
                "uses to reach this server. It would lock ServerAlly out, and " + _CONSOLE)

    if _TOUCHES_SSHD.search(cmd):
        for found in _SSHD_PORT.findall(cmd):
            if int(found) != access.port:
                return (f"That moves SSH to port {found}, but ServerAlly reaches this server "
                        f"on port {access.port} — it would not be able to reconnect. Change "
                        f"the port on the asset first, or do this from your provider's "
                        f"console.")

    return ""


def validate_command(cmd: str, os_family: str = "linux",
                     access: "Access | None" = None) -> ValidationResult:
    """Check a single command against the blocklists and against our own way in.

    ``access`` is how ServerAlly reaches THIS server. Pass it wherever a server is known —
    without it the self-lockout guard cannot run. It stays optional only because a couple of
    callers genuinely have no server (the eval corpus).
    """
    # Checked first: its message names the exact problem and the way out, where a generic
    # blocklist pattern would only say "blocked".
    cut_off = lockout_risk(cmd, access)
    if cut_off:
        return ValidationResult(status="blocked", pattern="self-lockout", reason=cut_off)

    blocked = WINDOWS_BLOCKED if os_family == "windows" else LINUX_BLOCKED

    for pattern in blocked:
        if re.search(pattern, cmd, re.IGNORECASE):
            return ValidationResult(
                status="blocked",
                pattern=pattern,
                reason=f"Command matches blocked pattern: {pattern}",
            )

    for pattern in CONFIRM_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return ValidationResult(
                status="confirm",
                pattern=pattern,
                reason="Command requires explicit confirmation before running",
            )

    return ValidationResult(status="ok")


# ── Read-only guard (mission verification) ────────────────────────────────────
# A mission's verification pass may only OBSERVE — it gathers fresh evidence that
# the goal was achieved, and must never change the server's state. This is a
# DEFAULT-DENY guard: any hint of mutation → not read-only. A wrongly-rejected
# check just means "couldn't confirm" (safe, honest); a wrongly-accepted mutation
# would let a "verification" step delete or reconfigure data — so we bias hard
# toward rejecting. Network reads (curl/wget to stdout or /dev/null) are allowed
# so an HTTP "is the site up?" check works; writing a file or piping to a shell is not.
# A "command position": the start of the line/command, or right after a shell
# separator (; & | newline `(` `` ` `` `$(`) or a loop keyword (do/then). Used to anchor
# tokens (eval, crontab) whose bare word legitimately appears inside a quoted grep
# pattern or an echo label — so we flag `; eval ...` but not `grep 'eval\(base64'`.
_CMD_POS = r"(?:^|[;&|(`\n]|\$\(|\bdo\b|\bthen\b)\s*"

# Case-INSENSITIVE mutating tokens (shell verbs, SQL, redirects, pipe-to-shell).
_MUTATION_TOKENS_I = [
    # Filesystem / ownership
    r"\brm\b", r"\brmdir\b", r"\bmv\b", r"\bcp\b", r"\bdd\b", r"\bmkfs\b",
    r"\bchmod\b", r"\bchown\b", r"\bchgrp\b", r"\bln\b", r"\btouch\b", r"\bmkdir\b",
    r"\btee\b", r"\btruncate\b", r"\bshred\b", r"\bsetfacl\b", r"\binstall\s+-\S",
    r"\bsed\b[^|;]*\s-i", r"\bperl\b[^|;]*\s-i",
    # Services / packages / power
    r"\b(systemctl|service)\s+\S*\s*(start|stop|restart|reload|enable|disable|mask|unmask)",
    r"\b(apt|apt-get|dnf|yum|apk|zypper|snap)\b[^|;]*\b(install|remove|purge|update|upgrade|autoremove)\b",
    r"\bpip\d?\s+install\b", r"\bnpm\s+(install|i|ci|update|run)\b", r"\byarn\s+(add|install)\b",
    r"\b(reboot|shutdown|halt|poweroff|init)\b", r"\bkill(all)?\b", r"\bpkill\b",
    # Accounts / firewall / mounts / cron writes — `passwd` must not match /etc/passwd.
    r"\b(useradd|usermod|userdel|groupadd|groupdel|adduser|deluser|chpasswd)\b",
    r"(?<![\w/])passwd(?![\w/])",
    r"\b(iptables|ip6tables|nft|ufw|firewall-cmd)\b",
    r"\bmount\b", r"\bumount\b", r"\bswapon\b", r"\bswapoff\b", r"\bsetcap\b",
    # `crontab` writes (crontab -r/-e/<file>) — but `crontab -l` is a read, and the
    # bare word "crontab" often appears in an echo label ("--- root crontab ---") or a
    # grep pattern. Anchor to a COMMAND position so a quoted mention isn't flagged.
    _CMD_POS + r"crontab\b(?!\s+-l)",
    # Data stores (SQL writes, dumps that write a file)
    r"\b(DROP|DELETE|INSERT|UPDATE|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|REPLACE)\s",
    r"\bmysqldump\b", r"\bpg_dump\b", r"\bmysqladmin\b",
    # WordPress / git / docker state changes
    r"\bwp\s+[\w-]+\s+(install|activate|deactivate|update|delete|create|import|reset|add|regenerate|download|scaffold|flush|set)\b",
    r"\bgit\s+(clone|pull|fetch|checkout|reset|merge|push|apply|clean|rm|commit)\b",
    r"\bdocker(-compose)?\s+(run|rm|start|stop|restart|kill|exec|pull|build|up|down|create)\b",
    # `find` that deletes or executes anything (a plain search is fine; -delete/-exec is not)
    r"\bfind\b[^\n]*\s-(delete|exec|execdir|ok|fprint|fls)\b",
    # Malware SCANNERS invoked with a DESTRUCTIVE action (remove/quarantine/clean) — these
    # delete or move infected files, so they're NEVER a read-only verification check even
    # though the base command looks like a scan. A plain scan (clamscan --infected, maldet
    # -a, `imunify… list`) carries no such flag and stays read-only. (Live-found via evals,
    # 2026-07-12: the verify gate must not let a "scan" auto-clean the server it's checking.)
    r"\bclam(d)?scan\b[^\n]*--(remove|move)\b",
    r"\bmaldet\b[^\n]*(\s-[qn]\b|--(quarantine|clean))",
    r"\bimunify[\w-]*\b[^\n]*\bcleanup\b",
    # awk/sed that call out to the shell or write a file (a plain filter is read-only)
    r"\bawk\b[^\n]*system\s*\(", r"\bawk\b[^\n]*\bprint[^\n]*>\s*\"?/",
    # Editors / stream editors that can write the file they open
    r"\b(vi|vim|nano|pico|emacs|ed|ex)\b", r"\bsed\b[^\n]*\s-i",
    # Executing arbitrary code via a shell: sh -c, process substitution, source, exec
    r"\b(ba|z|c|k|da)?sh\b\s+(-c\b|<)", r"<\(", r"\bsource\b", r"(^|\s|;)\.\s+\S",
    # Shell-level mutation: redirect into a real file, pipe to a shell, background exec.
    # `eval` runs arbitrary code — but the literal word also appears inside webshell-
    # signature grep patterns ('eval\(base64_decode|...') that incident-response uses as
    # a READ-ONLY scan. Anchor `eval` to a COMMAND position so a quoted mention (search
    # pattern / label) isn't flagged, while real `eval "$(curl ...)"` still is.
    r">\s*/(?!dev/null)", r">>", r"\|\s*(ba|z|c|k)?sh\b", _CMD_POS + r"eval\b", r"\bnohup\b", r"\bxargs\b",
]
# Case-SENSITIVE tokens — curl -O vs -o and PowerShell PascalCase cmdlets carry
# meaning in their case, so matching case-insensitively would flag benign reads.
_MUTATION_TOKENS_CS = [
    # Language interpreters with INLINE code (lowercase code flags: -c/-e/-r/-f) can do
    # ANYTHING (unlink, file_put_contents, plant a fake proof marker) — never a legit
    # read-only check. Case-sensitive so `awk -F:` / `perl -F` (field split) don't match.
    r"\b(python|python3|php|perl|ruby|node|nodejs|lua|Rscript)\b[^\n]*\s-[cerf]\b",
    r"\bwget\b(?![^|;]*O-(\s|$))",          # wget that SAVES a file (not `-O-` to stdout)
    r"\bcurl\b[^|;]*\s-O\b",                # curl -O (save as remote name)
    r"\bcurl\b[^|;]*-o\s+(?!/dev/null)\S",  # curl -o <file> (but /dev/null is fine)
    r"\b(Remove|Set|Stop|Start|Restart|New|Install|Uninstall|Clear|Format|Disable|Enable|Rename|Move|Copy|Add|Export|Out)-\w+",
    r"\bOut-File\b", r"\bSet-Content\b",
]
_MUTATION_RE = (
    [re.compile(p, re.IGNORECASE) for p in _MUTATION_TOKENS_I]
    + [re.compile(p) for p in _MUTATION_TOKENS_CS]
)


def is_read_only_command(cmd: str) -> bool:
    """True only if `cmd` merely OBSERVES — safe to run as a mission verification
    check. Default-deny: blank, blocklisted, or anything carrying a mutating token
    is rejected. Used by the mission engine so a verification pass can never change
    the server it's checking."""
    cmd = (cmd or "").strip()
    if not cmd:
        return False
    if validate_command(cmd, "linux").status == "blocked":
        return False
    if validate_command(cmd, "windows").status == "blocked":
        return False
    return not any(rx.search(cmd) for rx in _MUTATION_RE)


def validate_plan(commands: list[dict], os_family: str = "linux",
                  access: "Access | None" = None) -> ValidationResult:
    """Validate all commands in a plan. Blocked takes priority over confirm."""
    confirm_result: ValidationResult | None = None

    for item in commands:
        cmd = item.get("cmd", "")
        result = validate_command(cmd, os_family, access)
        if result.status == "blocked":
            return result
        if result.status == "confirm" and confirm_result is None:
            confirm_result = result

    return confirm_result or ValidationResult(status="ok")


def highest_risk(commands: list[dict]) -> str:
    """Return the highest risk_level across all commands in a plan."""
    levels = {"low": 0, "medium": 1, "high": 2}
    best = 0
    for item in commands:
        lvl = levels.get(item.get("risk_level", "low"), 0)
        if lvl > best:
            best = lvl
    return ["low", "medium", "high"][best]

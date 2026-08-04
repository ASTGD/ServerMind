"""Put a site's file ownership and permissions back to a known-good state.

Ploi's version of this is a confirm dialog that says, correctly, *no undo*. Ours says the
same, and then refuses the cases where "no undo" would mean "no server".

**The whole feature is one recursive `chown`, so the whole risk is the path.** If the
document root were ever empty, `/`, or a shared parent like `/var/www`, this would hand the
web server ownership of the operating system or of every other customer's site on the
machine. That is not a warning to show — it is a command not to run. `check_target`
refuses anything that is not deep enough to be one site's own folder, and the path is
resolved on the server FROM the site rather than accepted from a caller.

Why anyone needs it: our own scheduled-jobs work found the failure it repairs. A cron job
run as root writes root-owned files into `storage/`, the web server can no longer write
them, and the site breaks days later with an error pointing nowhere near cron.
"""
from __future__ import annotations

import shlex

# The user the web server runs as. Checked on the server rather than assumed, because
# Debian/Ubuntu use www-data and the RHEL family use nginx.
WEB_USERS = ("www-data", "nginx", "apache")

# A path with fewer parts than this is not one site's folder. `/var/www` is 2, and handing
# the web server ownership of it would hand it every other site on the machine.
MIN_DEPTH = 3

# Shallow or shared paths that are never a single site's own directory, whatever their
# depth. Listed as well as depth-checked because `/home/user` passes a depth test and is
# still somebody's whole account.
FORBIDDEN = {
    "/", "/etc", "/usr", "/var", "/var/www", "/var/lib", "/srv", "/opt", "/home", "/root",
    "/bin", "/sbin", "/boot", "/dev", "/proc", "/sys", "/tmp",
}


class PermissionsError(Exception):
    """Something we refuse to do, in words worth showing the customer."""


def check_target(doc_root: str | None) -> str:
    """The folder this may touch, or a refusal.

    Deliberately strict and deliberately not clever: there is no repair worth performing on
    an ambiguous path when the failure mode is `chown -R` across somebody's server.
    """
    raw = (doc_root or "").strip()
    # Checked BEFORE the trailing slash is stripped: "/" would otherwise become an empty
    # string and be reported as "we do not know which folder", which is not what is wrong
    # with it. The most dangerous input deserves the most accurate refusal.
    if raw == "/":
        raise PermissionsError(
            "“/” is the whole server, not one site's folder. That is refused.")
    path = raw.rstrip("/")
    if not path:
        raise PermissionsError(
            "We do not know which folder holds this site, so there is nothing safe to "
            "reset. Open Manage and check the site's configuration first.")
    if not path.startswith("/"):
        raise PermissionsError("That is not a full path, so it will not be touched.")
    if ".." in path.split("/"):
        raise PermissionsError("That path is not one we will follow.")
    if path in FORBIDDEN:
        raise PermissionsError(
            f"“{path}” is a system folder, not one site's own. Resetting ownership there "
            f"would affect the whole server, so it is refused.")
    parts = [p for p in path.split("/") if p]
    if len(parts) < MIN_DEPTH:
        raise PermissionsError(
            f"“{path}” is too high up to be a single site's folder. Resetting there could "
            f"affect other sites on this server, so it is refused.")
    return path


def build_command(doc_root: str) -> str:
    """Reset ownership and modes under one site's folder, and nowhere else.

    Directories become 755 and files 644 — readable by the web server, writable only by its
    own user. Executable bits are cleared from ordinary files on purpose: a `.php` that is
    also executable is a small thing, but it is one of the ways an uploaded file turns into
    a running one.
    """
    target = shlex.quote(check_target(doc_root))
    users = " ".join(WEB_USERS)
    return (
        f'set -e; '
        f'T={target}; '
        f'[ -d "$T" ] || {{ echo "That folder is not on this server."; exit 3; }}; '
        # Belt and braces: the guard above runs in Python, and this one runs on the machine
        # about to be changed. Depth is counted the same way, so a path that somehow reached
        # here without passing the first check still cannot be run.
        f'case "$T" in /|/etc|/usr|/var|/var/www|/home|/root|/srv|/opt) '
        f'  echo "Refusing to change a system folder."; exit 4 ;; esac; '
        f'D="$(echo "$T" | awk -F/ "{{print NF-1}}")"; '
        f'[ "$D" -ge {MIN_DEPTH} ] || {{ echo "Refusing: that path is too high up."; exit 4; }}; '
        # Which user the web server actually runs as, read off the machine.
        f'OWNER=""; for u in {users}; do id -u "$u" >/dev/null 2>&1 && {{ OWNER="$u"; break; }}; done; '
        f'[ -n "$OWNER" ] || {{ echo "No web server user on this machine."; exit 5; }}; '
        f'BEFORE="$(find "$T" ! -user "$OWNER" 2>/dev/null | wc -l)"; '
        f'chown -R "$OWNER":"$OWNER" "$T"; '
        f'find "$T" -type d -exec chmod 755 {{}} + 2>/dev/null || true; '
        f'find "$T" -type f -exec chmod 644 {{}} + 2>/dev/null || true; '
        # Laravel and WordPress both ship a runner that has to stay executable. Restoring
        # ownership must not stop `artisan` working, which would look like our repair broke
        # the site.
        f'[ -f "$T/artisan" ] && chmod 755 "$T/artisan" || true; '
        f'[ -f "$T/../artisan" ] && chmod 755 "$T/../artisan" || true; '
        f'AFTER="$(find "$T" ! -user "$OWNER" 2>/dev/null | wc -l)"; '
        f'echo "owner=$OWNER fixed=$BEFORE remaining=$AFTER"'
    )


_OUTCOMES: dict[int, str] = {
    3: "That folder is not on the server, so nothing was changed.",
    4: "That folder is too high up to reset safely, so nothing was changed.",
    5: "No web server user was found on this machine, so nothing was changed.",
}


def explain(code: int, output: str) -> tuple[bool, str]:
    if code == 0:
        owner, fixed = "the web server", None
        for part in (output or "").split():
            if part.startswith("owner="):
                owner = part.split("=", 1)[1]
            if part.startswith("fixed="):
                fixed = part.split("=", 1)[1]
        if fixed == "0":
            return True, (f"Nothing needed changing — every file already belonged to "
                          f"{owner}.")
        return True, (f"Done. {fixed} file(s) that did not belong to {owner} were put back, "
                      f"and folders and files are back to their normal permissions.")
    if code in _OUTCOMES:
        return False, _OUTCOMES[code]
    tail = (output or "").strip().splitlines()
    return False, (tail[-1] if tail else "The permissions could not be reset.")

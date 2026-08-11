"""Whether we can actually read what we are about to claim we read.

Every cloud image ships with root SSH disabled — AWS, Google Cloud and Azure all do — so the
ordinary way to connect is a user like `ubuntu` or `ec2-user` with passwordless sudo. Our
probes were written assuming they are already root, and most of them never ask for anything
more.

Measured on a real AWS server connected as `ubuntu`:

| Path                              | Result   |
|-----------------------------------|----------|
| `/usr/local/lsws/conf/vhosts`     | denied   |
| `/home/firevps.net`               | denied   |
| `/var/log/nginx`                  | denied   |
| `[ -x /usr/bin/cyberpanel ]`      | silently false — cannot traverse `/usr/local/CyberCP` |

A `find` that is denied everything prints nothing, and a probe that returns nothing looks
exactly like a probe that found nothing. **The malware scan therefore reported "No threats
found" — not "I could not look."** That is a false all-clear on the most safety-critical
feature in the product, and it is the same shape as the bug `threat_service._t` was written to
avoid: *"an empty webshell section reads as clean, i.e. a silent false all-clear on a critical
check."*

This module is the answer, and it is deliberately two separate things:

1. **`PRELUDE`** — decide once, at the top of a probe, whether we are root, can become root
   without a password, or neither; and set `$SA_SUDO` accordingly so a privileged command can
   simply be prefixed with it.
2. **`level` and the rules below** — so a caller that could NOT read can say so, instead of
   reporting an empty result as a clean one.

The second matters even after the first works, because `sudo -n` is not always available: a
user with no sudo rights, or with sudo that demands a password, gets `none`.
"""
from __future__ import annotations

#: Section id the prelude reports under, so a probe using the shared section format can read
#: the answer back out of its own output.
SECTION = "sa_privilege"

ROOT = "root"      #: connected as root
SUDO = "sudo"      #: not root, but `sudo -n` works — effectively root for our purposes
NONE = "none"      #: neither; privileged paths are unreadable

#: Sets `$SA_SUDO` (empty, or `sudo -n`) and prints the level under `SECTION`.
#:
#: `sudo -n` never prompts — it fails immediately instead of hanging forever waiting for a
#: password on a connection with no terminal. That is the whole reason for `-n`, and the
#: same reason `app_registry.owner_prelude` uses it when dropping DOWN to a site owner.
PRELUDE = f'''
SA_SUDO=""
if [ "$(id -u)" -eq 0 ]; then
  SA_PRIV={ROOT}
elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
  SA_PRIV={SUDO}; SA_SUDO="sudo -n"
else
  SA_PRIV={NONE}
fi
'''.strip()


def parse(raw: str) -> str:
    """Read the level back. Anything unrecognised is `none`.

    Fails closed on purpose: if we cannot tell what we had, we must not assume we had
    everything — that assumption is exactly what produces the false all-clear.
    """
    value = (raw or "").strip().splitlines()[0].strip() if (raw or "").strip() else ""
    return value if value in (ROOT, SUDO, NONE) else NONE


def can_read_everything(level: str) -> bool:
    """True when a privileged probe will actually see what it is looking for."""
    return level in (ROOT, SUDO)


def explain(level: str) -> str | None:
    """What to tell the customer, or None when there is nothing to say."""
    if can_read_everything(level):
        return None
    return ("ServerAlly is connected as a user that cannot read other accounts' files, and "
            "cannot become root without a password. Some checks could not run. Connect as "
            "root, or give this user passwordless sudo, for a complete result.")


def may_report_clean(level: str, *, skipped: list) -> bool:
    """**The rule this module exists for: you may report bad news while blind, but never
    good news.**

    Finding malware with half the disk unreadable is still finding malware — the answer is
    true and acting on it is right. Finding *nothing* with half the disk unreadable is not an
    answer at all, and reporting it as "clean" is the one outcome that gets somebody hurt.
    """
    return not skipped and can_read_everything(level)

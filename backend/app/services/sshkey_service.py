"""SSH key management — see who can log in, and add or remove people.

The `ssh-key-auth` playbook can switch a server to key-only login; nothing has ever
been able to answer the question that follows it — *which keys are on this server, and
whose are they?* On a server a team has touched for a year, that list is the access
control, and nobody has read it.

Two properties carry this.

**A key we are using is never removed.** Deleting the wrong line here is the same
outcome as the firewall guard's: the command succeeds and the server is unreachable.
`removal_risk` compares fingerprints, and it fails closed — if it cannot tell whether a
key is the one in use, it refuses.

**A key is validated, not escaped.** `authorized_keys` is line-oriented, so a value
carrying a newline adds an entry nobody agreed to — potentially with `command=` or
`from=` options that change what the *other* keys can do. Keys are parsed into their
three real parts and rebuilt from those, so nothing else survives the round trip.
"""
from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass

SENTINEL = "___SM_KEY___"

# The types OpenSSH still accepts for authentication. `ssh-dss` is deliberately absent:
# it is disabled by default in modern OpenSSH, so accepting one would let someone add a
# key that quietly never works.
KEY_TYPES = {
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com", "sk-ecdsa-sha2-nistp256@openssh.com",
}

MAX_KEYS = 200
MAX_LINE = 8192


class InvalidKey(ValueError):
    """Not something we are willing to write into authorized_keys."""


class WouldLockOut(Exception):
    """Removing this key would end our own access."""


@dataclass
class PublicKey:
    type: str
    body: str                  # the base64 blob
    comment: str = ""
    fingerprint: str = ""      # SHA256:… as OpenSSH prints it
    line: int = 0              # 1-based position in the file
    options: str = ""          # from="…",command="…" — shown, never invented by us

    @property
    def text(self) -> str:
        """The line as we would write it. Rebuilt from parts, never passed through."""
        base = f"{self.type} {self.body}"
        if self.comment:
            base += f" {self.comment}"
        return f"{self.options} {base}".strip() if self.options else base

    @property
    def label(self) -> str:
        """Something a person can recognise. Comments are usually user@machine."""
        return self.comment or f"{self.type} key"


def fingerprint(key_type: str, body: str) -> str:
    """The SHA256 fingerprint OpenSSH shows, so it can be compared with `ssh-keygen`."""
    try:
        blob = base64.b64decode(body, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise InvalidKey("The key's data is not valid — it may have been cut short "
                         "when it was copied.") from exc
    digest = hashlib.sha256(blob).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


_OPTION_RE = re.compile(r"^(?P<opts>[^\s]*[=\"][^\s]*(?:\s|,)?[^\s]*)\s+(?=\S+\s)")


def parse_key(raw: str) -> PublicKey:
    """Parse one public key. Everything not understood is refused.

    The parse is the sanitiser: only the type, the base64 body and a cleaned comment
    survive, so a pasted line cannot smuggle a second entry or an option that changes
    what other keys may do.
    """
    text = (raw or "").strip()
    if not text:
        raise InvalidKey("Paste the public key.")
    # Checked before the line-count rule, because a private key is ALWAYS several lines
    # and would otherwise be turned away with a message about formatting. Someone who
    # has just pasted a private key into a web form needs to be told that, plainly, and
    # told to replace it — it is the most important sentence in this file.
    if "PRIVATE KEY" in text.upper() or text.startswith("-----BEGIN"):
        raise InvalidKey(
            "That is a PRIVATE key — the secret half. Never paste it anywhere, and "
            "replace it now that it has left your machine. The one to add here is the "
            "public half, usually the same file name ending in .pub.")
    if len(text) > MAX_LINE:
        raise InvalidKey("That key is far too long to be a public key.")
    if "\n" in text or "\r" in text:
        raise InvalidKey(
            "That looks like more than one line. Add one key at a time — a stray line "
            "break can add an entry you did not intend.")

    parts = text.split()
    # Some keys are pasted with options in front. We do not carry them across: they can
    # change what a key is allowed to do, and silently keeping something the customer
    # did not read is worse than asking for a plain key.
    if parts and parts[0] not in KEY_TYPES:
        raise InvalidKey(
            f"A public key starts with its type, like “ssh-ed25519 AAAA…”. "
            f"“{parts[0][:24]}” is not one we recognise.")
    if len(parts) < 2:
        raise InvalidKey("That key is missing its data — it may have been cut short.")

    key_type, body = parts[0], parts[1]
    comment = " ".join(parts[2:])[:120]
    # A comment ends up in a file we write; keep it to characters that cannot mean
    # anything else there.
    comment = re.sub(r"[^\w@.\-+ ()\[\]]", "", comment).strip()
    if not re.fullmatch(r"[A-Za-z0-9+/=]+", body):
        raise InvalidKey("The key's data contains characters a key never has — it was "
                         "probably copied with something extra.")
    return PublicKey(type=key_type, body=body, comment=comment,
                     fingerprint=fingerprint(key_type, body))


def parse_file(text: str) -> list[PublicKey]:
    """Read an existing authorized_keys. Unreadable lines are skipped, not guessed at."""
    keys: list[PublicKey] = []
    for n, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        options = ""
        parts = line.split()
        if parts and parts[0] not in KEY_TYPES:
            # An options prefix. Keep it verbatim so the customer SEES the restriction
            # rather than us quietly dropping it from their view of the file.
            for i, tok in enumerate(parts):
                if tok in KEY_TYPES:
                    options = " ".join(parts[:i])
                    parts = parts[i:]
                    break
            else:
                continue
        if len(parts) < 2:
            continue
        try:
            fp = fingerprint(parts[0], parts[1])
        except InvalidKey:
            continue
        keys.append(PublicKey(type=parts[0], body=parts[1],
                              comment=" ".join(parts[2:])[:120],
                              fingerprint=fp, line=n, options=options))
        if len(keys) >= MAX_KEYS:
            break
    return keys


def public_from_private(private_pem: str) -> str | None:
    """The fingerprint of the key ServerAlly itself connects with, if it has one.

    This is what makes the guard exact rather than a guess: we do not ask which key is
    ours, we derive it from the credential we are actually authenticating with.
    """
    try:
        from cryptography.hazmat.primitives import serialization
        loaded = serialization.load_ssh_private_key(private_pem.encode(), password=None)
        pub = loaded.public_key().public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH).decode()
        parts = pub.split()
        return fingerprint(parts[0], parts[1]) if len(parts) >= 2 else None
    except Exception:  # noqa: BLE001
        # Encrypted, an unusual format, or not a key at all. The guard treats an
        # unknown fingerprint as "cannot prove this is safe", which is the point.
        return None


def removal_risk(keys: list[PublicKey], target: PublicKey, *,
                 our_fingerprint: str | None, auth_type: str) -> str:
    """Empty if the key is safe to remove. Otherwise, why it is refused."""
    if our_fingerprint and target.fingerprint == our_fingerprint:
        return ("That is the key ServerAlly connects with. Removing it would cut our "
                "own access to this server, and every action here would stop working.")

    remaining = [k for k in keys if k.fingerprint != target.fingerprint]
    if not remaining and auth_type == "key":
        # We authenticate with a key but could not identify which — removing the last
        # one is the case where being wrong is unrecoverable.
        return ("That is the last key on this server, and ServerAlly signs in with a "
                "key. Removing it would lock everyone out. Add the replacement key "
                "first, then remove this one.")
    return ""


# ── reading and writing the file ─────────────────────────────────────────────
def home_probe(username: str) -> str:
    """Where this user's authorized_keys lives, and what is in it. Read-only.

    The home directory is asked of the system rather than assumed to be `/home/<user>`,
    because root's is `/root` and panels put accounts in their own places.
    """
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", (username or "").lower()):
        raise InvalidKey(f"“{username}” is not a valid user name.")
    u = username.lower()
    s = SENTINEL
    return (
        f'H=$(getent passwd {u} | cut -d: -f6); '
        f'echo "{s}HOME"; echo "$H"; '
        f'echo "{s}PERMS"; stat -c "%a %U" "$H/.ssh" 2>/dev/null; '
        f'stat -c "%a %U" "$H/.ssh/authorized_keys" 2>/dev/null; '
        f'echo "{s}KEYS"; cat "$H/.ssh/authorized_keys" 2>/dev/null; '
        f'echo "{s}END"'
    )


def parse_home_probe(out: str) -> tuple[str, list[PublicKey], str]:
    """Returns (home, keys, permission note)."""
    sec: dict[str, str] = {}
    cur = ""
    for line in (out or "").splitlines():
        if line.startswith(SENTINEL):
            cur = line[len(SENTINEL):].strip()
            sec[cur] = ""
        elif cur:
            sec[cur] += line + "\n"

    home = sec.get("HOME", "").strip().splitlines()
    home = home[0].strip() if home else ""
    keys = parse_file(sec.get("KEYS", ""))

    note = ""
    perms = [l.split() for l in sec.get("PERMS", "").strip().splitlines() if l.strip()]
    # sshd ignores the whole file when it is group- or world-writable, so a wrong mode
    # here looks exactly like "the key does not work" — worth saying out loud.
    if perms and len(perms[0]) >= 1 and perms[0][0] not in ("700", "755"):
        note = (f"The .ssh folder's permissions are {perms[0][0]}. SSH ignores keys "
                "when the folder is too open, so logins may fail until this is fixed.")
    elif len(perms) > 1 and perms[1][0] not in ("600", "644"):
        note = (f"The authorized_keys file's permissions are {perms[1][0]}. SSH "
                "ignores the file when it is writable by others.")
    return home, keys, note


def render(keys: list[PublicKey]) -> str:
    """The whole file, rebuilt from parsed keys.

    Written whole rather than appended to, so the file always ends up in a shape we
    understand — and so a duplicate or a broken line already in there is cleaned up
    rather than carried forward forever.
    """
    header = ("# Managed by ServerAlly. Each line is one key that may sign in as this "
              "user.\n")
    return header + "".join(k.text + "\n" for k in keys)


def write_commands(home: str, content_path: str) -> str:
    """Move a staged file into place with the permissions sshd insists on.

    `.ssh` at 700 and the file at 600 are not tidiness: sshd silently refuses to read
    them otherwise, and the customer sees "key does not work" with nothing in any log
    they know how to find.
    """
    import shlex
    h, tmp = shlex.quote(home), shlex.quote(content_path)
    return (f"set -e; mkdir -p {h}/.ssh; "
            f"cat {tmp} > {h}/.ssh/authorized_keys; rm -f {tmp}; "
            f"chmod 700 {h}/.ssh; chmod 600 {h}/.ssh/authorized_keys; "
            f"chown -R $(stat -c '%U:%G' {h}) {h}/.ssh")

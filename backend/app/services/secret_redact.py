"""Server-side secret redaction — mask secret VALUES in text before it leaves the box.

The server-side counterpart of ``frontend/src/lib/redactSecrets.ts``: over MCP there is no
browser to redact file content client-side, so ``read_file`` must run this before returning
a file to a customer's AI (docs/MCP-SERVER-PLAN.md §6). Best-effort + conservative — errs
toward over-masking; keeps the file readable (keys + structure stay), masks only the
sensitive values. Ported line-for-line from the client filter so behaviour matches.
"""
from __future__ import annotations

import re

SECRET_MASK = "[secret hidden]"

# Key names whose value should be hidden. Precise enough to avoid masking ordinary config
# (kept out: bare "auth", "key" — too broad).
_SENSITIVE_KEY = (
    r"pass(?:word|wd|phrase)?|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|"
    r"secret[_-]?key|private[_-]?key|client[_-]?secret|auth[_-]?token|bearer|"
    r"authorization|credentials?|encryption[_-]?key|signing[_-]?key|master[_-]?key"
)

# Standalone high-signal tokens, masked wherever they appear.
_TOKEN_PATTERNS = [
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9]{16,}\b"),      # OpenAI/Stripe-style
    re.compile(r"\bsm_live_[A-Za-z0-9_-]{10,}\b"),          # our own gateway token
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),                # GitHub PAT
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                    # AWS access key id
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),        # Slack
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{6,}\b"),  # JWT
]

_PEM_BEGIN = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
_PEM_END = re.compile(r"-----END")
_INDENT = re.compile(r"^[ \t]*")

# A sensitive key with NO inline value (or a `|`/`>` YAML block indicator) → value is on
# the following indented lines.
_BLOCK_HEAD = re.compile(
    rf"^([ \t]*)['\"]?[\w.\- ]*(?:{_SENSITIVE_KEY})[\w.\- ]*['\"]?\s*:\s*[|>][+-]?\d*\s*$|"
    rf"^([ \t]*)['\"]?[\w.\- ]*(?:{_SENSITIVE_KEY})[\w.\- ]*['\"]?\s*:\s*$",
    re.IGNORECASE,
)
# define('DB_PASSWORD', 'value') — PHP / wp-config.php
_DEFINE = re.compile(
    rf"(define\s*\(\s*['\"][^'\"]*(?:{_SENSITIVE_KEY})[^'\"]*['\"]\s*,\s*['\"])([^'\"]+)(['\"])",
    re.IGNORECASE,
)
# KEY=value | KEY: value | KEY => value — env / ini / yaml / json (key stays)
_KV = re.compile(
    rf"^(\s*['\"]?[\w.\- ]*(?:{_SENSITIVE_KEY})[\w.\- ]*['\"]?\s*(?:=>|[:=])\s*)(['\"]?)([^\n]*?)(['\"]?\s*[,;]?\s*)$",
    re.IGNORECASE,
)
# Connection strings: scheme://user:password@host
_CONN = re.compile(r"(\b[a-z][a-z0-9+.\-]*://[^\s:@/]+:)([^@\s/]+)(@)", re.IGNORECASE)


def _indent_of(line: str) -> int:
    return len(_INDENT.match(line).group(0))


def redact_secrets(text: str) -> tuple[str, int]:
    """Return ``(redacted_text, mask_count)``."""
    counter = [0]

    def _def_sub(m: re.Match) -> str:
        counter[0] += 1
        return m.group(1) + SECRET_MASK + m.group(3)

    def _kv_sub(m: re.Match) -> str:
        val = m.group(3)
        if not val.strip() or val.strip() == SECRET_MASK:
            return m.group(0)
        counter[0] += 1
        return m.group(1) + m.group(2) + SECRET_MASK + m.group(4)

    def _conn_sub(m: re.Match) -> str:
        counter[0] += 1
        return m.group(1) + SECRET_MASK + m.group(3)

    in_pem = False
    block_key_indent: int | None = None
    out: list[str] = []

    for raw in text.split("\n"):
        # Multi-line PEM private-key blocks → mask the body.
        if _PEM_BEGIN.search(raw):
            in_pem = True
            counter[0] += 1
            out.append(raw)
            continue
        if in_pem:
            if _PEM_END.search(raw):
                in_pem = False
                out.append(raw)
            else:
                out.append(SECRET_MASK if raw.strip() else raw)
            continue

        # Inside a block scalar under a sensitive key: mask more-indented content lines.
        if block_key_indent is not None:
            if not raw.strip():
                out.append(raw)
                continue
            if _indent_of(raw) > block_key_indent:
                counter[0] += 1
                out.append(raw[: _indent_of(raw)] + SECRET_MASK)
                continue
            block_key_indent = None  # de-indented → the block ended; fall through

        if _BLOCK_HEAD.match(raw):
            block_key_indent = _indent_of(raw)
            out.append(raw)
            continue

        line = _DEFINE.sub(_def_sub, raw)
        line = _KV.sub(_kv_sub, line)
        line = _CONN.sub(_conn_sub, line)
        for pat in _TOKEN_PATTERNS:
            line, n = pat.subn(SECRET_MASK, line)
            counter[0] += n
        out.append(line)

    return "\n".join(out), counter[0]

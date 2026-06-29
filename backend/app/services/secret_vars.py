"""Secret-aware handling of playbook install inputs (``variables_used``).

Install inputs can contain credentials the user typed (``DB_PASS``, ``ADMIN_PASSWORD``,
``MYSQL_ROOT_PASS`` …). We encrypt those **at rest** with the same AES-256-GCM used for SSH
credentials (``crypto_service``), and mask them in any UI. A variable is treated as a
secret when its NAME looks credential-ish — so this never depends on inspecting the value."""
from __future__ import annotations

import re

from app.services.crypto_service import decrypt, encrypt

_SECRET_RE = re.compile(r"(PASS|PASSWORD|PWD|SECRET|TOKEN|KEY|CRED)", re.IGNORECASE)
_ENC_PREFIX = "enc:v1:"  # marks an already-encrypted value (idempotent encrypt + detectable)
_MASK = "••••••"


def is_secret(name: str) -> bool:
    """True if a variable name looks credential-ish and should be encrypted/masked."""
    return bool(_SECRET_RE.search(name or ""))


def is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(_ENC_PREFIX)


def encrypt_variables(variables: dict | None) -> dict:
    """A copy of install inputs with secret-named values encrypted at rest (AES-256-GCM);
    non-secret values pass through. Idempotent — already-encrypted values are left as-is —
    so it is safe to run repeatedly and on a backfill."""
    out: dict = {}
    for key, value in (variables or {}).items():
        if value is None:
            out[key] = ""
        elif is_secret(key) and not is_encrypted(value):
            out[key] = _ENC_PREFIX + encrypt(str(value))
        else:
            out[key] = str(value)
    return out


def decrypt_variable(value: object) -> str:
    """Decrypt a stored value if it's an encrypted blob; otherwise return it unchanged."""
    if is_encrypted(value):
        return decrypt(value[len(_ENC_PREFIX):])
    return "" if value is None else str(value)


def mask_variables(variables: dict | None) -> dict:
    """Install inputs for display: secret-named values shown as •••••• (never the stored
    value or ciphertext), everything else unchanged."""
    return {k: (_MASK if is_secret(k) else str(v)) for k, v in (variables or {}).items()}

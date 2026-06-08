from __future__ import annotations
"""AES-256-GCM encryption for server credentials."""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

# Derive a 32-byte key from the hex config value
_KEY: bytes = (
    bytes.fromhex(settings.ENCRYPTION_KEY)
    if len(settings.ENCRYPTION_KEY) == 64
    else settings.ENCRYPTION_KEY.encode().ljust(32, b"\x00")[:32]
)


def encrypt(plaintext: str) -> str:
    """Encrypt plaintext with AES-256-GCM.

    Returns a base64-encoded string: nonce(12 bytes) + ciphertext + tag(16 bytes).
    """
    aesgcm = AESGCM(_KEY)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ciphertext).decode()


def decrypt(token: str) -> str:
    """Decrypt a value produced by encrypt()."""
    raw = base64.b64decode(token)
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(_KEY)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()

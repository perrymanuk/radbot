"""Encryption helpers for the credential store.

Uses Fernet symmetric encryption with PBKDF2 key derivation.
Each credential gets a unique random salt so that even with a shared
master key, derived keys differ per credential.
"""

import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 480_000


def derive_key(master_key: str, salt: bytes) -> bytes:
    """Derive a Fernet-compatible key from *master_key* and *salt*.

    Args:
        master_key: The master key string (typically from RADBOT_CREDENTIAL_KEY).
        salt: A random 16-byte salt unique to each credential.

    Returns:
        A 32-byte URL-safe base64-encoded key suitable for ``Fernet()``.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    derived = kdf.derive(master_key.encode("utf-8"))
    return base64.urlsafe_b64encode(derived)


def encrypt(plaintext: str, master_key: str) -> tuple[bytes, bytes]:
    """Encrypt *plaintext* and return ``(ciphertext, salt)``.

    A fresh 16-byte salt is generated for each call.
    """
    salt = os.urandom(16)
    key = derive_key(master_key, salt)
    token = Fernet(key).encrypt(plaintext.encode("utf-8"))
    return token, salt


def decrypt(ciphertext: bytes, salt: bytes, master_key: str) -> str:
    """Decrypt *ciphertext* using *salt* and *master_key*.

    Raises:
        cryptography.fernet.InvalidToken: If the key is wrong or data is corrupt.
    """
    key = derive_key(master_key, salt)
    return Fernet(key).decrypt(ciphertext).decode("utf-8")

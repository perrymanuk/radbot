"""Encrypted credential store for Radbot.

Stores credentials (OAuth tokens, API keys, service account JSON) encrypted
in PostgreSQL using Fernet symmetric encryption with per-credential salts.
"""

from radbot.credentials.store import CredentialStore

__all__ = ["CredentialStore"]

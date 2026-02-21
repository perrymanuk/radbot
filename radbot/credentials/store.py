"""Encrypted credential store backed by PostgreSQL.

Usage::

    from radbot.credentials.store import CredentialStore

    store = CredentialStore()
    store.set("gmail_token_default", token_json, credential_type="oauth_token")
    token_json = store.get("gmail_token_default")
    store.delete("gmail_token_default")
    store.list()  # [{name, credential_type, description, updated_at}, ...]
"""

import logging
import os
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras

from radbot.credentials.crypto import decrypt, encrypt
from radbot.tools.todo.db.connection import get_db_connection, get_db_cursor

logger = logging.getLogger(__name__)

_ENV_KEY = "RADBOT_CREDENTIAL_KEY"

# Singleton instance
_instance: Optional["CredentialStore"] = None


class CredentialStore:
    """Encrypted credential CRUD against the ``radbot_credentials`` table."""

    def __init__(self, master_key: Optional[str] = None):
        self._master_key = master_key or os.environ.get(_ENV_KEY, "")
        if not self._master_key:
            # Fall back to config.yaml credential_key
            try:
                from radbot.config.config_loader import config_loader

                self._master_key = (
                    config_loader.get_config().get("credential_key") or ""
                )
            except Exception:
                pass
        if not self._master_key:
            logger.warning(
                "RADBOT_CREDENTIAL_KEY not set — credential store will be unavailable"
            )

    @property
    def available(self) -> bool:
        """True when the master key is configured."""
        return bool(self._master_key)

    # ------------------------------------------------------------------
    # Schema initialisation
    # ------------------------------------------------------------------
    @staticmethod
    def init_schema() -> None:
        """Create the ``radbot_credentials`` table if it does not exist."""
        try:
            with get_db_connection() as conn:
                with get_db_cursor(conn, commit=True) as cur:
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE table_name = 'radbot_credentials'
                        );
                    """)
                    if not cur.fetchone()[0]:
                        logger.info("Creating radbot_credentials table")
                        cur.execute("""
                            CREATE TABLE radbot_credentials (
                                name        VARCHAR(255) PRIMARY KEY,
                                encrypted_value TEXT     NOT NULL,
                                salt        BYTEA        NOT NULL,
                                credential_type VARCHAR(50) NOT NULL,
                                description TEXT,
                                created_at  TIMESTAMPTZ  DEFAULT CURRENT_TIMESTAMP,
                                updated_at  TIMESTAMPTZ  DEFAULT CURRENT_TIMESTAMP
                            );
                        """)
                        logger.info("radbot_credentials table created")
                    else:
                        logger.info("radbot_credentials table already exists")
        except Exception as e:
            logger.error(f"Error creating credential schema: {e}")
            raise

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def set(
        self,
        name: str,
        value: str,
        credential_type: str = "api_key",
        description: Optional[str] = None,
    ) -> None:
        """Store (or update) a credential."""
        if not self.available:
            raise RuntimeError(
                "Credential store unavailable — RADBOT_CREDENTIAL_KEY not set"
            )

        ciphertext, salt = encrypt(value, self._master_key)

        sql = """
            INSERT INTO radbot_credentials
                (name, encrypted_value, salt, credential_type, description, updated_at)
            VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO UPDATE SET
                encrypted_value = EXCLUDED.encrypted_value,
                salt            = EXCLUDED.salt,
                credential_type = EXCLUDED.credential_type,
                description     = COALESCE(EXCLUDED.description, radbot_credentials.description),
                updated_at      = CURRENT_TIMESTAMP;
        """
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cur:
                cur.execute(
                    sql,
                    (
                        name,
                        ciphertext.decode("utf-8"),
                        salt,
                        credential_type,
                        description,
                    ),
                )
        logger.info(f"Stored credential '{name}' (type={credential_type})")

    def get(self, name: str) -> Optional[str]:
        """Retrieve and decrypt a credential.  Returns ``None`` if not found."""
        if not self.available:
            return None

        sql = "SELECT encrypted_value, salt FROM radbot_credentials WHERE name = %s;"
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (name,))
                    row = cur.fetchone()
                    if not row:
                        return None
                    ciphertext_str, salt_memview = row
                    salt = bytes(salt_memview)
                    return decrypt(
                        ciphertext_str.encode("utf-8"), salt, self._master_key
                    )
        except Exception as e:
            # Distinguish decryption failures from DB errors
            from cryptography.fernet import InvalidToken

            if isinstance(e, InvalidToken):
                logger.error(
                    f"Failed to decrypt credential '{name}' — "
                    "master key may have changed"
                )
            else:
                logger.error(f"Error retrieving credential '{name}': {e}")
            return None

    def delete(self, name: str) -> bool:
        """Delete a credential.  Returns ``True`` if a row was deleted."""
        sql = "DELETE FROM radbot_credentials WHERE name = %s RETURNING name;"
        with get_db_connection() as conn:
            with get_db_cursor(conn, commit=True) as cur:
                cur.execute(sql, (name,))
                deleted = cur.rowcount > 0
        if deleted:
            logger.info(f"Deleted credential '{name}'")
        return deleted

    def list(self) -> List[Dict[str, Any]]:
        """List stored credentials (metadata only — no values)."""
        sql = """
            SELECT name, credential_type, description, updated_at
            FROM radbot_credentials
            ORDER BY name;
        """
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql)
                return [dict(row) for row in cur.fetchall()]


def get_credential_store() -> CredentialStore:
    """Return the singleton ``CredentialStore`` instance."""
    global _instance
    if _instance is None:
        _instance = CredentialStore()
    return _instance

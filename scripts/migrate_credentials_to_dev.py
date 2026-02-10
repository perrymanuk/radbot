#!/usr/bin/env python3
"""One-off script to copy and re-encrypt credentials from a production DB to a dev DB.

Usage:
    uv run python scripts/migrate_credentials_to_dev.py \
        --prod-db radbot_todos --dev-db radbot_dev \
        --prod-key '<prod_credential_key>' \
        [--dev-key '<dev_credential_key>']

If --dev-key is omitted a new Fernet-compatible key is generated and printed.
"""

import argparse
import base64
import os
import sys

import psycopg2
import psycopg2.extras
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# ---------------------------------------------------------------------------
# Crypto helpers (duplicated from radbot/credentials/crypto.py so this script
# is fully standalone and doesn't need the radbot package on sys.path)
# ---------------------------------------------------------------------------
PBKDF2_ITERATIONS = 480_000


def derive_key(master_key: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    derived = kdf.derive(master_key.encode("utf-8"))
    return base64.urlsafe_b64encode(derived)


def decrypt(ciphertext: bytes, salt: bytes, master_key: str) -> str:
    key = derive_key(master_key, salt)
    return Fernet(key).decrypt(ciphertext).decode("utf-8")


def encrypt(plaintext: str, master_key: str) -> tuple:
    salt = os.urandom(16)
    key = derive_key(master_key, salt)
    token = Fernet(key).encrypt(plaintext.encode("utf-8"))
    return token, salt


# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS radbot_credentials (
    name            VARCHAR(255) PRIMARY KEY,
    encrypted_value TEXT         NOT NULL,
    salt            BYTEA        NOT NULL,
    credential_type VARCHAR(50)  NOT NULL,
    description     TEXT,
    created_at      TIMESTAMPTZ  DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ  DEFAULT CURRENT_TIMESTAMP
);
"""

UPSERT_SQL = """
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


def main():
    parser = argparse.ArgumentParser(description="Migrate credentials from prod to dev DB")
    parser.add_argument("--prod-db", required=True, help="Production database name")
    parser.add_argument("--dev-db", required=True, help="Development database name")
    parser.add_argument("--prod-key", required=True, help="Production credential_key")
    parser.add_argument("--dev-key", default=None, help="Dev credential_key (generated if omitted)")
    parser.add_argument("--host", default=os.getenv("POSTGRES_HOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("POSTGRES_PORT", "5432")))
    parser.add_argument("--user", default=os.getenv("POSTGRES_USER", "postgres"))
    parser.add_argument("--password", default=os.getenv("POSTGRES_PASSWORD", ""))
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without writing")
    args = parser.parse_args()

    dev_key = args.dev_key
    if not dev_key:
        dev_key = Fernet.generate_key().decode("utf-8")
        print(f"\n  Generated new dev credential_key:\n  {dev_key}\n")

    # --- Read from prod ---
    conn_prod = psycopg2.connect(
        host=args.host, port=args.port, user=args.user,
        password=args.password, dbname=args.prod_db,
    )
    with conn_prod.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT name, encrypted_value, salt, credential_type, description "
            "FROM radbot_credentials ORDER BY name"
        )
        rows = cur.fetchall()
    conn_prod.close()

    if not rows:
        print("No credentials found in production database.")
        return

    print(f"Found {len(rows)} credential(s) in {args.prod_db}:")
    for row in rows:
        print(f"  - {row['name']} (type={row['credential_type']})")

    # --- Decrypt with prod key, re-encrypt with dev key ---
    migrated = []
    for row in rows:
        name = row["name"]
        ciphertext = row["encrypted_value"].encode("utf-8")
        salt = bytes(row["salt"])
        try:
            plaintext = decrypt(ciphertext, salt, args.prod_key)
        except Exception as e:
            print(f"  WARNING: Failed to decrypt '{name}': {e} — skipping")
            continue

        new_ciphertext, new_salt = encrypt(plaintext, dev_key)
        migrated.append({
            "name": name,
            "encrypted_value": new_ciphertext.decode("utf-8"),
            "salt": new_salt,
            "credential_type": row["credential_type"],
            "description": row["description"],
        })

    print(f"\nSuccessfully re-encrypted {len(migrated)} credential(s).")

    if args.dry_run:
        print("Dry run — not writing to dev database.")
        return

    # --- Write to dev ---
    conn_dev = psycopg2.connect(
        host=args.host, port=args.port, user=args.user,
        password=args.password, dbname=args.dev_db,
    )
    with conn_dev.cursor() as cur:
        cur.execute(CREATE_TABLE_SQL)
        for cred in migrated:
            cur.execute(UPSERT_SQL, (
                cred["name"],
                cred["encrypted_value"],
                cred["salt"],
                cred["credential_type"],
                cred["description"],
            ))
    conn_dev.commit()
    conn_dev.close()

    print(f"Wrote {len(migrated)} credential(s) to {args.dev_db}.")
    print(f"\nPut this in your config.dev.yaml as credential_key:")
    print(f"  {dev_key}")


if __name__ == "__main__":
    main()

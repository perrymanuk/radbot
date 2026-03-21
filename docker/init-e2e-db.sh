#!/bin/bash
# Create the e2e database if it doesn't exist.
# Mounted as a Postgres init script in docker-compose.e2e.yml.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    SELECT 'CREATE DATABASE radbot_e2e OWNER $POSTGRES_USER'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'radbot_e2e')\gexec
EOSQL

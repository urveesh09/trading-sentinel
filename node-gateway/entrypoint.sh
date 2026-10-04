#!/bin/sh
set -e

# Runs as root.
# Make /data world-writable so both node-gateway (appuser) and python-engine
# (quantuser) can create their own files on the shared volume without conflicts.
mkdir -p /data
chmod 777 /data

# Fix ownership of OUR OWN files only — never touch the whole directory with -R.
# A global 'chown -R' would steal python-engine's cache.db ownership, causing
# SQLITE_READONLY in that container. Silently ignore if files don't exist yet.
# WAL/SHM files are included: images before the shared uid 1000 created them
# as uid 100, which the new appuser could not write.
for db in signals.db app.db; do
  chown appuser:appgroup "/data/$db" "/data/$db-wal" "/data/$db-shm" 2>/dev/null || true
done
# Shared cache.db: same uid as python-engine, so repairing its WAL/SHM here only
# matters when this container starts first after an older image ran.
chown appuser:appgroup /data/cache.db-wal /data/cache.db-shm 2>/dev/null || true

exec su-exec appuser "$@"

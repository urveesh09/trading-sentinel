#!/bin/bash
set -e

# Ensure volume mount exists.
mkdir -p /data

# Make /data world-writable so both containers can create their own files.
# Do NOT use 'chown -R' on the whole directory — that would steal node-gateway's
# signals.db/app.db ownership, causing SQLITE_READONLY in that container.
chmod 777 /data

# Fix ownership of OUR OWN database and its WAL/SHM files (node-gateway also
# writes cache.db under the same uid 1000; older images created them as uid
# 100). Silently ignore files that don't exist yet.
chown quantuser:quantuser /data/cache.db /data/cache.db-wal /data/cache.db-shm 2>/dev/null || true

if ! su -s /bin/bash quantuser -c 'touch /data/.write_test && rm -f /data/.write_test'; then
    echo "ERROR: /data is not writable even after permission repair"
    exit 1
fi

# Drop privileges for the app process.
exec gosu quantuser "$@"

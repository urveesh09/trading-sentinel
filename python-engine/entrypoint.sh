#!/bin/bash
set -e

# Ensure volume mount exists.
mkdir -p /data

# Make /data world-writable so both containers can create their own files.
# Do NOT use 'chown -R' on the whole directory — that would steal node-gateway's
# signals.db/app.db ownership, causing SQLITE_READONLY in that container.
chmod 777 /data

# Fix ownership of OUR OWN file only. Silently ignore if it doesn't exist yet
# (it will be created with correct ownership after the gosu privilege drop).
chown quantuser:quantuser /data/cache.db 2>/dev/null || true

if ! su -s /bin/bash quantuser -c 'touch /data/.write_test && rm -f /data/.write_test'; then
    echo "ERROR: /data is not writable even after permission repair"
    exit 1
fi

# Drop privileges for the app process.
exec gosu quantuser "$@"

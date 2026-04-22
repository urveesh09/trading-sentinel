#!/bin/bash
set -e

# Ensure volume mount exists, then repair ownership/permissions if needed.
mkdir -p /data

# Chown can fail on some non-local volume drivers; fall back to permissive mode.
chown -R quantuser:quantuser /data 2>/dev/null || true
# Always make /data world-writable so other containers sharing the volume (e.g. node-gateway)
# can also write to it, regardless of which container started first.
chmod 777 /data

if ! su -s /bin/bash quantuser -c 'touch /data/.write_test && rm -f /data/.write_test'; then
    echo "ERROR: /data is not writable even after permission repair"
    exit 1
fi

# Drop privileges for the app process.
exec gosu quantuser "$@"

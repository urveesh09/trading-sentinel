#!/bin/bash
set -e

# Ensure volume mount exists, then repair ownership/permissions if needed.
mkdir -p /data

# Chown can fail on some non-local volume drivers; fall back to permissive mode.
chown -R quantuser:quantuser /data 2>/dev/null || chmod -R 0777 /data

if ! su -s /bin/bash quantuser -c 'touch /data/.write_test && rm -f /data/.write_test'; then
    echo "ERROR: /data is not writable even after permission repair"
    exit 1
fi

# Drop privileges for the app process.
exec gosu quantuser "$@"

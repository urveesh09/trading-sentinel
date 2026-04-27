#!/bin/sh
set -e

# Runs as root. Fix /data permissions so all containers sharing the
# trading_data volume can write to it regardless of which started first.
# -R ensures any pre-existing SQLite files (owned by root from a prior run)
# are re-owned before the privilege drop — prevents SQLITE_READONLY on restart.
mkdir -p /data
chown -R appuser:appgroup /data
chmod 755 /data

exec su-exec appuser "$@"

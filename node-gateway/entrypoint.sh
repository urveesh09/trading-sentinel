#!/bin/sh
set -e

# Runs as root. Fix /data permissions so all containers sharing the
# trading_data volume can write to it regardless of which started first.
mkdir -p /data
chown appuser:appgroup /data
chmod 777 /data

exec su-exec appuser "$@"

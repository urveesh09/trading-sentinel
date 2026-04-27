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
chown appuser:appgroup /data/signals.db /data/app.db 2>/dev/null || true

exec su-exec appuser "$@"

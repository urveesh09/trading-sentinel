#!/bin/bash
set -e

# Ensure the /data directory exists and test writability
# This handles cases where a volume mount has different owner permissions
if [ ! -d /data ]; then
    echo "ERROR: /data directory does not exist"
    exit 1
fi

# Test if we can write to /data by touching a test file
if ! touch /data/.write_test 2>/dev/null; then
    echo "ERROR: /data is not writable by quantuser. Run on host:"
    echo "  docker run --rm -v trading_data:/data alpine chmod 777 /data"
    exit 1
fi
rm -f /data/.write_test

# Execute the main command
exec "$@"

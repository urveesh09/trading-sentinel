#!/bin/bash
# Smoke test for the engine → OCI relay → Kite path.
# Engine runs in Docker (see entrypoint.sh), so we exec into it.
# If you ever run engine bare-metal, swap the docker exec line for: source .env && python3 -c '...'

set -e
cd "$(dirname "$0")"

# 1. From the HOST (sanity, mirrors what curl proved earlier)
echo "[1/2] host → relay sanity:"
curl -s -m 5 -o /dev/null -w "  status=%{http_code} time=%{time_total}s\n" \
  "${KITE_BASE_URL:-http://161.118.160.180:31527}/"

# 2. From inside the engine container (the real code path)
echo "[2/2] engine container → relay:"
CONTAINER=$(docker ps --filter 'ancestor=' --format '{{.Names}}' 2>/dev/null | head -1)
if [ -z "$CONTAINER" ]; then
  CONTAINER=$(docker ps --format '{{.Names}}' | grep -iE 'engine|python|sentinel' | head -1)
fi

if [ -z "$CONTAINER" ]; then
  echo "  no engine container running — start it and re-run, or test the host path above only"
  exit 0
fi

docker exec -e KITE_BASE_URL="${KITE_BASE_URL:-http://161.118.160.180:31527}" \
  "$CONTAINER" python3 -c '
import asyncio, os, httpx
async def go():
    async with httpx.AsyncClient(base_url=os.environ["KITE_BASE_URL"], timeout=10) as c:
        r = await c.get("/")
        print(f"  status={r.status_code} body={r.text[:60]!r}")
asyncio.run(go())
'

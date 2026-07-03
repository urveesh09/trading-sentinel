# 2026-07-03 — Nginx 502 on /api/auth/login (stale Docker DNS cache)

## Symptom
After a `node-gateway` container restart (during penny-edge deployment round), all requests via the ngrok URL returned HTTP 502:
```
connect() failed (111: Connection refused) while connecting to upstream,
upstream: "http://172.18.0.2:3000/api/auth/login"
```
Health checks from inside the gateway itself worked fine. nginx → node-gateway by name (node-gateway:3000) returned 200 from inside the nginx container. Only external traffic via the IP was broken.

## Root cause
Static `proxy_pass http://node-gateway:3000;` resolves DNS exactly once at nginx config load. Docker's internal DNS at 127.0.0.11 had returned 172.18.0.2 for `node-gateway` at the time nginx started. After the gateway container was recreated, docker assigned it 172.18.0.3, but nginx kept sending traffic to 172.18.0.2 → ECONNREFUSED → 502.

## Fix
Two changes to `node-gateway/nginx/nginx.conf`:
1. Added `resolver 127.0.0.11 ipv6=off valid=10s;` at top level.
2. Wrapped the upstream in a named block — only the named-upstream form actually uses the resolver directive:
   ```
   upstream node_gateway_upstream {
       zone node_gateway 64k;
       server node-gateway:3000 max_fails=3 fail_timeout=10s;
       keepalive 16;
   }
   ```
   and changed `proxy_pass http://node-gateway:3000;` → `proxy_pass http://node_gateway_upstream;`.
3. Added `proxy_next_upstream error timeout invalid_header http_502 http_503 http_504;` as a safety net.

Deployed with `docker compose restart nginx` (no full stack restart, no downtime on python-engine / agent).

## Verification
- `GET /api/health` through nginx: 200 OK with `python_engine: reachable, uptime_seconds: 109`
- `GET /api/auth/login` through nginx: 302 Found (was 502 before)
- nginx access log shows clean 200/302, no further `connect() failed` entries

## Gotcha
The production Docker stack is bind-mounted from `/home/urveesh/Desktop/trading-sentinel/` NOT `/home/urveesh/trading-sentinel/`. Editing the wrong path silently no-ops. Always edit from the Desktop path or from inside the container.

## Recipe for next time
1. `docker compose restart nginx` (5s of 502 risk on external traffic; gateway/python stay up)
2. Verify with `docker logs quant_nginx --since 30s | grep -E "connect|error"`
3. If error lines persist: `docker exec node-gateway hostname -i` to see current IP, `docker exec quant_nginx getent hosts node-gateway` to see what nginx resolves to, and check for `proxy_pass` lines that bypass the named upstream.

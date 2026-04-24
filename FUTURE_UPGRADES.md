# Future Upgrade Backlog — Trading Sentinel V2.0

Items deferred from the April 2026 audit. These are real issues but not blocking
current trading. Address before scaling capital or deploying to a second account.

---

## 🔴 Security (Do before going beyond ₹50k bankroll)

### CRIT-004 — nginx rate limiting is disabled
File: `node-gateway/nginx/nginx.conf`  
Fix: Uncomment `limit_req zone=api_limit burst=10 nodelay;` inside the `location /` block.

### CRIT-005 — No HTTPS
File: `node-gateway/nginx/nginx.conf`  
Fix: Add a second `server {}` block listening on port 443 with SSL cert (Let's Encrypt via certbot).
Add HTTP→HTTPS redirect. Re-enable `hsts` in `security.js` and remove `upgradeInsecureRequests: null`.
GCP alternative: Terminate TLS at the GCP Load Balancer level before nginx.

### HIGH-001 — `INTERNAL_API_SECRET` defaults to empty string
File: `python-engine/config.py`  
Fix: Change `INTERNAL_API_SECRET: str = ""` to `INTERNAL_API_SECRET: str` (no default, Pydantic will
require it from .env). Add `@field_validator` to reject empty-string values.

### HIGH-002 — `/token` endpoint in Container B has no authentication
File: `python-engine/main.py` (`inject_token()`)  
Fix: Add the same `X-Internal-Secret` check as other internal endpoints before calling `kite.set_token()`.

### HIGH-004 — No Docker health checks
File: `docker-compose.yml`  
Fix: Add `healthcheck:` blocks to each service so Docker can auto-restart truly broken containers.
Example for python-engine:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
```

### MED-011 — `X-Internal-Secret` header not sanitized in logs
File: `node-gateway/server/middleware/logger.js`  
Fix: In pino-http custom serializer, also sanitize `req.headers` using `sanitise()`.

---

## 🟠 Correctness

### HIGH-007 — Momentum execute uses live data, not approved signal data
Files: `node-gateway/server/index.js` (EM handler), `agent/agent.py`  
Issue: When user clicks Execute on a momentum Telegram button, Container A re-fetches
the signal live from Container B. If the screener ran again in the 40-minute window
(Container B scans at :00/:15/:30/:45, Container C alerts at :55), the signal data
can have different entry price, shares, or stop_loss than what was displayed to the user.  
Fix: Container C should POST the signal data to a Container A internal endpoint
(`/api/internal/register-momentum`) before sending the Telegram alert. The EM handler
then reads from DB instead of doing a live fetch.

### HIGH-008 — `MomentumSignal.shares` missing `Field(ge=1)` validator
File: `python-engine/models.py`  
Fix: Change `shares: int` → `shares: int = Field(ge=1)` in the `MomentumSignal` model,
consistent with `Signal.shares: int = Field(ge=1)`.

### HIGH-010 — `is_trading_day()` falls back silently on NSE API failure
File: `python-engine/market_calendar.py`  
Issue: If the NSE API is unreachable AND the holidays table is empty (fresh DB),
`is_trading_day()` returns `True` for all weekdays including NSE holidays. No alert sent.  
Fix: On fallback, send a Telegram warning: "Holiday DB empty and NSE API unreachable —
running with weekday-only check. Verify manually."

---

## 🟡 Code Quality / Minor

### MED-002 — Dual Telegram notification sources
Files: `python-engine/main.py` (`notify_screener_results`) and `agent/agent.py`  
Issue: User receives 2 messages per scan cycle — plain text from Container B and
AI-enriched from Container C. The Container B message has no buttons; the Container C
message has working buttons. Consider removing the Container B plain-text summary
and letting Container C be the sole alert path, or merging them.

### MED-004 — `retry.js` has no exponential backoff or error type discrimination
File: `node-gateway/server/utils/retry.js`  
Fix: Add exponential backoff (`delay * 2^attempt`) and skip retry for 4xx errors
(non-retryable), retry only on network errors and 5xx responses.

### MED-005 — Two internal auth schemes (X-Internal-Secret vs Authorization Bearer)
Files: `node-gateway/server/middleware/auth.js` and `security.js`  
Fix: Standardise on `X-Internal-Secret` header for all internal routes. Remove the
`verifyInternalApi` Bearer-token variant from security.js (currently used by token.js only).

### MED-006 — `/circuit-breaker/reset` proxied but not implemented in Container B
Files: `node-gateway/server/routes/proxy.js`, `python-engine/main.py`  
Fix: Add `@app.post("/circuit-breaker/reset")` endpoint in main.py that clears the
circuit breaker state from the `bankroll_ledger` table.

### MED-007 — `/rejected` endpoint always returns empty array
File: `python-engine/main.py`  
Fix: Change `return {"data": []}` to `return {"data": rejected_signals}` (serve the
state-locked `rejected_signals` global, same pattern as `/signals`).

### MED-010 — `/token/invalidate` on logout returns 404 from Container B
File: `node-gateway/server/routes/auth.js` (logout handler)  
Fix: Add `@app.post("/token/invalidate")` to Container B that calls `kite.invalidate_token()`
and clears the `access_token` field.

### LOW-001 — `TOKEN_INJECTION_SECRET` is dead config
File: `python-engine/config.py`  
Status: The field has been commented out in the April 2026 fix. No further action needed.

### LOW-003 — `/health` endpoint in Container B returns minimal response
File: `python-engine/main.py`  
Fix: Expand the `/health` response to include `market_regime`, `scheduler_running`,
`kite_connected`, and `circuit_breaker_status` fields.

### LOW-006 — No independent trading-day check in Container C
File: `agent/agent.py`  
Fix: Import `is_trading_day()` logic (or a lightweight holiday check) so Container C
skips all pipeline work on NSE holidays without relying on Container B to return empty signals.

---

*Last updated: April 2026 audit. Reviewed by: CODE_AUDITOR agent.*

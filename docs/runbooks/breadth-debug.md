# Breadth Enrichment -- Operator Runbook

**Audience:** Whoever is on-call when the bot starts behaving strangely.
**Spec:** `docs/superpowers/specs/2026-06-14-breadth-enrichment-design.md`
**Plan:** `docs/superpowers/plans/2026-06-14-breadth-enrichment.md`
**Branch:** `evolve/smart-strategies` (Tasks 1-7 done; Tasks 8-10 in progress)

## What this feature does

Computes real market breadth (% of Nifty 100 stocks above their 50-day SMA)
hourly (Tier 1, cached 1 h) and refreshes the per-stock rank every scan
(Tier 2, live LTP). The system uses breadth to:

- Give a +15 / +7 / -10 score bonus to stocks in the top 20% / top 40% /
  bottom 20% of the breadth distribution. Works in all regimes (R1/R2/R3).
- Apply a 1.2x score multiplier to top-quintile stocks (pushes borderline
  signals above the score threshold).
- In R1 (normal) regime, when breadth is below 40%, only allow entry into
  top-quintile stocks (narrow-rally gate). Top quintile is exempted.

Tier 1 = hourly batch fetch (100 Nifty 100 tokens x 60-day history).
Tier 2 = per-scan rank refresh using the LTPs already in the scan cache
(zero extra Kite calls).

## Quick diagnostics

### "Breadth is degraded" warning in logs

**Symptom:** `breadth_tier1_degraded reason=tier1 fetch failures exceeded
threshold n_resolved=<N>` OR `breadth_tier2_degraded n_resolved=<N>`.

**What it means:** Tier 1 or Tier 2 failed on >10% of Nifty 100 fetches.
The system falls back to regime-only filtering (no bonus, no multiplier, no
narrow-rally gate -- `evaluate_signal` runs as if pre-breadth).

**How to check (on Oracle VM or wherever python-engine runs):**
```bash
# 1. Confirm degraded state
docker logs python-engine 2>&1 | grep -i "breadth" | tail -20
# OR if running directly:
tail -200 /var/log/python-engine.log | grep -i "breadth" | tail -20

# 2. Test Kite historical endpoint directly (relay URL is the OCI VM)
curl -H "Authorization: token $KITE_API_KEY:$KITE_ACCESS_TOKEN" \
  "https://api.kite.trade/instruments/historical/256265/day?from=2026-04-15&to=2026-06-14"
```

**Common causes:**
- Kite API rate limit hit (3 req/s). Tier 1 fires 100 fetches with
  `BREADTH_TIER1_PARALLELISM=4` default -> ~25s burst, well within limits,
  but if the bot restarted mid-fetch you may catch a stale burst.
  -> Wait 60s, retry.
- Kite historical endpoint down. -> Check status.kite.trade.
- Access token expired. -> Re-login via the OCI ngrok flow (see
  `docs/runbooks/zerodha-auth.md` if it exists, otherwise the daily
  ritual in the user's notes).
- `nifty100.json` has stale symbols (Kite instrument cache not refreshed).
  -> Run the instrument-cache refresh (search `kite_client.py` for the
  refresh function, e.g. `kite.refresh_instruments()`).
- OCI relay (`aiohttp` on `:31527`) is down. -> Check
  `ss -tlnp | grep 31527` on the OCI VM, restart the relay container.

**Recovery:** Setting `BREADTH_ENRICHMENT_ENABLED=False` in `.env` disables
the feature and returns the system to pre-breadth behaviour. Restart the
python-engine container after the change.

### "Too few signals firing" complaint

**Symptom:** Signal count drops more than 20% vs. pre-breadth baseline.

**What it means:** The R1 narrow-rally gate is rejecting more signals than
expected.

**How to check:** Look at scan logs for `narrow_rally_filtered` rejections
and the rejected-signals list returned by `/signals`:
```bash
docker logs python-engine 2>&1 | grep "narrow_rally_filtered" | tail -20
curl -s http://localhost:8000/signals | jq '.rejected_signals[] | select(.reject_reason=="narrow_rally_filtered")'
```

**Tuning:** If too aggressive, raise `BREADTH_NARROW_RALLY_THRESHOLD`
(default `0.40`) toward `0.30` (more permissive) in `.env`. If still too
aggressive, raise `BREADTH_NARROW_GATE_EXEMPT_RANK` (default `0.80`) toward
`0.70` (broader exemption).

**Rollback:** Set `BREADTH_ENRICHMENT_ENABLED=False` in `.env` and restart.

### "Score feels inflated" complaint

**Symptom:** Win rate is up but R-multiples are down (taking more trades,
smaller winners). The 1.2x multiplier is pushing borderline signals above
`MIN_SIGNAL_SCORE` more than expected.

**How to check:** Look at top-quintile signal scores in scan logs and
compare to pre-breadth baseline. Specifically, look for signals where
`score` was just below threshold pre-breadth and is now above.

**Tuning:** Lower `BREADTH_RANK_MULTIPLIER` (default `1.2`) toward `1.1`
in `.env`. Setting it to `1.0` disables the multiplier while keeping the
+15 base bonus.

### "Tier 2 says stale"

**Symptom:** `breadth_tier2_stale=True` in some log lines.

**What it means:** Tier 1 cache expired and Tier 2 had to re-run from
scratch. Normally this is fine -- Tier 1 is stale-while-revalidate.
It only matters if you see this firing on every scan (i.e., Tier 1 is
never landing within the TTL window).

**How to check:** Count stale events:
```bash
docker logs python-engine 2>&1 | grep -c "breadth_tier2_stale"
```

**Tuning:** If firing on every scan, increase `BREADTH_CACHE_TTL_SECONDS`
(default `3600`) to e.g. `7200`. Or decrease scan frequency so each scan
sees a fresh Tier 1.

## Feature flag reference

All settings are defined in `python-engine/config.py` and can be
overridden via `.env`. The `BREADTH_ENRICHMENT_ENABLED` flag is the kill
switch -- set it to `False` for instant revert with no code rollback.

| Env var                                | Default | What it does                                          |
|----------------------------------------|---------|-------------------------------------------------------|
| `BREADTH_ENRICHMENT_ENABLED`           | `False` | Master kill switch. `False` = no behaviour change     |
| `BREADTH_UNIVERSE`                     | `NIFTY100` | Universe identifier (reserved for future multi-universe support) |
| `BREADTH_CACHE_TTL_SECONDS`            | `3600`  | Tier 1 stale-while-revalidate window (1 hour)         |
| `BREADTH_FETCH_TIMEOUT_SECONDS`        | `90`    | Max time for one Tier 1 fetch                         |
| `BREADTH_NARROW_RALLY_THRESHOLD`       | `0.40`  | R1 gate fires below this breadth %                    |
| `BREADTH_NARROW_GATE_EXEMPT_RANK`      | `0.80`  | Top quintile bypasses R1 gate                         |
| `BREADTH_RANK_BONUS_TOP`               | `15`    | +15 to top 20% of breadth distribution                |
| `BREADTH_RANK_BONUS_MID`               | `7`     | +7 to top 40%                                         |
| `BREADTH_RANK_PENALTY_BOTTOM`          | `-10`   | -10 to bottom 20%                                     |
| `BREADTH_RANK_MULTIPLIER`              | `1.2`   | Top quintile score x this                             |
| `BREADTH_DATA_DEGRADED_THRESHOLD`      | `0.10`  | >10% fetch failures = degraded path                   |
| `BREADTH_TIER1_PARALLELISM`            | `4`     | Concurrent Kite historical fetches (Tier 1)            |
| `BREADTH_DATA_DIR`                     | `data`  | Path (relative to `python-engine/`) to `nifty100.json` |

### Changing a setting

```bash
# 1. Edit .env (NOT config.py -- env vars override defaults at runtime)
echo "BREADTH_NARROW_RALLY_THRESHOLD=0.35" >> python-engine/.env

# 2. Restart python-engine (no systemd per user preference -- SSH+restart)
ssh oracle-vm "docker restart python-engine"

# 3. Verify
ssh oracle-vm "docker logs python-engine --tail 30 | grep -i 'breadth'"
```

## Architectural notes for new operators

- **Why two tiers?** Tier 1 is the expensive batch (100 Nifty 100
  fetches). We cache it for 1 hour. Tier 2 only needs the live LTP
  (already in the scan cache from the universe pass), so it costs zero
  extra Kite calls per scan -- only the rank recompute.
- **Why the narrow-rally gate only in R1?** R1 (normal) is when narrow
  rallies are most likely to fool the trend filter. In R2/R3 the system
  is already cautious via other mechanisms (RS filter in R2, etc.).
- **Why top-quintile exempt from the gate?** When 90%+ of Nifty 100 is
  below SMA50, the few survivors are statistically the best risk-on names.
  Letting them in is the whole point of the gate.
- **Why the 1.2x multiplier?** In backtests, top-quintile stocks that
  almost-pass the score threshold (say 50/60) had a higher win rate
  than the median. The multiplier nudges them over the line.

## Rollout checklist

- [x] **Stage 0 (current default):** `BREADTH_ENRICHMENT_ENABLED=False`.
  Code is shipped; the engine is built but the gate never fires and the
  bonus/multiplier never apply. Run 1 week. Confirm scan logs show
  `breadth_engine_enabled` (once) and `breadth_tier1_degraded=False`
  (every scan). No signal-flow change.
- [ ] **Stage 1:** `BREADTH_ENRICHMENT_ENABLED=True`. Run 1 week. Monitor:
  - Signal count delta (expect 5-20% reduction from narrow-rally filter)
  - Win rate (expect 1-3 pp improvement)
  - Breadth-degraded alerts (expect zero)
  - Tier 2 stale rate (expect <1/day)
- [ ] **Stage 2:** After 2 clean weeks, flip the default in
  `config.py:184` to `True` and remove the explicit `.env` override.

## Cross-references

- Spec: `docs/superpowers/specs/2026-06-14-breadth-enrichment-design.md`
- Plan: `docs/superpowers/plans/2026-06-14-breadth-enrichment.md`
- Settings source of truth: `python-engine/config.py` (lines 184-196)
- Engine gate logic: `python-engine/engine.py` (`narrow_rally_filtered` block)
- Engine score adjustments: `python-engine/engine.py` (`BREADTH SCORING BONUS` block)
- Wiring helpers: `python-engine/main.py` (`build_breadth_engine`, `build_breadth_kwargs`)
- Universe loader: `python-engine/universe.py`
- Two-tier breadth engine: `python-engine/breadth.py`
- Nifty 100 ticker list: `python-engine/data/nifty100.json`

## When to escalate

Open a high-priority ticket (or page the on-call) if:
- `breadth_tier1_degraded` fires on >50% of scans for 3+ hours straight
- `BREADTH_ENRICHMENT_ENABLED` is stuck on `True` but no signals have
  fired in 24 hours (the gate may be over-aggressive due to bad Nifty 100
  data -- set flag to `False` to confirm)
- Tier 2 stale rate >10/day (Tier 1 is broken)

For non-urgent tuning questions, leave the flag on and adjust thresholds
in `.env` as described above.

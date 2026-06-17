# Breadth Enrichment -- Rollout Checklist

**Audience:** Operator running Stage 0/1/2 of the breadth enrichment feature.
**Feature flag:** `BREADTH_ENRICHMENT_ENABLED` (default `False` in `python-engine/config.py:184`).
**Spec:** `docs/superpowers/specs/2026-06-14-breadth-enrichment-design.md`
**Runbook:** `docs/runbooks/breadth-debug.md`

---

## Stage 0 -- Ship with flag off (CURRENT DEFAULT)

**Goal:** Confirm the breadth engine is computing data correctly without
affecting signal flow. **Zero risk** -- the gate never fires, the bonus
and multiplier never apply.

### Pre-conditions
- [x] `BREADTH_ENRICHMENT_ENABLED=False` in `python-engine/config.py:184`
- [x] No `BREADTH_ENRICHMENT_ENABLED=True` in `python-engine/.env`
- [x] Branch `evolve/smart-strategies` merged to `main` and pulled into
  `~/Desktop/trading-sentinel` (user-controlled)
- [x] python-engine container restarted with the new code

### Monitoring (1 week)
- [ ] **No "reject_reason: narrow_rally_filtered"** in rejected signals
      (this is the proof that the gate is correctly off)
- [ ] **Signal count unchanged** vs. pre-breadth baseline (within +/-1)
- [ ] **breadth_engine_enabled** logged once at startup
- [ ] **breadth_tier1_degraded** count = 0 (or near 0)
- [ ] **breadth_tier2_degraded** count = 0
- [ ] Tier 1 fetch latency < 30 s (default parallelism=4, 100 tokens)

### Monitoring queries

```bash
# On the OCI VM, with the python-engine container running:

# 1. Confirm engine is initialised (should fire once at startup)
docker logs python-engine --since 1h 2>&1 | grep "breadth_engine_enabled"

# 2. Confirm Tier 1 is computing breadth (not degraded)
docker logs python-engine --since 1h 2>&1 | grep "breadth_tier1_degraded" | wc -l
# Expected: 0

# 3. Confirm Tier 2 is computing rank
docker logs python-engine --since 1h 2>&1 | grep "breadth_tier2_degraded" | wc -l
# Expected: 0

# 4. Confirm no narrow-rally rejections (proves the gate is off)
docker logs python-engine --since 1h 2>&1 | grep "narrow_rally_filtered" | wc -l
# Expected: 0

# 5. Signal count from /signals endpoint (compare to baseline)
curl -s http://localhost:8000/signals | jq '.signals | length'
```

### Stage 0 -> Stage 1 gate

[OK] Move to Stage 1 if, after 1 week of monitoring:
- [ ] All five monitoring queries return the expected value
- [ ] No python-engine crashes or restarts
- [ ] No `breadth_engine_init_failed` errors
- [ ] No complaints from the user about the bot

---

## Stage 1 -- Enable the feature (1 week)

**Goal:** Run the gate + bonus + multiplier in production. Watch for
unintended side effects on signal flow and win rate.

### Pre-conditions
- [ ] Stage 0 monitoring passed
- [ ] Baseline metrics recorded (signal count, win rate, avg R-multiple
      from the pre-breadth era -- should be in `performance` table)
- [ ] Quiet market week preferred (avoid earnings season or a known
      macro event that would skew the data)

### Enable

```bash
# 1. Add the override to .env
echo "BREADTH_ENRICHMENT_ENABLED=True" >> python-engine/.env

# 2. Restart python-engine
ssh oracle-vm "docker restart python-engine"

# 3. Verify
ssh oracle-vm "docker logs python-engine --tail 30 | grep -i breadth"
# Expected output: "breadth_engine_enabled" + "tier1" + "tier2" all
# computing successfully.
```

### Monitoring (1 week)

#### Hard go/no-go gates
- [ ] **No python-engine crashes.** A crash on the first scan after
      enabling would indicate a Tier 1 fetch blowing up. Roll back
      immediately (set flag back to `False`).
- [ ] **No >50% reduction in signal count.** Expected reduction is
      5-20% in narrow-rally periods. >50% means the gate is over-gating.
      Roll back or tune `BREADTH_NARROW_RALLY_THRESHOLD` from `0.40` to
      `0.30`.
- [ ] **No `breadth_tier1_degraded` alerts.** A persistent degradation
      is a Kite / relay problem, not a strategy problem. Investigate
      (see runbook "Breadth is degraded" section).
- [ ] **No consecutive days of 0 signals.** Should not happen -- the
      gate exempts top-quintile, and there are always at least 1-2
      top-quintile names.

#### Soft metrics (record, don't act on)
- [ ] **Signal count delta** vs. baseline (expect 5-20% reduction)
- [ ] **Win rate delta** vs. baseline (expect 1-3 pp improvement)
- [ ] **Avg R-multiple** vs. baseline (expect similar)
- [ ] **Top-quintile signal rate** (expect 5-15% of all signals)
- [ ] **breadth_tier2_stale rate** (expect <1/day)

### Monitoring queries

```bash
# 1. Hard gate -- no crashes
docker ps --filter "name=python-engine" --format "{{.Status}}"
# Expected: "Up X hours (healthy)"

# 2. Signal count (compare to baseline)
curl -s http://localhost:8000/signals | jq '.signals | length'

# 3. Rejection reasons -- should see narrow_rally_filtered in the mix
curl -s http://localhost:8000/signals | jq '[.rejected_signals[] | .reject_reason] | group_by(.) | map({reason: .[0], count: length}) | sort_by(.count) | reverse'

# 4. Win rate (need at least 1 week of closed trades to be meaningful)
# Use the existing /performance endpoint:
curl -s http://localhost:8000/performance | jq '{win_rate, avg_r, total_trades}'

# 5. Tier 2 stale rate
docker logs python-engine --since 1d 2>&1 | grep -c "breadth_tier2_stale"
# Expected: 0-2 per day

# 6. Top-quintile signal rate
# (counts signals where breadth_rank >= 0.80)
curl -s http://localhost:8000/signals | jq '[.signals[] | select(.breadth_rank >= 0.80)] | length'
```

### Stage 1 -> Stage 2 gate

[OK] Move to Stage 2 if, after 1 week of monitoring:
- [ ] All four hard go/no-go gates passed
- [ ] Soft metrics are within expected range (or the deviations are
      explainable by market conditions, not the feature)
- [ ] No complaints from the user

[X] Roll back to Stage 0 if:
- [ ] Any hard go/no-go gate failed
- [ ] Win rate dropped >5 pp (the feature is hurting, not helping)
- [ ] Avg R-multiple dropped >0.3 (the feature is taking lower-quality trades)

Rollback is one env-var change and a container restart -- no code rollback.

---

## Stage 2 -- Make it the default

**Goal:** Flip the default in `config.py:184` to `True` so future
deployments don't need the explicit `.env` override.

### Pre-conditions
- [ ] Stage 1 monitoring passed
- [ ] Two clean weeks of Stage 1 (no rollbacks, no degradation)

### Action

```bash
# 1. Flip the default in config.py
# Change line 184 from:
#   BREADTH_ENRICHMENT_ENABLED:         bool  = False
# To:
#   BREADTH_ENRICHMENT_ENABLED:         bool  = True

# 2. Remove the explicit override from .env (no longer needed)
sed -i '/BREADTH_ENRICHMENT_ENABLED/d' python-engine/.env

# 3. Restart python-engine
ssh oracle-vm "docker restart python-engine"

# 4. Verify
ssh oracle-vm "docker logs python-engine --tail 30 | grep -i breadth"
# Expected output: "breadth_engine_enabled" with the feature ON
```

### Post-Stage-2 monitoring (1 month)

- [ ] **No regressions** vs. Stage 1 metrics
- [ ] **Signal count** stabilises within +/-10% of the Stage 1 weekly avg
- [ ] **Win rate** trends positive (or stable if Stage 1 was already at
      the floor)
- [ ] No new "Top-of-funnel" issues (e.g. exhausted Kite rate limit,
      OOM from holding the universe in memory)

---

## Quick reference

| Stage | Flag value | .env override? | Duration | Risk |
|-------|-----------|----------------|----------|------|
| **0 (current)** | `False` (config default) | No | Indefinite | None -- code is shipped, feature is dormant |
| **1** | `True` | Yes (in `.env`) | 1 week | Low -- flag is a one-line revert |
| **2** | `True` (config default) | No | Indefinite | Normal -- fully on, no easy revert |

### Decision flowchart

```
Stage 0 healthy?
+-- No  -> Investigate (check runbook)
+-- Yes -> Move to Stage 1

Stage 1 hard gates passed?
+-- No  -> Roll back to Stage 0 (set flag = False)
+-- Yes -> Run Stage 1 for 1 more week

Two clean weeks of Stage 1?
+-- No  -> Stay in Stage 1, re-evaluate
+-- Yes -> Move to Stage 2
```

---

## When in doubt, roll back

The flag is a true kill switch. If anything looks wrong -- even if you
can't pinpoint why -- set `BREADTH_ENRICHMENT_ENABLED=False` and restart.
This reverts to the exact pre-breadth behaviour within 30 seconds.

```bash
# Quick rollback (one command)
ssh oracle-vm "sed -i 's/^BREADTH_ENRICHMENT_ENABLED=True/BREADTH_ENRICHMENT_ENABLED=False/' python-engine/.env && docker restart python-engine"
```

After rollback, open an issue with the symptom + the log snippet so we
can fix in a follow-up PR.

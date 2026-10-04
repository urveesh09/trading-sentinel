# F&O growth slice — SENSEX, capped-loss income book, smarter vehicle, adaptive risk (Dev)

Owner goal (October 4, 2026): a steady ~₹20,000/month on the ₹2.5 lakh F&O paper
pool, growing slowly; never "crazy" losses or long runs of bad days, because a
loss shrinks the capital that earns. Own cash only. The owner approved: SENSEX,
expanding the capped-loss (defined-risk) book, smarter per-trade choices, and
size that grows only when the system is winning. A small rise in the max-loss
cap is allowed.

## Problem (verified in code and data)

- Capital is ~95% idle: one NIFTY single-leg idea at a time, 1–2 lots, 4–7% of
  the pool per trade, ~0.7 trades/day; the capped-loss book trades one 1-lot
  structure intraday with a ₹10,000 ceiling.
- Entry brakes allow −₹15,000 days, −₹30,000 weeks and −₹50,000 months, which is far
  larger than the ₹20,000 monthly goal.
- On a directional signal, the naked option and the debit spread both open:
  the same idea held twice.
- SENSEX futures volume is unusable for the volume check (median 40–120
  contracts per 5-minute bar, 24% zero bars on the October contract) while
  NIFTY futures trade thousands per bar.

## Design

1. **Adaptive risk** (`fno_adaptive_risk.py`, pure, shared by live and replay):
   a risk multiplier from book evidence. It cuts to 0.5× once equity is 4% under its
   peak and to 0.25× at 8%; it rises to 1.25×, and later to 1.5×, only after ≥20 (or ≥40)
   closed trades with profit factor ≥1.3 (or ≥1.5) while equity is within 2% of
   its peak. Single-leg entries stop for the day after two losing closes
   ("two strikes"). The multiplier scales the per-trade risk budget and its
   rupee ceiling; the lot ceiling stays the hard cap.
2. **Tighter brakes:** daily 3% (₹7,500), weekly 6% (₹15,000), monthly 10%
   (₹25,000), drawdown halt 15%. Structural cap ₹30,000 → ₹40,000 (approved
   small rise). `FNO_MAX_LOTS` stays 2; `FNO_MAX_LOTS_PROVEN` = 3 applies only
   while the adaptive multiplier is above 1 (proven ×1.25–1.5).
3. **Capped-loss income book:** multi-lot structures sized by `dr_lots` as
   min(floor(₹10,000 × multiplier / max loss per lot), floor(40% of pool /
   capital per lot), 3). Capital per lot is the debit for a debit spread and
   the conservatively reserved broker margin (`FNO_DR_MARGIN_PER_LOT_RS`
   ₹50,000) for a condor. Round-trip costs now count every leg's full quantity.
   Still intraday, still target/stop fractions, still one structure at a time.
4. **Smarter vehicle (no double exposure):** on a directional signal, rich
   ATM IV (IV-rank proxy ≥ `FNO_VEHICLE_SPREAD_IV_RANK`) → debit spread only;
   otherwise → the naked option only. **Ships OFF** (`FNO_VEHICLE_BY_IV=False`):
   at normal IV it would retire the debit spreads, and no evidence yet shows
   that is better. Score it on forward sessions first.
5. **SENSEX:** trade NIFTY and SENSEX (`FNO_TRADING_UNDERLYINGS`). SENSEX uses
   its own price for the opening range, ATR and EMAs, and NIFTY futures
   relative volume as the participation proxy (declared). A correlation
   guard refuses a same-direction entry when the other index already has an
   open single-leg position. Positions are managed per underlying futures
   price; orders carry the right exchange (NFO/BFO). Caps (concurrency,
   trades/day, premium, brakes) remain shared across both underlyings.
6. **Replay:** `fno_policy_replay` sizes through the same `risk_stance`
   (multiplier and two-strike halt) and reads the new brakes/caps from
   settings. SENSEX replay is **deferred**: it needs a second read-only export
   with SENSEX futures candles (the frozen `2026-10-04-archive/_local` export
   must not change). Reruns at HEAD differ from the frozen `fno-trader-v1`
   scores because the runtime rules changed.
7. **Instrument refresh:** `fno_underlyings.refresh_all` now refreshes every
   traded underlying as well as the analytics list.

## Acceptance

- Existing F&O suite stays green except where a test pins an intentionally
  changed number (brake levels, caps), each updated deliberately.
- New tests: multiplier ladder, two-strike rule, DR multi-lot economics and
  margin ceiling, vehicle choice, SENSEX RVOL proxy, correlation guard,
  per-underlying management, exchange routing.
- Replay evidence on the archived sessions, labelled as development data
  (every archived session has now been seen); forward sessions decide.

## Rollout / rollback

Paper only; live remains disarmed. Every behaviour has a setting:
`FNO_ADAPTIVE_RISK_ENABLED`, brake levels, `FNO_DR_MAX_LOTS`,
`FNO_VEHICLE_BY_IV`, `FNO_TRADING_UNDERLYINGS`. Rollback = restore the previous
values via environment and redeploy; open positions keep their stored exits.

## Receipt (Dev only, October 4, 2026)

Implemented as designed above, with the deviations noted (vehicle OFF, SENSEX
replay deferred). Live-money limits:

- The **live** single-leg leg runs on NFO (NIFTY) only. `fno_exit_evidence` and
  `fno_exit_recovery` accept `exchange == "NFO"` only, so SENSEX is paper-only
  until those support BFO. `FNO_LIVE_BANKROLL` stays 0 (not armed).
- Shared caps (concurrency, trades/day, open premium, brakes) cover both indices.

Verification (Windows venv, `python -m pytest tests -q -p no:cacheprovider`):
commit `e8d93c3`, 4854 passed, 4 skipped, 4 failed (below). New tests:
`test_fno_adaptive_risk.py` (6), `test_fno_dr_sizing.py` (4),
`test_fno_sensex.py` (5), two orchestrator tests, one replay test and one
refresh test. Pre-existing failures, unrelated and verified on `31f84ec`:
`test_dev_acceptance_harness` (AI-outage harness), `test_integrated_dev_demo`,
`test_proactive_intelligence` demo, and `test_mark_to_market` DR writer row
(its premise predates the immutable contract-leg identity the writer now stores;
the test needs redesign, not a fixture patch).

Configuration impact: new settings listed above, all environment-overridable.
No schema migration (`fno_positions.underlying` and `fno_dr_positions.lots`
already existed). No scheduler job added.

Not evidence of profit: tests prove the rules behave as written, not that the
book earns. The archived sessions are all seen; forward paper sessions from
October 5, 2026 decide.

## Owner-requested test, Sep 17 – Oct 1, 2026 (development evidence; all sessions already seen)

Reproduce: `docs/research/fno/2026-10-04-growth-window-test/` holds the drivers
(`run_window.py ENGINE LABEL BANKROLL history|fresh OUT`, `ledger_whatif.py BANKROLL`)
and every scenario's JSON. Old rules ran from a detached worktree at `c791a38`.

Single-leg NIFTY replay (`fno_policy_replay`) on the 10 archived sessions in the
window (Sep 17, 21–25, 28–30, Oct 1; **Sep 18 is missing from the archive**).
Old rules = worktree at `c791a38`; new rules = this slice. Capped-loss and SENSEX
decisions are not replayable (no SENSEX candles; DR closes enter as history).

**Bug found and fixed by this test:** a drawdown cut (0.5×/0.25×) shrank the
risk budget below the cost of one lot (~₹2,400–3,600 of risk), so it silently
refused every trade. The paper book entered the window ₹36k below its
allocation (−14.4%) and the new rules took **0 trades**. Fix: a cut now shrinks
to one lot, never below; whether that lot fits is judged on the normal budget
(`fno_entry_plan`, `dr_lots`). Halting remains the entry brakes' job. Tests pin
it (`test_drawdown_cut_shrinks_to_one_lot_but_never_halts`, mutation-checked).

| Scenario | Trades | Net | Net excl. best | Max DD |
| --- | --- | --- | --- | --- |
| Old rules, ₹2.5L, real paper history | 10 | +₹12,054 | +₹4,947 | ₹1,991 |
| New rules, ₹2.5L, real paper history | 9 | +₹9,001 | +₹1,894 | ₹1,991 |
| New = old, fresh ₹2.5L | 10 | +₹11,577 | +₹4,470 | ₹1,991 |
| New = old, fresh ₹2.0L | 10 | +₹11,821 | +₹4,714 | ₹1,991 |
| New = old, fresh ₹1.75L | 9 | +₹9,810 | +₹2,703 | ₹1,991 |
| New = old, fresh ₹1.5L | 7 | +₹1,743 | −₹654 | ₹1,252 |

- With real history the new rules earned ₹3,053 less: the drawdown cut held
  2-lot trades at 1 lot, and on Sep 24 equity (₹212,281) sat just under the new
  15% halt line (₹212,500).
- Fresh accounts: identical old/new (no drawdown, <20 trades, no brake hit).
- ₹1.5L could not afford ~₹195–222 premiums (1-lot risk > 2% of pool) and missed
  the Sep 30/Oct 1 trades, including the +₹7,108 winner. **Minimum live test
  amount revised to ₹2,00,000.**
- One trade (+₹7,108) is most of the profit in every scenario.

Approximate stress test on the **actual** 38 paper single-leg trades since July
(new sizing/brakes applied, P&L scaled per lot, DR kept as traded; it can only
remove or resize trades; July–Aug trades came from older code, some of which the
current reward/risk gate would refuse):

| | Total since July | Worst day | Max DD | Losing days | Longest losing streak |
| --- | --- | --- | --- | --- | --- |
| As traded (old rules) | −₹22,089 | −₹8,580 | ₹38,054 | 22/33 | 10 days |
| New rules, ₹2.5L | −₹20,039 | −₹8,580 | ₹33,491 | 22/33 | 10 days |
| New rules, ₹2.0L | −₹19,960 | −₹8,580 | ₹31,433 | 21/33 | 10 days |

Exit mix since July: underlying stops 11 (−₹22,165), time stops 20 (−₹9,145),
trail stops 5 (+₹16,636). Reading: the risk rules trim drawdown a little but
cannot turn a losing stretch into a winning one; July–August lost because the
entries lost, not because size was too large. Entry quality in unfavourable
stretches is the open problem; any fix must be frozen and scored on sessions
from October 5, not fitted to July–August.

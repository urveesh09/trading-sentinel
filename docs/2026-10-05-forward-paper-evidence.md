# Everything on paper, forward evidence for the new strategies (Dev)

Owner direction (October 4, 2026): live money stays off for every module
tomorrow, every module runs on paper, and the new strategies run alongside so
their impact can be seen on days nobody has looked at yet. The owner also
authorised using that day's Kite session after about 16:30 IST for read-only
history acquisition.

## What the failed smart-Penny experiment taught (penny-smart-t4)

1. **More trades made things worse.** The incumbent took 38 trades (+₹91.72).
   The new entries took 79 (−₹47.75) and the combined policy 153 (−₹47.50). Its
   costs were five times higher (₹64 vs ₹13). In Penny, the small edge lives in
   *few* trades. Any next idea must remove trades, not add them.
2. **Ranking did nothing.** The cap of three positions never filled, so the
   order in which candidates were ranked never mattered. Ranking is not where
   the edge is today.
3. **The current exits beat the new ones.** With the shipped entry rules, the
   smart trail and stall exits ended at −₹2.27, against the incumbent's +₹91.72.
   This is not a fixed-entry comparison, because occupancy changes which entries
   happen. The noise-floor stop is
   still the only Penny change that has helped (on seen data).
4. **Seen September data is exhausted.** Every further idea scored there is
   in-sample. The only honest next measurements are forward paper days and the
   reserved Kite January–July history.

Momentum's round-3 development finding points the same way. Ordinary 15-minute
breakouts lost after costs in a falling market. `MOM_SELECTIVE` took zero trades
on the seen data because the market never qualified. That says nothing either
way about its edge.

Therefore this slice adds **no new thresholds**. It turns the untested ideas
into forward paper measurements instead.

## Changes

- **`MOM_SELECTIVE` Momentum shadow variant**
  - Files: `momentum_shadow.py`, `main.py`, `routes_ops.py`.
  - The broker-free Momentum shadow book now evaluates a third variant: the
    shipped evaluator, then the `momentum_selective.selective_gate` context check
    (NIFTY up on the day, stock at least 0.3% stronger, close above yesterday's
    high).
  - Each scan fetches NIFTY 50 15-minute bars once; previously the shadow made no
    market calls. A failed fetch makes only this variant reject, with
    `selective_index_bar_unavailable`.
  - The live and paper funnel, existing variants and their configs and
    fingerprints are unchanged.
  - Outcomes appear at `/api/experiments/momentum` and in the daily
    decision-quality report next to `MOM_BASE`.
- **`PENNY_SMART_SHADOW_ENABLED=True`**
  - The owner's separate smart-Penny paper book (₹2,000, own sibling DB
    `<DB_PATH>.penny-smart-paper.db`, no broker capability) now collects forward
    evidence.
  - It remains a failed candidate, not a trading policy.
- **Owner's smart-Penny controller and price-tick corrections committed**,
  unchanged from their verified state (see
  [the implementation receipt](2026-10-04-penny-smart-trader-implementation.md)).
  - Penny orders use the instrument's real tick size.
  - A live Penny entry refuses to proceed without today's tick metadata (paper is
    unaffected).
  - The noise-floor stop is tick-quantised.

## Paper and live switches for October 5

The defaults in Dev `config.py` and the gateway `config.js` already give this
picture. The Production `.env` overrides none of them (read-only check, Oct 4).

| Module | Live money | Paper |
| --- | --- | --- |
| Momentum | Owner-tap EXEC only; `MOMENTUM_AUTO_EXECUTE=false` | `MOMENTUM_PAPER_ENABLED=true`, shadow variants `MOM_BASE`, `MOM_RECENCY_5`, `MOM_SELECTIVE` |
| Penny MIS | `PENNY_LIVE_TRADING=false` | Paper book with the noise-floor stop, plus the smart paper shadow |
| EDGE (CNC) | `PENNY_EDGE_DISABLE_LIVE=true` | `PENNY_EDGE_DISABLE_PAPER=false` |
| F&O | `FNO_LIVE_TRADING=false`, `FNO_DISABLE_LIVE=true` | `FNO_DISABLE_PAPER=false`, `FNO_DR_DISABLE_PAPER=false`, shadow on |
| Swing / Range | Owner-tap alerts only (no automatic orders) | Shadow and decision-quality records |

Momentum, Swing and Range EXEC buttons still place a real order if the owner
taps one. To make tomorrow strictly paper, do not tap them, or set
`OWNER_LIVE_ENTRY_HALT=true`. That halt is enforced at the broker order call
(`kite_client`) and by the gateway executor, so paper books keep running while
every real entry is refused. Exits are never blocked.

## Acceptance

- `test_momentum_shadow.py`: four selective cases (accept; missing index;
  falling market; under yesterday's high), registry and config unchanged for
  existing variants.
- `test_momentum_shadow_integration.py`: shadow on/off keeps the funnel
  identical; shadow-on adds exactly one NIFTY 50 intraday call.
- Full engine suite (counts in HANDOVER_CHECKLIST).

## Rollout / rollback

- Promotion is through GitHub (merge to `main`, then restart Production).
- Rollback: `PENNY_SMART_SHADOW_ENABLED=false` stops new smart-shadow admissions.
  Existing simulated positions remain visible.
- `MOMENTUM_SHADOW_ENABLED=false` stops all Momentum shadow variants and the
  NIFTY fetch.

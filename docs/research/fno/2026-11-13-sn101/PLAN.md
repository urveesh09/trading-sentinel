# SN101–SN110: frozen plan, phase A (written and committed before any scoring, Nov 13, 2026)

Owner (Nov 13): run the other agent's SN101–SN110 (`docs/SN101_SN110_RESEARCH_REVIEW.md`, that agent's local file, not edited here), then SN111–SN115 (better permutations and perspectives from what SN92–SN110 teach) and SN116–SN120 (the combined learning). "I don't want fast testing, but correct testing." Phases B (SN111–115) and C (SN116–120) get their own frozen plans after phase A's results; nothing in them may re-score phase A's data with a changed rule and call it new.

Research only: no runtime, Production, broker or download action. Frozen Gold harnesses are untouched; the SN92 harness (`../2026-11-13-sn92/common.py`, parity with v5 proven) is imported, never edited.

## Data found before planning (inventory only; no outcomes read)

| Source | What it holds | Used by | Status |
|---|---|---|---|
| Sealed 1-minute caches (`sn01`) | 742 non-expiry sessions 2023 – Oct 28 2026, nearest weekly only | SN101, 102, 104, 107, 110 | Seen |
| **Production quote archive** (`sentinel-operations/fno-forward-panel-20261028/.../exports/20261112T103005Z/quotes`) | Real bid/ask + 5-level depth (price, quantity, orders), ~1 snapshot a minute, NIFTY and SENSEX: futures and **two weekly expiries** × ~11 strikes; 40 sealed days Sep 10 – Nov 11 2026 (Nov 12 is unsealed: excluded) | SN103, 108, 109 | Never used by an SN rule. Sep 10 – Oct 28 overlaps seen minute days; Oct 29 – Nov 11 (9 sessions) unseen by any SN rule |
| N012 Round 36 SENSEX panel (`simulation/2026-11-05-fno-n12/_local/round36/breeze.sqlite`, SHA-256 `0fdd6159…`) | 145 ordinary dates Jul 2025 – Oct 2026, front future + 20 strikes of one later expiry; never scored | SN106 | Unscored |
| 15-minute stock bars (Kite Jan–Jul 2026, Production Aug–Nov 2026) | Bank stocks for a bank-index proxy; no BANKNIFTY index or options exist anywhere | SN105 | Seen for NIFTY direction (SN96), not for bank continuation |
| RBI decision dates (N012 R31) | 17 sessions in the minute cache | SN107 | Seen as dates |

Files are read in place, read-only, each checked against its recorded SHA-256 (export manifest / R36 manifest); compact caches go to `_local/` (git-ignored). No copy of the 374 MB archive (disk 88% full).

## Common rules

- Costs: `fno_costs` NFO (BFO for SENSEX) on every leg + stress. Single leg ₹205/lot; multi-leg **₹205 per leg-lot is the primary (strict) basis** this phase (the other agent's correct point: SN95's +₹23,518 was at ₹100/leg, +₹17,144 strict); ₹100/leg and ₹400/leg reported.
- Fill model and causality as SN92 (`PLAN.md` there). The straddle rule SN95-L stays frozen as written; nothing here changes it.
- Every money result is per year, with trades, won/lost, without its best 5 days, and at the relevant wallets.
- A "pass" is never adoption; Gold v6 needs SN110's bar.

## SN101 — what SN95's result is made of (diagnosis)

1. A per-decision ledger at 10:00 for every session: R_today, its causal admission flag, combined ask × 65, days to expiry, affordability at ₹15k / ₹20k, exit (stop / 15:10), net, best net reached (MFE), index displacement.
2. **2 × 2 attribution:** premium ceiling ₹15k / ₹20k × stop room ₹3k / ₹4k, one lot, strict — for the SN95-L signal days (Gold-free and all days), by year.
3. **Decile table:** straddle net (pure hold, no ceiling, no stop) by R_today decile, by year.
4. **Matched permutation test:** the signal days' total (₹15k ceiling, ₹3k room, strict) against 5,000 random sets of non-signal days matched on exact days-to-expiry and premium tercile (same count, same affordability, same rule).
- **Decision (frozen):** R_today "carries information" only if the permutation p < 0.05 (Gold-free days) AND the top two deciles' mean net exceeds the bottom five deciles' in ≥ 3 of 4 years. Otherwise SN95's result is a premium/expiry/stop effect and is described as such.

## SN102 — forecast the remaining straddle value (one model, two baselines)

Features at 10:00 from 09:20–10:00 index minutes: positive and negative realised semivariance, largest-bar share of variance, directional efficiency |Σr|/Σ|r|, last-15 / first-25 variance ratio, R_today, log(straddle / future), days to expiry, yesterday's ATR%, |gap|, first-45-minute range. Target: the straddle's executable net at 15:10 (strict, 1 lot, pure hold). Ridge regression (λ = 10, standardised on the training rows), trained leave-one-year-out (primary) and walk-forward by year (2024–26, secondary).
- Baselines, same procedure: B1 = R_today alone; B2 = days-to-expiry + premium alone. Random admission at the same count per year (2,000 draws).
- Trade when the predicted net > **₹300** (primary; ₹0 reported): ₹15k ceiling / ₹3k room and ₹30k / ₹6k, strict.
- **Pass:** LOYO net > 0 strict, ≥ 3/4 years positive, beats B1, B2 and the random 95th percentile, positive without its best 5 days, positive at ₹400/leg and with the entry 1 minute late. Days: all sessions (primary) and Gold-free.

## SN103 — which expiry buys the move (real quotes)

On the quote archive's 40 sealed days: at the first snapshot at/after 10:00, the ATM strike (smallest |call mid − put mid|) for the nearest and the next weekly expiry; buy the straddle at the real asks, sell at the real bids at 15:10 (or the last snapshot before). Net at ₹0 / ₹100 / ₹205 per leg-lot; per day, per expiry, the paired difference, and per rupee of premium; on SN95-L signal days separately (R_today from the archive's own future and straddle quotes). Description; no selection.

## SN104 — does the straddle give its profit back?

For SN95-L's admissions (strict, ₹15k / ₹3k): the minute net path, MFE, giveback, minutes above +₹0 / +₹1,000, the hindsight bound (unattainable). One frozen challenger `GB`: once net ≥ ₹1,000, exit at the first minute net ≤ 50% of its peak; stop and 15:10 unchanged. Control: a fixed 13:00 exit. **Pass:** GB ≥ hold in total and in ≥ 3/4 years, and better without the best 5 days, and better than 13:00.

## SN105 — banks when NIFTY cancels them (information only)

Bank proxy: 12 BANKNIFTY members with fixed approximate weights (HDFCBANK .28, ICICIBANK .25, SBIN .09, KOTAKBANK .08, AXISBANK .08, INDUSINDBK, BANKBARODA, FEDERALBNK, IDFCFIRSTB .03 each, AUBANK, PNB, CANBK .025 each; renormalised over names present). Rest of NIFTY = SN96's fitted non-financial weights. At block ends 10:00–14:00: bank 30-minute return B, rest R, NIFTY N, share of banks agreeing with B. Cancellation state: |B| ≥ development 80th percentile, sign R = −sign B, |N| ≤ development median.
- Targets: the bank proxy's next 30 and 60 minutes, signed by B (continuation). Development Feb–Apr 2026, test May–Oct.
- Bank-only baseline (B and the last block) vs + R, agreement, cancellation flag: test error and correlation with a day-clustered bootstrap; the mean signed continuation in the cancellation state on test days, bootstrap interval.
- **Information pass:** incremental correlation interval above 0 OR continuation-in-cancellation interval above 0. No option P&L is possible: a pass means "download BANKNIFTY option minutes is justified", on the owner's word.

## SN106 — SENSEX directly (R36 panel, partial)

The SN95-L rule transplanted unchanged to SENSEX: R_today from the front future's 1-minute returns, implied σ from the SENSEX ATM straddle (strike step 100) of the panel's expiry, causal admission over prior panel dates (≥ 30), buy at 10:00, hold to 15:10, ₹3k room, BFO costs, lot 20, strict. Report every-day and admitted nets, and on dates common with the NIFTY minute cache: NIFTY vs SENSEX vs a pre-decision choice (the cheaper by R, abstain if neither admitted). Partial evidence only (145 dates, one expiry each).

## SN107 — RBI days (description)

On RBI decision days in the minute cache vs 5 matched non-event days each (same days-to-expiry, nearest earlier dates): implied σ change 09:45 → 10:30; straddle bought 10:30 held to 15:10 (strict); an ATM option bought at 10:30 in the direction of 10:00–10:30, 3-ATR index trail, 25% backstop, flat 15:10. No consensus/surprise archive exists: price-reaction only, labelled.

## SN108 — order-book absorption (quote archive, NIFTY future)

Per minute: mid, top-5 depth imbalance, a signed volume proxy (Δvolume × sign Δmid over 5 minutes), absorption (|5-minute mid move| / 5-minute volume, relative to the day's median, signed by the move). Targets: mid return over the next 5 / 15 / 30 minutes. Development Sep 10 – Oct 12, test Oct 13 – Nov 11. OLS baseline on the last 5- and 15-minute returns vs + the three book features. **Information pass:** test correlation gain interval above 0 (day bootstrap). Minute snapshots are not an order-flow tape: even a pass only justifies a capture design.

## SN109 — the real execution hurdle (quote archive)

For NIFTY options of both expiries (usable depth only): real spread vs the model's P75 spread by premium bucket and clock; the cost to buy / sell 1, 2, 3, 6 lots by walking the 5 levels; quote age; the 1-minute mid change (latency risk). At Gold v5's own research trades inside Sep 10 – Oct 28: real ask at entry and real bid at exit against the model's. Output: measured round-trip friction per lot against the model spread + ₹205 stress. **No cost gate changes**; ₹205 / ₹400 stay the standard.

## SN110 — the same account (Gold v5 + a straddle companion)

The straddle companion (SN95-L as written, or a phase-A pass) inside Gold's ledger: opened at 10:00 only when admitted, no Gold position is open, the premium leaves ≥ ₹15,000 of the wallet free for Gold, and with half the day room as its own stop (10% of the wallet). A Gold signal while it is open sells both legs at the bid that minute, then Gold enters. Every wallet of SN92's list; paired daily difference split into new-day profit and overlap days; maximum drawdown of the cumulative day nets; mean of the worst 5% of days.
- **Gold v6 bar (proposed by the other agent, adopted here before scoring):** ≥ 15% more total net than v5 at ₹30k fixed and ₹30k growing (stop 3), no worse maximum drawdown, no worse worst-5% mean, positive increment at ₹400/leg and 1 minute late. Below the bar: description only.

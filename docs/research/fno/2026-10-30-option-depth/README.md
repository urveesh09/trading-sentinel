# O30p: choosing a different option — no offspring passes

Research only. Freeze **75358a6**, pushed before scoring. Five focused tests pass. Six candidates replayed over both years; identical baseline and 20 random controls reused. Baseline parity +271 / +80,912 per lot. No unresolved candidates. No runtime deployment.

## Question and method

Could choosing an option that responds differently to NIFTY improve the robust parents, without adding another filter? For TPB alone and live + TPB on closed days, change only the planner's target absolute delta from 0.55 to 0.40 / 0.65 / 0.75. Actual sealed near-weekly contract quotes only, subject to the existing planner's expiry, freshness, cash, risk and entry gates. Each member keeps its own exits. The override is process-local and restored even when entry raises. No global live setting changes.

The pass rule was declared before scores: beat the own parent in both years, >=40 trades/year, positive net excluding the best day and after 200 extra/trade, no worse in at least three half-years, drawdown within 1.25 times parent, no unresolved trades and beat random median. All six are reported.

## Results (rupees per modelled current 65-unit lot)

| Book | 2025 | 2026 | 2025 minus 200/trade | 2026 minus 200/trade |
|---|---:|---:|---:|---:|
| REF|LIVE | 271 | 80,912 | -27,329 | 59,712 |
| REF|BEST | 34,517 | 80,232 | -8,283 | 46,432 |
| REF|TPB | 36,694 | 42,056 | 15,294 | 25,056 |
| P|TPB|D40 | 9,124 | 50,219 | -12,076 | 33,219 |
| P|TPB|D65 | 20,403 | 4,307 | 2,803 | -10,893 |
| P|TPB|D75 | 13,799 | 13,658 | 1,599 | 1,858 |
| P|BEST|D40 | 384 | 58,032 | -41,816 | 24,432 |
| P|BEST|D65 | -14,587 | 29,636 | -47,787 | 2,636 |
| P|BEST|D75 | -40,310 | 38,920 | -45,710 | 17,320 |

All six fail. Choosing on one year and checking the other fails for both parents in both directions. The cheaper 0.40 TPB improves 2026 (+50,219 versus +42,056) but sharply worsens 2025 (+9,124 versus +36,694). The deeper-in-the-money choices are not a transferable improvement. A target delta is a preference, not a promise the archive contains exactly that contract/delta. Higher premiums also change affordability and the subsequent book path; these are exact planner replays, not slices of the old trades.

## Important new data-quality finding

After the download, a full streaming structural check found **162 negative-volume candles** in the raw history: 108 futures / 54 options. Both raw sealed inputs were separately checked: the **2025 research dataset contains 2 negative-volume futures rows and 54 option rows; 2026 contains zero**. Volume affects futures features and cumulative option liquidity. The exact ranking is therefore **provisional**, and qualification requires verification/reacquisition plus a new versioned dataset and parity/sensitivity replay. Never replace negative values with guessed zeros/absolute values or overwrite the sealed evidence. `data-quality-findings.json` records counts. None of these results supports promotion regardless of that unresolved defect.

The raw download is outside Git. Its `run-logs/negative-volume-reacquisition-plan.json` records 139 affected request keys for verification after owner login / the next allowance. All 6,082,896 raw candles passed finite positive coherent OHLC and timestamp checks; SQLite quick_check passed. These checks do not prove complete session coverage, correct volume, live spreads or true fills.

## Learning and concrete next plan

1. **Data quality first:** verify the negative volumes against provider semantics; controlled re-fetch into separate evidence, preserve original responses and hashes, rebuild new sealed versions, rerun references and the small fixed candidate set. Retain missing-session/entry-window reasons, rather than manufacturing candles. Keep the 2024 exam and its declared books unchanged.
2. **An account-realistic test:** exact one-lot Rs12,500 cash/reservations, entry affordability, broker charges, original stops, drawdown halt, missing bids and forced exit/retry semantics. Weekly filters on a multi-lot parent path are proxies and cannot answer the owner's Monday cash outcome.
3. **Existing 2024 exam:** after clean acquisition, apply the already-frozen scorer once; no extra search on 2024. If input validation fails, report it before scoring. An earlier year tests another regime, not future profitability.
4. **Forward evidence:** preserve quotes/depth, execution delays and slippage; compare the existing TPB and blend on fresh days. Re-evaluate whether extra trade frequency survives costs. Any changed live book needs a separate Dev implementation, regression tests, PR/deploy and explicit owner activation.
5. **Smarter intraday development:** next hypotheses should earn their complexity through falsifiable experiments, e.g. executable option cost versus causal expected move, an entry-price limit/retest with missed-trade accounting, and thesis-based target/stop policy. No unbounded genome search until the evidence/execution gaps are fixed. This round does not assert these untested ideas will help.
6. **Partner data independence:** source reads partner quote/history first, so the owner's expired subscription is not an automatic stop for manual CHECK/watch. The partner needs its own valid session and entitled key; cached instruments/future mappings must be available. A generic system health 200 is not proof of a delivered tip. Verify source-specific data timestamps and delivery receipts separately, without sending a test message unless requested.

TPB remains positive after 300 extra/trade in each year (+4,594 / +16,556). That is a useful stress diagnostic, not proof of executable edge or safe funding. Its combined normalised drawdown is 22,896, and its filtered Rs12,500 weekly proxy has 28 up / 33 down / 35 no-change weeks, worst end 8,503. None is an exact owner-account forecast.

The current live book still has the same rules: these studies improve our knowledge and reject weak ideas; they do not establish a higher chance of profit next Monday. No trading-system or capital switch was changed.

## Files and reproduction

`lab_p.py`, `analyze_p.py`, `test_lab_p.py`, `freeze.json`, `results.json`; raw trades and funnels in ignored `_local/`. Run with the engine venv, `O30C_YEAR=2025` then 2026, `lab_p.py run --jobs 2`, then `analyze_p.py`. Macro/micro study and data hash verification: [O30n](../2026-10-30-micro-adaptation/README.md).

Subscription scope: [Zerodha's paid data plan is per API key](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/historical-data-and-live-market-data-payment-plan); login/session requirements are documented in [Kite user API](https://kite.trade/docs/connect/v3/user/). These public facts do not verify this account's current entitlement or delivery.

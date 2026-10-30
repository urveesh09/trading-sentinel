# O30n: micro-adaptive offspring — none passes

Research only; freeze **b8ed28d**, pushed before scoring. Eight focused tests passed. All 31 books (8 candidate definitions, 3 references, 20 random books) completed on each sealed year: 62 evaluations, with references reused under identical identities. Exact live parity is +271 / +80,912 per lot. No unresolved candidate trades. No runtime change, no Production edit or deploy.

## What was tested

- Extend a position's time/trail only while completed intraday bars show continuing progress, VWAP/EMA agreement and directional efficiency. Retain original stops, premium backstop, existing profit-lock setting and hard-flat deadline.
- Exit on two consecutive post-entry VWAP thesis failures, after the shipped safety ladder gets priority; a positive observed bid is required.
- A new confirmed VWAP-pullback reclaim entry, alone and added after the previous best book.
- Each micro rule on TPB alone and on the previous best book (live + TPB on closed days).

These are eight frozen definitions, not eight independent discoveries. TPB already uses 120 minutes / 2 ATR / no profit lock: its RUN arm is a deliberate-effect null control in hindsight, and BOTH equals BREAK. The complete TPB RUN trade list equals the TPB reference; no added benefit is claimed.

## Results (rupees per current 65-unit lot; minute-candle model)

| Book | 2025 net | 2026 net | 2025 minus 200/trade | 2026 minus 200/trade |
|---|---:|---:|---:|---:|
| REF|LIVE | 271 | 80,912 | -27,329 | 59,712 |
| REF|BEST | 34,517 | 80,232 | -8,283 | 46,432 |
| REF|TPB | 36,694 | 42,056 | 15,294 | 25,056 |
| N|TPB|RUN | 36,694 | 42,056 | 15,294 | 25,056 |
| N|BEST|RUN | 30,365 | 79,349 | -12,435 | 45,549 |
| N|TPB|BREAK | 31,692 | 28,380 | 9,892 | 10,980 |
| N|BEST|BREAK | 16,714 | 78,217 | -25,886 | 43,817 |
| N|TPB|BOTH | 31,692 | 28,380 | 9,892 | 10,980 |
| N|BEST|BOTH | 7,212 | 77,639 | -35,188 | 43,239 |
| N|RECLAIM | -18,539 | 30,920 | -60,939 | -5,680 |
| N|BEST+RECLAIM | -17,717 | 33,888 | -84,917 | -23,112 |

All eight fail the frozen improvement rule. Selecting on one year and checking the other fails in one direction. No failed arm is promoted or retuned.

The useful finding is narrower: the two-close VWAP exit cuts TPB profits; adding a superficially sensible entry increases activity and loses in 2025. Existing TPB is more robust under execution-cost stress than the higher-total-profit blended book. The earlier claim that the blend is the 'best' must be read as highest seen-data net, not best downside or executable performance.

## Limits and next work

Both years were already used by prior research: this is development, not a new clean test. The 2024 exam remains untouched and byte-identical; this round adds no books to it. Earlier-year 2024 is an additional market sample, not future performance.

- The existing best blend's 2025 +34,517 turns into -8,283 under only 200 extra per trade. The deployed live book's 2025 +271 turns into -27,329. Neither supports an assurance that Monday's real-money week will profit.
- TPB remains positive under that stress, but positive totals hide losing weeks and drawdowns. This is not a capital recommendation.
- Minute-close synthetic bid/ask, fixed current lot size, incomplete historical regime labels, provider gaps and missing true depth limit the result. Stress holds the original trade path fixed.
- The 12,500-rupee weekly figure in results is explicitly a filtered parent-trade proxy, not an exact cash-constrained one-lot replay. Build the latter before using it as owner-account evidence.
- Keep 2024 as the frozen exam, add forward quote/depth evidence, and require separate Dev/PR/deploy and owner activation for any live change.

## Reproduction

`O30C_YEAR=2025 python lab_n.py run --jobs 2`, then 2026, then `python analyze_n.py`; use the documented engine venv. Frozen hashes bind source, settings and the sealed manifests. `input-verification.json` independently verifies both raw database hashes. `_local/` retains all raw replay trades and is ignored by Git.

The VWAP idea is informed by [Zarattini and Aziz's VWAP study](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4631351); results on US equities do not transfer automatically to NIFTY option buyers. The bounded trials and full failure ledger follow the selection-risk concern in [Bailey et al., The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf). This study does not claim to have estimated PBO.

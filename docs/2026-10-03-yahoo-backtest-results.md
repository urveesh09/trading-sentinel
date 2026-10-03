# Yahoo-only backtest delivery and results — October 3

The reusable [script](../scripts/backtest_all_yahoo.py) now accepts inclusive
start/end arguments and exercises all registered shipped non-F&O paths using
Yahoo market data. It does not read Sentinel candles, positions, quotes or cash
history. Current universe configuration supplies names only. See
[usage guide](YAHOO_BACKTEST_GUIDE.md) and
[pre-implementation plan](2026-10-03-yahoo-all-module-backtest-plan.md).

This is an all-module research interface, not a claim that every module already
has a complete entry-to-exit portfolio adapter. Results preserve the Lab's actual
EVALUATOR, LIFECYCLE and PORTFOLIO_PARTIAL boundaries. Partner has no OHLCV money
book adapter; F&O is excluded. No strategy thresholds, risk budgets, exits,
orders or runtime settings were changed.

## Runs and data

The main request is Q3 **July 1–September 30, 2026**, inclusive IST. A separately
declared **September 24–30** intraday diagnostic remains inside that window and
contains five sessions. The primary quarter intraday requests were preserved as
UNAVAILABLE: Yahoo returned native 1m retention of 30 days and 15m retention of
60 days. Seven-day minute chunking cannot recover expired July data.

Download acquisition archived **1,203** responses/probes, 1,197 available and
six unavailable. Imported daily rows: **374,379**; intraday rows: **161,790**.
The separately hashed B1-validated snapshot contains **371,706 daily** and
**140,689 intraday** rows. It excludes whole invalid ticker-days and invalid
daily histories; original imported data and raw responses are retained.

Current requested universes are 100 Penny names and 500 stock names. Effective
daily universes are **95 Penny / 499 stock** names. Missing daily history:
ATLPP-E1 and JBCHEPHARM. Invalid daily history: BOHRAIND, GTECJAINX, SHYAMTEL and
WEWIN. Their exclusion was frozen before scoring, not chosen from profits.
The empty checked-in Dev Penny universe uses the explicit October 1 symbol-only
fallback. None of its retained trade/price history was used. Current membership
still cannot reproduce historical constituents.

Yahoo all-null slots, flat zero-volume known-holiday marks and its exact
metadata-bound closing quote mark are recorded as absent candles/marks. Invalid
actual candles are preserved and B1-invalidated; no OHLC/volume is repaired or
invented. Prices are Yahoo's quote OHLC as returned, with no local adjustment;
historical split/adjustment revisions remain a source limitation.

## Current results

| Module | Dates | Actual result | Scope/limit |
| --- | --- | --- | --- |
| Adaptive Penny EDGE | Q3 | **1,142 candidate appearances / 167 selections**, 65 scans | EVALUATOR; no filled-trade P&L |
| Swing | Q3 | **171 entry decisions** / 31,749 decisions | EVALUATOR; Yahoo supplies the actual index warm-up missing from the earlier cache study |
| Range Reversion | Q3 | **1,097 ENTER verdicts** / 32,423 decisions | EVALUATOR; no execution/exit P&L |
| Penny MIS strict | Q3 and Sep 24–30 | Unavailable | Expired quarter minutes; recent Yahoo opening bars have zero-volume ranges, so no complete-session day |
| Penny MIS gap sensitivity | Sep 24–30 only | **18 closed trades, +₹15.1765**, 0 unresolved | PARTIAL LIFECYCLE; unchanged entry/exit rules, explicit incomplete-data sensitivity |
| Penny CNC | Sep 24–30 only | **0 entries**, 398 evaluations | PARTIAL LIFECYCLE; no profitability estimate; 77 requested stock-days lack usable partial-candle evidence |
| Joint Penny gap sensitivity | Sep 24–30 only | **18 admitted/settled, +₹15.1765**; ₹2,000 → ₹2,015.1765; no cash rejection/locked exposure | PORTFOLIO_PARTIAL; reuses the same MIS outcomes, not additional profit |
| Momentum | Sep 24–30 only | **2 virtual closes, −₹0.827101** | EVALUATOR plus existing virtual T1 lifecycle; both time exits, no later-day fallback |
| Partner advisory/protection | Q3 | NOT_ADAPTED | No OHLCV money-book replay; no advice/qualification was generated |

All quarter MIS/CNC/joint/Momentum primary attempts remain unavailable. The
shorter studies never replace them. Sixteen report rows include separate strict
and sensitivity attempts; there is no system-total profit or annualized return.

Penny MIS sensitivity made 87,623 evaluations, accepted 46 signals and filled
18. Other admissions were occupied (12), stop already breached (10), no executable
evidence (4) or drift rejected (2). Five wins and thirteen losses yielded gross
₹24.46 less ₹9.2835 charges, net **₹15.1765**, profit factor **1.187**, realized
cash drawdown **₹45.0962**. Exits: 13 PAPER_STOP_LTP, four smart-EOD and one
15:00 time exit. Mean trade R is **−2.322** despite positive money P&L: positions
have different risk amounts and paper LTP stops can overshoot tiny planned risk.
Do not treat those two metrics as interchangeable.

Removing the largest winner leaves **−₹27.7362**; the shipped adverse-fill bound
is **−₹115.8338**. The small positive result is fragile and is not evidence to
loosen gates. It does establish that current Penny rules can find trades on a
broader, fresh provider sample instead of the earlier sparse retained cache.
Opening-bar volume remains incomplete and excludes a complete-session claim.

Momentum's recent study uses 52,530 validated native 15-minute bars across
498 evidenced stocks and five sessions. ONESOURCE lost ₹7.38705; TENNIND gained
₹6.559949. Both virtual exits occur at 15:15 on their entry days. Unlike the
earlier retained-cache study, this dataset supplies EOD observations, so there
are **zero overnight fallback exits** here. Two trades still cannot establish
expectancy, and full quantity at T1 remains different from the live partial
runner/trail. No out-of-sample qualification is available.

## Reproducibility and verification

The original acquisition, earlier three-stock development trials and failures
are preserved. A final offline all-module run uses only the verified Yahoo
archive, freezes current source/settings/importer hashes, and verifies the raw
and validated snapshots. The final summary is
[here](research/yahoo/2026-10-03-q3-final/summary.md); the acquisition receipts are
[here](research/yahoo/2026-10-03-q3/provider-manifest.json). A separate EDGE/Range
offline rerun already reproduces both sets of quarter metrics exactly.

Focused verification command:

```powershell
.\python-engine\winvenv\Scripts\python.exe -m pytest scripts/tests/test_backtest_all_yahoo.py scripts/tests/test_current_system_review.py python-engine/tests/test_backtest_lab.py python-engine/tests/test_research_data_contracts.py -q
```

**70 passed**, one existing HTTPX deprecation. Tests cover dates/clocks,
non-candle provider placeholders, invalid whole-day rejection, identity/currency,
retention errors, raw tampering, no overwrite, offline reuse, module isolation,
Production/F&O exclusion, UTC cash ordering and mid-run policy drift.
Compilation, diff and deterministic 240-module atlas checks accompany delivery.
Software tests do not prove profitable strategies.

Full raw/coverage/provider archives remain locally retained and Git-ignored;
compact per-run summaries and retention sidecars bind their hashes. A Git clone
does not alone carry the data needed for offline replay. All 16 original/final
outcomes, 1,203 raw response hashes, both snapshot row hashes and current policy/
importer fingerprints passed the [integrity receipt](research/yahoo/2026-10-03-q3-final/verification.json).

Source baseline `3cbf0ff`; no new dependency, live schema/configuration change,
Production edit, broker action, push or deployment. New research configuration
is only the symbol fallback and immutable Yahoo reports. Source commit and
research delivery **`df0c3791c4ba10e55c0142fa47e1d735883aa8af`** are Dev-local.
Immediately after commit, guide/plan/checklist/results consistency, byte-identical
atlas regeneration, all 16 final reports, excluded large local evidence and
clean Dev worktree checks passed. This receipt update is documentation only;
its own commit also receives immediate consistency/clean-worktree verification.

Remaining limits: Yahoo intraday retention, current rather than historical
membership, adjusted-history uncertainty, historical broker/manual/context
admission, EDGE/Swing/Range complete lifecycles, live Momentum exit parity,
full portfolio equity and prospective qualification. The one-script interface
is delivered; these limits do not become solved by downloading additional bars.

# Overnight v2 enrichment — November 4, 2026

**Outcome: a useful conditional cost-aware route, not a qualified replacement.**
The best new rule improves poor post-close fill scenarios while retaining most
of v2's ideal modeled profit. It does not beat v2 with complete close fills.
Stricter stresses still lose money. A default-off evidence path is built in
Dev so the next comparison can use actual decision-time inputs and valid
post-close observations. No strategy/real order is activated. Production is
unchanged; no push or deployment.

## The enrichment

Keep native V2's top-ten-then-night-screen candidate pool and two equal tickets.
For each stock, compare its existing causal shrunk 60-night return estimate
against an estimated full regular-session roundtrip cost: spread/slippage,
fees including DP, and exit allowance. If the estimate clears that hurdle,
reserve half the ticket for a regular-session buy and half for post-close.
Otherwise reserve all of it for post-close. Fund both sleeves; never replace
a failed close order using tomorrow's knowledge. Zero filled shares incur no
fee. DP is charged once per sold stock, not twice for the two entry sleeves.

This is `V3_COST_ROUTE` in the research engine. The night threshold, lookback,
ranking and cost schedule were not fitted again. No learning/genome model or
new stock predictor was needed. This is an execution-risk trade-off, not a
new alpha claim or an enabled strategy. Its regular entry and the auction
exit are still price/fill assumptions.

## Fixed Rs 25,000 results

Profits are withheld from risk capital; losses reduce the next day's own
capital. These are cumulative modeled rupees from repeated fixed-size trades,
not compounded returns and not actual trading profit.

| Panel | Assumed winning post-close fills | Native v2 | Cost-aware route | Difference |
|---|---:|---:|---:|---:|
| 2023-Oct 2026 Yahoo, already seen | 100% | 227,942 | 219,880 | -3.5% |
| Same | 75% | 161,775 | 163,707 | +1.2% |
| Same | 50% | 81,310 | 96,062 | +18.1% |
| 2015-2018 older check, first opening | 100% | 127,735 | 124,211 | -2.8% |
| Same | 75% | 72,073 | 72,704 | +0.9% |
| Same | 50% | 20,056 | 24,366 | +21.5% |
| Jul 2025-Sep 2026 Kite, partial tail | 100% | 51,835 | 50,387 | -2.8% |
| Same | 50% | 11,300 | 15,043 | +33.1% |

Primary model: regular entry at final daily close +36 bp, post-close at official
close, next daily opening price less 5 bp; all filled-share costs included.
A deterministic common ticker/date draw denies the stated share of reference
net-winning post-close tickets; losing tickets all fill. It never changes the
pre-reserved quantities or selection. Regular fills are assumed complete.
Thus 50% is an adversarial scenario, not measured broker availability.

The fresh older check has 1,515 full-fill closes, no unresolved exposure.
At 50% fills, drawdown falls from Rs 8,159 to Rs 7,620 (32.6% to 30.5% of initial
capital); at full fills it is Rs 5,276 versusRs 5,298. Showing drawdown against
initial capital avoids diluting it with years of withheld profits. Kite has
one unresolved position at the data boundary in every original arm: its totals
are partial evidence, never a qualification pass.

Native V2 here applies depth ten BEFORE the night gate, like current runtime.
The earlier v2 research filtered all candidates before depth ten. That is why
its headline totals (e.g. Rs 231,005 Yahoo) differ slightly from this study's
native v2 control. The legacy control was reproduced separately, not silently
replaced. Actual-panel parity:30 trades, zero differences in shares/summary.

## Iterations and rejected ideas

- Round 1: choose the lowest downside-risk pair from the eligible pool and cap
  inverse-risk weights at 65%. Yahoo ideal profit fell 15% for 25% less DD. It
  missed the retained-profit requirement. Reject.
- Round 1: buy half of every ticket early. It protected the 50%-fill case but
  paid spread even when unnecessary. On the older higher-cost 75%-fill case,
  profit fell fromRs 48,509 toRs 18,328. It failed the frozen worst-model check.
- Round 2: preserve the first ranked pick; choose a new equal-weight partner
  only with at least 20% lower estimated pair downside risk. This retained more
  profit but did not meet improvement rules. Reject.
- Round 2: cost-aware early sleeve. The only finalist to pass the declared
  four-model minimum-net arithmetic test on older history. Full-fill profit
  improvement failed. Only 167 of 1,515 older full-fill tickets used an early
  sleeve; it is a selective hedge against non-fills, not blanket early buying.

Source/round freezes were committed before scoring: round 1 `4d95c71`,
round 2 `a8976d1`, older finalists `a4cf227`. At most two new arms per round.
Older history was opened once, after the finalist commit. No arm changed
following that opening. The earlier 2019-2022 exam remains seen and untouched
by this study; no reserved Penny/F&O/Breeze data was used.

## Why this is not qualified

The raw older verdict is an arithmetic pass for the four predeclared models,
not general profitability. Fixed-rule diagnostics retained after the opening:

- Ten further random seeds at 50% fills, original costs: the cost route beats
  v2 in 10/10 Yahoo and 10/10 older runs. Average additional net isRs 15,397 and
  Rs 4,529 respectively. At 75% fills it wins only 5/10 older seeds; mean benefit
  isRs 96. The small middle-case benefit is not robust.
- Combine 50% winning fills with 60 bp regular entry and 20 bp exit: older mean
  profit is negative for both (-Rs 12,931 v2; -Rs 12,641 cost route). The four
  original scenarios did not include every combination of bad conditions.
- Correlate the non-fill draw across the day's two stocks at 50%: older net is
  -Rs 8,317 v2 versus -Rs 2,260 cost route, withDD Rs 15,392 versusRs 12,489.
  The route reduces this loss; it does not establish a safe profit.
- Final daily candles determine the research candidate list. That list and
  final daily volume are not available for a15:20 buy. The night mean itself
  is known by today's open, but that does not fix candidate/price clock
  mismatch or unknown 15:20-to-close drift. Full-fill PC v2 is also a daily
  proxy: real 15:20 picks may differ. No claim of executable early-entry profit.
- Daily open need not be an opening-auction trade. Post-close queue priority,
  broker admission, stock eligibility, partial fills and next-morning auction
  fills remain unobserved. No volume total proves our own fill.

Final status is `RESEARCH_ONLY_NOT_QUALIFIED` in `qualification.json`.
The clock limitation blocks promotion regardless of numerical pass rules.
This is the honest boundary of the evidence, not a reason to re-open or tune
on the older check again.

## Better execution evidence built in Dev

New `overnight_execution_evidence.py`, independent from the old book, ON_V2,
Oct 21 shadows and original probe. Flag
`EDGE_OVERNIGHT_EXECUTION_EVIDENCE_ENABLED=false` by default.

- Optional entry hook archives the actual ranked 15:20 shortlist, already-fetched
  fresh quotes and night estimates, with decision/late state. No extra quote,
  rescan, assumed position, fee/P&L or alteration to admissions.
- Three new bounded quote jobs:15:49 before the supported interval,15:51 for
  the hypothetical decision baseline,16:03 after it ends. At most ten existing
  ENTRY-receipt names; missing quotes remain rows in the denominator.
- A valid capacity proxy requires same-session provider/receipt/trade clocks,
  fresh quotes, monotone volume, an observed supported-session trade by the
  decision and a later trade after that decision. Closing-price reference is
  a post-close last trade, never the quote's previous-day `ohlc.close`.
- Only later volume at a conservative 1% participation is compared with one
  hypotheticalRs 12.5 k ticket. Every answer says `actual_fill=UNKNOWN`; no order
  or aggregate portfolio is implied. Missing/stale/reset/cross-day evidence
  stays `UNKNOWN`. Even `CAPACITY_PROXY_MET` is not an order fill.
- `GET /experiments/edge-overnight` gains an additive `execution_evidence`
  field. A missing store is not created by reading it. Damaged evidence cannot
  break the older comparison. Existing book/shadow/P&L and probe rows stay
  unchanged. Separate sibling`<DB_PATH>.overnight-execution-evidence.db`;
  no migration of existing stores. Rollback is the new flag=false.

Current dated broker rules support post-close 15:50-16:00 and pre-open market
order submission 09:00-09:05. The earlier 15:32-to 16:03 volume delta can include
CAS matching/late reports on eligible names; it is not isolated post-close
volume or proof of fills. The new API caveat preserves the older result while
making that limitation explicit. Sources: [Zerodha dated bulletin](https://zerodha.com/marketintel/bulletin/439989/introduction-of-closing-auction-session-cas-in-the-equity-cash-segment-and-certain-modifications-in-the-pre-open-auction-session),
[broker session guide](https://support.zerodha.com/category/trading-and-markets/trading-faqs/market-sessions/articles/what-are-pre-market-and-post-market-sessions-and-orders).

## Production reality and coverage

Read-only Production export at checkout `5e30ce0`: existing book 21 closes,
-Rs 878.58; ON_TWO_LARGER15 closes, -Rs 1,790.92; ON_TIGHT_SPREAD18 closes,
-Rs 2,541.47, all flat, since 2026-10-22. These have different admissions, so
not a paired v2 trial. ON_V2 is absent there. Entry-at-close counterfactual for
the book is+Rs 1,165.47; observed-bid exit comparison is-Rs 2,005.96 on 20 closes.
Counterfactuals are not fills. Actual forward paper results take precedence
when assessing deployed performance. No Production file/process changed.

Older public acquisition requested 874 existing broad-universe symbols;
443 returned 710,167 rows. Validation retained 327 equity tickers/514,884 rows,
35,637 zero-volume rows excluded,157,319 pre-last-split rows excluded,
102 inconsistentOHLC rows excluded. NIFTYBEES supplies the calendar/regime:
986 scoring sessions,984 with candidates,11,484 candidate observations.
All missing/failed provider receipts remain. Raw data and full ledgers are in
`_local/`, with hashes in freezes and acquisition receipts. No local repair,
forward fill, brokerage bypass or invented historical universe. Current
surviving membership and later-known split restrictions limit generalisation.
A backwards new historical check is not prospective qualification. Fees are
current frozen CNC costs applied consistently to all years, not tax history.

## Verification, status and next usable step

See `VERIFICATION.md`, `audit-results.json`, `environment.json`, the two round
result files,`older-results.json`, `older-verdict.json`, `qualification.json`
and `production-readonly.json`. Sixty primary result artifacts reconcile net,
fees, quantity, funded daily cash and flat ending equity. No profit reinvestment.

Engineering tests verify mechanics, not profitable strategies. New collector
remains disabled; no process restarted, no extra live quote request or order
was made. Smart/daytime EDGE, V2 and existing books remain unchanged. New code
is local Dev commits only, not pushed or deployed; owner working changes and
all older research are preserved.

Next meaningful test: enable only the reviewed evidence path in Dev, freeze a
forward own-cash paper route using archived actual 15:20 inputs, and compare it
with native V2 under explicit missing/partial fills and timely auction exits.
Real-money fill proof requires a separate owner-authorized order trial; none
is built or executed here. More daily-data optimisation cannot resolve that.

# When did the failed entries work, and could we recognise those times?

**O31h, 31 October 2026. Yes, both had good trades and months. No dependable
entry-time condition was found, and neither follow-up entry passed.**
Research only; the main strategy, application and Production are unchanged.

Source/diagnosis/follow-up rules were frozen and pushed as **a45eadd before
the 21 new replays**. [Rules](PLAN.md), [configuration](configuration.json),
[freeze](freeze.json), [diagnosis](diagnosis.json),
[conditional stability](conditional-stability.json), [new results](results.json),
[financial checks](crosschecks.json), [diagnostic checks](diagnostic-crosschecks.json).
The previous failed study is [O31g](../2026-10-31-fno-complements/README.md).

## 1. When the original entries performed well

Numbers below are **one normalized lot of65**, after broker charges and the
same extra Rs200/trade assumption. These are simulated profits, not real fills.

| Original entry | Winning trades / all | Profitable active months | Example good trade |
| --- | ---: | ---: | --- |
| Intraday DMI break | 34/138 | 11 | July8,2026: +Rs14,699; future moved about270 points in its favour by exit |
| Confirmed shock recovery | 17/44 | 10 | January12,2026: +Rs4,885; future moved about149 points in its favour by exit |

Other good DMI trades: August5,2024 **+Rs12,652**, September30,2024
**+Rs7,907**, August1,2025 **+Rs5,910**. Its best month was August2024
**+Rs6,711**. The August5 winner alone exceeded its entire 2024 net; removing
that day turns the year from +Rs1,795 into **−Rs10,857**.

Recovery's next two best trades were June10,2026 **+Rs4,335** and July16,2026
**+Rs3,482**, with about102/81 favourable futures points by exit. Those three
2026 winners total **+Rs12,702**; the other six 2026 trades total **−Rs1,771**.
It also earned **+Rs4,268 in September2025**, while losing over 2025 overall.

## 2. Why those profits did not become a reliable strategy

**The winning trades captured substantial follow-through after entry.** Most
of the largest wins exited by a trailing stop after the move developed.
That observation describes the outcome; it does not tell us beforehand which
initial break or recovery will keep moving.

The DMI rule had **104 losing trades**, totalling −Rs178,529, against its34
winners' +Rs102,912. Its stops/time stops were frequent: 65 underlying-stop
and37 time-stop exits among138 trades. A trend-strength reading and a new
price extreme did not establish that the subsequent entry would continue.

Recovery had27 losing trades, totalling −Rs24,000, versus17 winners'
+Rs23,255. There were15 time-stop exits. The initial rebound often did not
produce enough profitable movement under this entry/exit/option model.

**Costs explain some losses, not all.** Gross option P&L was positive but net
after all declared costs negative on9 DMI and3 recovery trades. There were
also13/6 losing trades where the future ended on the favourable side of the
entry; on5/3 of these the gross option result itself was negative. This
establishes a divergence in the recorded model, not its cause. We did not
isolate implied-volatility changes, decay, spread, delta changes or stale
quote effects, so none is presented as a measured explanation.

## 3. Can the favourable conditions be known before buying?

**The inputs can be observed before entry; a profitable outcome cannot be
known. We did not demonstrate a useful predictor from these inputs.**

For all182 original trades, reconstructed only the completed signal bars and
daily history through yesterday. Checked daily DMI/EMA alignment, prior ADX,
prior RV10, opening30-minute range versus prior daily ATR, VWAP distance,
relative volume, six-bar path efficiency, gap direction, direction and clock.
Future intraday prices and today's daily high/low/close were then changed:
all182 entry-input sets remained identical.

Across **22 described single-condition buckets per entry**, none earned in
every year. All buckets and missing values are published, including these
tempting examples:

| Condition known at entry | 2024 | 2025 | 2026 |
| --- | ---: | ---: | ---: |
| DMI entry after11:00 | +Rs2,253 (6 trades) | −Rs4,124 (15) | +Rs12,229 (12) |
| DMI entry after a wide opening range, >=0.5 prior dailyATR | +Rs13,310 (11) | −Rs25,970 (25) | −Rs9,091 (7) |
| Recovery with prior RV10 below15% annualized | −Rs3,514 (11) | −Rs3,453 (16) | +Rs10,029 (6) |

Selecting one positive condition on two years, requiring at least8 trades in
each training year, produced **no eligible choice in any of the three
rotations**. These are exploratory subsets of old trades, not independent
holdouts or cash-path replays. Removing a trade can release later entries and
alter sizing/brakes, so subset P&L is never a portfolio recommendation.

**Even hindsight day labels are insufficient.** Classifying a finished day
as trending helped explain DMI's2024 wins, but DMI was still negative on such
days in2025/26. Recovery earned on two-way2026 days but lost on two-way2024/25
days. Finished-day shape is not an entry input and was never used by a rule.

This does not prove that all combinations are impossible. With44 recovery
trades, trying many intersections can easily manufacture a good-looking
historical subset. We stopped short of such a search.

## 4. What the literature adds

The most relevant new source is [Xiao, Yin & Zhao's US index-ETF jump study](https://onlinelibrary.wiley.com/doi/full/10.1111/jfir.12223).
It separates the behaviour following news-related jumps from other jumps,
and distinguishes scheduled from unscheduled news. That supports testing
reversal and continuation separately; it does not establish either rule's
profitability in NIFTY options.

[CME's explanation of futures volume](https://www.cmegroup.com/education/courses/introduction-to-futures/what-is-volume)
also matters: a volume spike does not reveal whether participants are opening
or closing, or why they trade. Our bars cannot label it buyer absorption.

Related domains reviewed:

- **Continuation after a level holds / pullback entry:** [Osler's NYFed study](https://www.newyorkfed.org/research/staff_reports/sr125.html)
  explains different effects of orders around FX levels. Our VWAP adaptation
  is an inference, not the paper's tested trading rule.
- **Reversal of stock-specific pressure:** [Brogaard, Han & Kim](https://papers.ssrn.com/sol3/Delivery.cfm/4731947.pdf?abstractid=4731947&mirid=1)
  study residual returns across stocks. A NIFTY-only dataset lacks their
  constituent/factor information; we cannot reproduce it faithfully here.
- **Momentum at different speeds with regime changes:** [Wood et al.](https://arxiv.org/abs/2105.13727)
  combine a learned momentum model with online changepoint detection. This is
  a separate training/validation project, not a ready-made NIFTY-option edge.

The full primary-source review and data limits are in [SOURCES.md](SOURCES.md).
News, true signed order flow, depth and stock-specific residuals were not
invented from candles.

## 5. Two related entries were implemented and tested

These change **when and where to enter**; neither adds a runtime filter.
Both remain offline, below the main book's dailyADX30 gate, with the existing
cash/risk/lot/skip/deadline contracts.

1. **DMI break → held VWAP pullback → renewed move:** wait for a separate
   pullback that holds VWAP and a later confirmation. Bounded wait, structural
   stop and RUN exits. This differs from the previously tested opening-range
   retest: its trigger and held reference are intraday DMI and VWAP.
2. **Shock → two holding inside bars → continuation:** trade in the shock's
   direction after a pause holds its directional half, then breaks its range.
   This tests acceptance of a move instead of automatically fading it. Price
   acceptance here is only a pattern, not proof that a jump contains news.

Standalone one lot, after broker charges and Rs200 extra/trade:

| Entry | 2024 | 2025 | 2026 | Trades |
| --- | ---: | ---: | ---: | ---: |
| Held VWAP pullback | −Rs1,166 | +Rs6,600 | −Rs6,329 | 3/2/6 |
| Shock continuation flag | +Rs8,971 | Rs0 | −Rs1,352 | 1/0/1 |

**Neither passes.** Pullback's2025 profit comes from one +Rs7,302 winner on
February28; without it, −Rs702. Its three-year net is −Rs896. Shock flag's
+Rs7,620 total comes from only two trades, including one +Rs8,971 call on
November22,2024. No trade in2025 is absence of evidence, not a successful year.

Complete combined books, each year from freshRs250,000, shared sizing/brakes
and extra cost `(200+5*lots)*lots` inside the lifecycle:

| Book | 2024 | 2025 | 2026 throughOct28 |
| --- | ---: | ---: | ---: |
| Current Dev main | +Rs16,371 | +Rs5,710 | +Rs30,540 |
| Main + held VWAP pullback | +Rs12,092 | +Rs10,792 | +Rs14,046 |
| Main + shock continuation flag | +Rs25,338 | +Rs5,710 | +Rs27,020 |

The first hurts2024/26; the second helps2024, does nothing2025 and hurts2026.
No independent-arm profits were added to manufacture a combined result.
More confirmation made the patterns too rare to establish dependable earnings.
No threshold, exit or direction was retuned after these results.

## 6. Checks, boundaries and next work

- **21 new offline replays**, seven books/year: current main, both original
  raw entries and each new entry alone/combined. Original raw trades match
  O31g trade for trade; main annual net parity exact.
- **77 focused tests passed**,15 new. State ordering, separate confirmation,
  gaps, timeout, invalidation, missing data, mirrored direction, all-prefix
  and changed-tail checks. No full-suite claim; application source unchanged.
- **532 closed records** across independent arms reconciled. Maximum net
  arithmetic discrepancy <Rs0.00005; no unresolved positions or memo conflicts.
  Proper datetime checks establish signal-bar close before entry, entry/exit
  ordering, hard-flat clock, lots/day caps and daily-gate attribution.
- All source/data/daily/memo/control bindings rechecked. Daily/monthly/bucket
  partitions match all182 original trades without omissions or duplicates.
- Every one of the699 cached observation sessions was independently rebuilt
  from the sealed raw SQLite candles and compared:248/248/203 identical.
  This checks derived caches, not just the raw database's fingerprint.
- Guarded three-worker runs completed in108/104/86 seconds; no network in
  workers. No API acquisition, orders, notifications, scheduler, settings,
  migration, Production edit or deployment. Read-only availability HTTP200.
- Atlas regenerated:291 modules, no diff. Unrelated work preserved.

**Limits:** all three years are seen; candlestick fills/spreads are modelled,
lot65 is normalized, costs assumed and annual books restart. These are
comparisons under the current shipped fee/tax schedule, not reconstructions
of each historical year's dated tariff or lot sizes. These are
NIFTY single-leg comparisons, not a shared system portfolio. Existing gaps,
special sessions,56 negative-volume bars in the sealed2025 snapshot and
UNKNOWN regimes where no historical regime was logged remain. Market-data
availability and modeled profits do not establish executable fills or skill.
The2023 intraday/options exam is unchanged and unscored; existing daily warmup
is permitted. No new sample was relabelled untouched.

**Next work, in order:**

1. Keep all four O31g/O31h additions out of the main strategy. The observed
   wins are real within the model, but do not qualify a repeatable strategy.
2. Run the **existing unchanged2023 exam** for the stronger TPB-put candidates
   after verified acquisition. No new failed candidate is added to that exam.
3. For a genuine continuation/reversal router, first collect **news and
   event labels as available at each decision time**, revisions/arrival times,
   and contemporaneous price reactions. Validate on new chronological days.
   Price confirmation is observable; information type is missing here.
4. If revisiting liquidity reversal, obtain a point-in-time constituent panel,
   market/sector controls and costs before testing residual reversal. If using
   order flow, archive real bid/ask depth and trades; aggregate volume is not
   enough. A learned changepoint model needs its own frozen training protocol.
5. Separately compare a fixed surviving entry as a long option versus a funded
   debit spread, with both legs, fees, partial fills, own cash and missing-leg
   refusals. No extra borrowing/naked option selling is proposed. First build
   and verify the matched two-leg lifecycle; do not invent spread returns.

Any later pass permits prospective paper evaluation, not automatic real-money
authority. Further threshold mining on these three years will not provide the
fresh evidence this project needs.

## Reproduce and evidence

Use `python-engine/winvenv/Scripts/python.exe`. `diagnose.py` runs each year
with `O30F_YEAR=2024` or `O30C_YEAR=2025/2026`; `diagnose.py report` generates
all buckets/stability results. These shaped the hypotheses and were frozen
before their replays, not claimed as untouched outcomes.

The exact per-year commands are in [VERIFICATION.md](VERIFICATION.md); use
`run_slice.py --seconds 550` and `lab_follow.py run --jobs 3`, then
`analyze_follow.py`. Actual commands/exit codes and local raw evidence are in
`_local/`. A post-run helper report under `_local/evidence-report/` packages
the committed study, daily attribution and checked private inputs; it is a
consistency check. The actual pre-replay contract is the source/data freeze
at a45eadd. Raw prices, daily snapshots and trades are not committed. Both
research folders have their own `_local/` ignore rule, independent of the
owner's uncommitted root `.gitignore` edits.

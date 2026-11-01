# N07 — why N04 loses, what switching knew, and whether repairs pay

**The failure investigation and two fixed repair tests are complete. Registered
primary passing candidates: none. These are repeatedly seen-data research
results; no configuration is qualified for deployment or larger size.**

The new PREMIUM_AWARE_RETEST_N07 research lead returns aboutRs57,982/Rs52,023/
Rs77,135. It improves N05 net and has no larger annual closed drawdown in ALL
three studied years, also in the fixed-one-lot diagnostic. It does not dominate
N04: gives upRs2028 in2025 and raises that year's closed fall4.65%to4.77%.
The strict predeclared primary test still FAILS (t0.65 vsN04,adjustedp0.4384).
The secondary t versus N05 is1.70, also below2; do not substitute that benchmark
or declare qualification after seeing the result. Keep N04/N05 alongside N07.

Production unchanged. Original N03/N04/N05/N06 records retained. FreshRs250000
PER YEAR, normalized65-unit lot, existing2/3caps and LOW TPB1lot; not a continuous
wallet, whole-system portfolio or forecast for a small live account.

## 1. N04 and the switch are different things

N04 is the fixed MAIN+LOW-day TPB1+EFF-retest book with an early EFF exit from
30min when untrailed, progress<0.5R and liquidation net after costs<=0. Native
stops/trail/premium backstop and hard flat still apply.60min is a soft stagnation
check, not a holding cap on winners. N05 additionally requires the original
retest level to fail on a fresh completed bar before the early cut.

N06 chose N04 only on74 days2025 and90 days2026, never2024. It used prior84
same-year closed shadow outcomes, eight weeks/ten paired days/twelve challenger
and six anchor closes, one-SE weekly advantage, positive gain excluding best day,
no higher trailing closed drawdown and two consecutive decisions. Nothing in
that rule knows the next trade's outcome. See diagnosis.json's exact prior-label
cutoffs, scores, alternatives and contexts for EVERY selected N04 admission.

Those selected N04 trades were13 in2025 (6wins/7losses, netRs3749.67) and16
in2026 (9wins/7losses, netRs13780.24). Both groups were net-positive. The FULL
MAIN-anchored selector still worsened2024/25 and reached8.55%worst annual closed
drawdown: selected-trade P&L alone is not proof of selection benefit. Missing
opportunities, fallback MAIN trades and changed entry/risk history matter.

## 2. Specific N04 harm and why removing it is not free

All eleven changed exact early-exit pairs against N03 are retained. In2024,
one early cut helped and two hurt: combined−Rs4888.34 versus original exits.
OnJan16, N04 sold at net−Rs201.37; the exact original position later made
Rs6655.94, so the cut gave upRs6857.31. OnNov6 it gave upRs126.51, although
both exits were small net losses. ConverselyJan12's cut protectedRs2095.47
against a later larger loss. These later outcomes are labels, not available
advance knowledge that a losing observation will recover.

| Early N04 exit | Gross at bid | Estimated fees | Extra stress | Net before stress | Net after stress | Later delta vs original |
|---|---:|---:|---:|---:|---:|---:|
| 2024-01-12 | Rs+299.00 | Rs+96.73 | Rs+420.00 | Rs+202.27 | Rs-217.73 | Rs+2,095.47 |
| 2024-01-16 | Rs+305.50 | Rs+86.87 | Rs+420.00 | Rs+218.63 | Rs-201.37 | Rs-6,857.31 |
| 2024-11-06 | Rs+468.00 | Rs+78.08 | Rs+645.00 | Rs+389.92 | Rs-255.08 | Rs-126.51 |

All three2024 early cuts had positive premium gross and positive estimated net
BEFORE extra stress. The net-loss condition came from synthetic stress, not
demonstrated deterioration of their option bids. This is a research-model
coupling: a cost assumption affects the exit decision AND final returns. It is
not evidence of an incorrect broker fee or a Production bug. Even this seemingly
good distinction includes the helpfulJan12 cut; fixing it may sacrifice protection.

N05 already preserves the two adverse2024 recoveries, but gives up profitable
N04 cuts elsewhere. N04's exact paired improvement versus N03 in2025 is about
Rs2426 and in2026 aboutRs10117; full-account uplifts are aboutRs3961/Rs22983.
The balance is changed shared exposure/cash/risk history, not paired exit alpha.

## 3. All losses, not only the motivating examples

N04 has169 closed trades:83wins/86losses. N05 has84wins/85losses on the same
counts33/80/56 per year, with some different economic quantities/exits.

| Year | N04 SHIPPED | OR20 | EFF | TPB | N04 losing trades |
|---|---:|---:|---:|---:|---:|
| 2024 | Rs+6,583 | Rs+0 | Rs+21,968 | Rs+22,753 | 17 |
| 2025 | Rs+3,160 | Rs+3,296 | Rs-6,863 | Rs+54,457 | 41 |
| 2026 | Rs+6,456 | Rs+25,124 | Rs+7,669 | Rs+37,886 | 28 |

EFF remains loss-making in2025 under both N04 (−Rs6863) and N05 (−Rs10188).
TPB supplies most2025 profit; removing EFF globally would also give up positive
EFF2024/26 earnings and change priority/cash paths. That exclusion is not tested
or promoted in this exit-only round. Earlier studies already showed context
and sizing matter; a member's standalone result is not its portfolio effect.

The biggest closed drawdown in2025 runs fromAug12 toSep19: N04Rs13752.57/4.65%,
N05Rs14651.34/5.00%. This is not all caused by the two2024 early-cut cases.
failure-explanation.json retains every annual worst episode and member totals.

51 of N04's86 eventual losers had at least one earlier observed net-positive
snapshot (11/25/15 by year). That motivates future profit-management research;
it does NOT mean those peaks were predictable or recoverable without sacrificing
winners. No candidate receives a perfect-peak exit or unobserved intrabar fill.

Known-at-entry contexts for ALL169 wins/losses are in entry-anatomy-YEAR.json.
Closed-bar/VWAP/previous-close/spread data are separated from later outcomes:

| Year / entry relative to VWAP | Trades | Wins / losses | Modeled net |
|---|---:|---:|---:|
| 2024 / WITH_VWAP | 30 | 15 / 15 | Rs+42,691.56 |
| 2024 / BEHIND_VWAP | 3 | 1 / 2 | Rs+8,611.88 |
| 2025 / WITH_VWAP | 75 | 37 / 38 | Rs+47,157.25 |
| 2025 / BEHIND_VWAP | 5 | 2 / 3 | Rs+6,893.79 |
| 2026 / WITH_VWAP | 49 | 26 / 23 | Rs+80,665.20 |
| 2026 / BEHIND_VWAP | 7 | 2 / 5 | Rs-3,529.76 |

These are descriptive seen-data groups, not new filters. Some seemingly weak
entry categories contain substantial winners. No hindsight loss label or new
VWAP parameter was used to suppress entries in the repair candidates.

## 4. Later sizes explain part of N04's advantage

resizing-attribution.json retains identical-time/contract/price/stop/target
opportunities with DIFFERENT quantities separately from identical economics.
In2026, N04 versus N05 gains aboutRs12384.65 from two larger OR20 winners,
plusRs2152.57 on a larger TPB winner but loses anotherRs1671.63 on a larger TPB
loser. These are actual separate-book cash contributions under existing limits;
they are not a recommendation to increase limits or assume every larger trade
wins. Fixed-one-lot controls below remove much of that amplification.

## 5. Two fixed repairs, frozen before candidate replay

- A, PREMIUM_STALL: N04's SAME early eligibility, but require actual positive
  bid<=immutable entry premium. A rising premium preserved despite fee/stress
  loss continues ordinary management. No new time/risk/price buffer.
- B, STRUCT_OR_PREMIUM: SAME eligibility, then permit either original N05
  structural failure OR bid<=entry premium. This tests whether price weakness
  can recover useful N04 cuts that N05 misses while its retest level still holds.

Equality is eligible; unknown/zero/nonfinite bid cannot create an early cut.
Missing structure cannot satisfy its structural branch. All entry strategies,
priority, stops/trail, deadlines, cash and size limits stay unchanged. These
are reactive exit hypotheses, not a learned prediction of the entire day.

Source/input/diagnosis/config freeze3ec8503 preceded controls. All18 NORMAL/ONE
static annual controls match exactly. First candidate invocation then failed
BEFORE any candidate evaluation due to runner self-import; SOURCE_CORRECTION.json
preserves failure hash, zero candidate evals and identical trading-function ASTs.
Preflight-only fixe67fd64 and separately committed freeze-v2.json preceded all
candidate scores. Original freeze.json retained. No strategy/threshold/grid
retuning followed outcomes; no hidden source overwrite or discarded failed run.

## 6. Primary normal-size modeled results

| Policy | 2024 net | 2025 net | 2026 to Oct28 net | Worst annual closed fall |
|---|---:|---:|---:|---:|
| N03 original balanced | Rs+56,192 | Rs+50,090 | Rs+54,153 | 5.22% |
| N04 early stagnation | Rs+51,303 | Rs+54,051 | Rs+77,135 | 4.65% |
| N05 structural | Rs+57,243 | Rs+50,726 | Rs+61,496 | 5.00% |
| A: premium-aware N04 | Rs+57,982 | Rs+52,023 | Rs+77,135 | 4.77% |
| B: structure OR premium weakness | Rs+57,982 | Rs+52,023 | Rs+77,135 | 4.77% |

Current modeled fees/adverse candle quotes plus extra(200+5*lots)*lots are inside
the COMPLETE cash/exit/risk path, not subtracted from a selected trade list.

| Candidate vs reference, year | Full account delta | Identical-entry exit delta | Helped / hurt exact pairs |
|---|---:|---:|---:|
| PREMIUM_STALL vs STALL30, 2024 | Rs+6,678.90 | Rs+6,678.90 | 2 / 1 |
| PREMIUM_STALL vs STRUCT30, 2024 | Rs+739.58 | Rs+739.58 | 1 / 0 |
| STRUCT_OR_PREMIUM vs STALL30, 2024 | Rs+6,678.90 | Rs+6,678.90 | 2 / 1 |
| STRUCT_OR_PREMIUM vs STRUCT30, 2024 | Rs+739.58 | Rs+739.58 | 1 / 0 |
| PREMIUM_STALL vs STALL30, 2025 | Rs-2,027.60 | Rs-1,751.63 | 0 / 1 |
| PREMIUM_STALL vs STRUCT30, 2025 | Rs+1,297.50 | Rs+1,297.50 | 3 / 1 |
| STRUCT_OR_PREMIUM vs STALL30, 2025 | Rs-2,027.60 | Rs-1,751.63 | 0 / 1 |
| STRUCT_OR_PREMIUM vs STRUCT30, 2025 | Rs+1,297.50 | Rs+1,297.50 | 3 / 1 |
| PREMIUM_STALL vs STALL30, 2026 | Rs+0.00 | Rs+0.00 | 0 / 0 |
| PREMIUM_STALL vs STRUCT30, 2026 | Rs+15,639.01 | Rs+2,773.41 | 3 / 0 |
| STRUCT_OR_PREMIUM vs STALL30, 2026 | Rs+0.00 | Rs+0.00 | 0 / 0 |
| STRUCT_OR_PREMIUM vs STRUCT30, 2026 | Rs+15,639.01 | Rs+2,773.41 | 3 / 0 |

Unpaired candidate/reference cash is reported separately in repair-effects.json;
it is never attributed to the exit of a different-size or missing admission.
Both sacrificed winners and prevented losses are retained at full precision.

Specific repair trade-off:Jan16,2024 retains the originalRs6655.94 winner;
Nov6 improves the small loss byRs126.51. ButJan12,2024 exits one observed minute
later and loses anotherRs304.91 versus N04. OnFeb1,2025 waiting one observed
minute for premium weakness loses anotherRs1751.63 versus N04, plus later
cash/size-path effects bring2025 account sacrifice toRs2027.60. This answers
the owner's question directly: countering a false early cut CAN sacrifice
useful protection elsewhere. Nothing here perfectly identifies future recoveries.
Feb1,2025 was a scheduled Union Budget trading session; EVENT_FOLLOWUP.md
links the advance NSE circular and official Budget record. That lookup occurred
AFTER results and changes no rule/verdict. It suggests a future predeclared,
complete-calendar event-risk review; excluding this one losing date would be
hindsight, and the calendar does not establish this quote move's causal source.

A and B have EXACTLY identical entry/quantity/exit/price/net economics in all
nine year/sizing/cost comparisons. The structure alternative did not change any
outcome in this sample; it is not an extra independent confirmation. Retain both
identities but use simpler predeclared A as the named N07 research lead. They
are not asserted mathematically equivalent on unobserved future paths.

Primary acceptance was stricter than finding one appealing combined total:
strictly more annual net than BOTH N04/N05 and no higher annual closed drawdown
than EITHER; positive net without best trade/day;>=12annual/60total closes;
>=5/6positive periods;t>=2 versus N04 and two-arm four-week max-T adjustedp<=.05,
4096 draws seed110701. Periods explicit:2024/25 Jan-Jun/Jul-Dec;2026 Jan-May/
Jun-Oct28. Historical wins cannot authorize deployment regardless of acceptance.

| Candidate | Failed registered checks | t vs N04 | Two-arm adjusted p |
|---|---|---:|---:|
| NORMAL / PREMIUM_STALL | higher_net_than_both_each_year, closed_drawdown_no_larger_either_each_year, paired_weekly_stall, max_t | 0.65 | 0.4384 |
| NORMAL / STRUCT_OR_PREMIUM | higher_net_than_both_each_year, closed_drawdown_no_larger_either_each_year, paired_weekly_stall, max_t | 0.65 | 0.4384 |

## 7. Fixed-one-lot diagnostic

| Policy | 2024 net | 2025 net | 2026 to Oct28 net | Worst annual closed fall |
|---|---:|---:|---:|---:|
| N03 original balanced | Rs+36,439 | Rs+45,487 | Rs+51,469 | 4.01% |
| N04 early stagnation | Rs+32,922 | Rs+48,530 | Rs+57,873 | 3.99% |
| N05 structural | Rs+36,964 | Rs+46,123 | Rs+55,907 | 4.01% |
| A: premium-aware N04 | Rs+37,334 | Rs+47,391 | Rs+57,873 | 4.00% |
| B: structure OR premium weakness | Rs+37,334 | Rs+47,391 | Rs+57,873 | 4.00% |

Same cash/brakes/strategy logic, all trades at most one lot. Diagnostic only;
do not substitute this result for the registered normal-sizing verdict or
rescale whole-book P&L to a small account with different binding constraints.

## 8. Cost sensitivity, not an actual-cost claim

| Policy | 2024 net | 2025 net | 2026 to Oct28 net | Worst annual closed fall |
|---|---:|---:|---:|---:|
| N03 original balanced | Rs+65,342 | Rs+65,518 | Rs+66,271 | 5.08% |
| N04 early stagnation | Rs+67,132 | Rs+68,710 | Rs+86,576 | 4.25% |
| N05 structural | Rs+66,393 | Rs+66,790 | Rs+82,881 | 4.66% |
| A: premium-aware N04 | Rs+67,132 | Rs+68,710 | Rs+86,576 | 4.25% |
| B: structure OR premium weakness | Rs+67,132 | Rs+68,710 | Rs+86,576 | 4.25% |

Only synthetic extra stress removed; current modeled fees and adverse candle
quotes REMAIN, as do normal caps and all risk gates. Full paths rerun because
cost changes early-exit eligibility, realised equity and later sizing. This
setting is not selected as better economics or represented as actual fills.
Both repairs are also economically IDENTICAL to N04 in every no-extra-stress
year. This strongly locates the change in stress-induced exit behavior, rather
than establishing a new predictive market edge. Actual execution-cost evidence
is needed to know how much of that distinction matters in a real account.
Production read-only inventory from N06 has paper closes only and no real
execution-event/run evidence; calibration to actual costs remains unavailable.

## Verification and limitations

110 focused checks (99research/11native),45 fresh annual books,18 exact controls;
2545 closed financial/immutable-admission identities,
5090 archive entry/exit prices, 345 retest paths and 345 independent
first-exit lifecycles/17213 observations/478 structural reviews.
All45 cash paths/15 weekly vectors/two primary resampling comparisons checked
independently. Prior699 raw/cache checks reused by identical inherited hashes,
not claimed newly executed;56 original2025 negative-volume bars and known gaps
retained. No historical real depth, IV/Greek attribution or perfect monitoring
invented. Closed drawdown is not intratrade/gap risk or a future guaranteed cap.

Sources/context in SOURCES.md: Kaminski/Lo's author manuscript studies the
conditional benefits/costs of stop rules, not our intraday option policy;
Zerodha describes time decay all else equal. Our snapshots cannot identify
whether a particular premium loss came from theta, volatility or quote effects.

## Successor checkpoint and remaining work

Read FNO_RESEARCH_FAILURES_N07 md/json plus all FOUR earlier checkpoint records.
Preserve each saved identity and all primary/diagnostic failures. This is the
owner-authorized exploratory failure/repair round after N06, still seen-data.
No historical improvement proves day prediction, reliable future switching,
profitable partner advice or readiness for a larger real allocation.

Next: prospective keyed shadow admissions/quotes/closed outcomes for every
compared policy; explicit real fill/order/charge/cash reconciliation when
authorized evidence exists; freeze future sample/review BEFORE scoring. Keep
missing/partial/unreconciled evidence unavailable.2023 remains deferred until
explicitly requested. No automatic risk/lot increase, deployment, broker order,
Telegram message or Production action. All code/docs are Dev research only.
See VERIFICATION.md for exact commands, timings, identity and environment limits.

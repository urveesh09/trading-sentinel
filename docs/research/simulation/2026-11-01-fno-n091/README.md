# N09.1: budget the exposure, preserve N08's clocks

November 1, 2026. Dev research only. No application, environment, broker, orders,
Telegram, capital authority, restart, deployment or Production change.

**CUSHION retains 94.0% of N08's modeled aggregate annual profit, with a
37.0% smaller worst day.** It ends the no-reset continuous account at
₹384,310. Read the frozen verdict below before treating this as a lead.
This is a loss-control hypothesis, not a new direction predictor. It does not
turn 2023 profitable, and all four years were already seen.

## The two concrete N09 issues

1. **Sizing comparison changed two things.** N09 S_VOL sets low_two_lots_before
   to1440, whereas N08 uses720. It both applies volatility sizing and expands
   the time window where a second lot can be considered. This is a research
   design confound, not a discovered live-order bug. VOL_CLOCK preserves all
   N08 clocks and only reduces size. Do not describe S_VOL as a pointwise size
   reduction of N08 on identical state.
2. **The whole-year SHADOW stress diagnostic used the current outcome.** In
   N09 stress_years.path_end, paper.append(net) precedes the restart decision
   and that same net can be booked. The corrected event proxy only permits
   labels whose exit is strictly before the new entry. A synthetic regression
   demonstrates the difference. The original results remain unchanged. This
   finding does not invalidate the separate full N09 account replays, which
   use prior timestamps correctly.

## What N09.1 changes

- VOL_CLOCK: N08 plus N09's prior-day ATR-versus-prior250-session median sizing,
  only allowed to reduce the native count. The before-noon low-day two-lot
  ceiling and14:00 last entry stay intact. Missing volatility means at most1lot.
- CUSHION: VOL_CLOCK plus full remaining premium/current fee/stress reservation
  above a floor initially85% of starting equity. The floor ratchets with closed
  high-water equity only when already-open exposure can fund it; it never falls.
  Choose the largest whole lot count accepted by the native planner that fits.
  Recompute a smaller native plan before creating the position. If even1lot
  cannot fit, decline the admission; continue every existing exit.
- Both: N08 signals, member priority, exits, expiry rules, own-cash restrictions,
  original risk budgets and hard deadlines remain. At most2lots. No averaging
  down, new option selling, margin, new capital or automatic halt reset.

The reserve explicitly allows the option to lose its entire premium; it does
not assume an SL fills at its requested price. The historical model still lacks
actual depth, broker fills and operational failures, so this is no live guarantee.

**Capital scope matters:** these accounts start at ₹2,50,000. At ₹15,000 an 85%
floor initially leaves only ₹2,250 for full premium plus fees/stress. A whole
eligible lot can exceed that amount, so applying CUSHION unchanged could reject
most or all entries. It is not a drop-in change for the small live trial and
does not justify increasing capital or relaxing its approved risk limits.

## Fresh annual accounts

Fresh ₹2,50,000 each year; lot of 65 throughout;2026 ends October 28. Current fee model,
modeled adverse bid/ask and extra stress(200+5×lots)×lots are inside each cash path.
The sum is a comparison of separate experiments, not one investor's return.

| Book | 2023 | 2024 | 2025 | 2026 | Sum | Worst annual closed fall | Worst day |
|---|---:|---:|---:|---:|---:|---:|---:|
| N08 | −₹37,581 | +₹76,294 | +₹58,647 | +₹104,924 | +₹202,284 | 15.08% | −₹9,720 |
| S_VOL | −₹37,974 | +₹70,317 | +₹50,442 | +₹108,643 | +₹191,428 | 15.24% | −₹6,127 |
| VOL_CLOCK | −₹37,974 | +₹76,294 | +₹52,320 | +₹104,924 | +₹195,564 | 15.24% | −₹6,127 |
| CUSHION | −₹32,684 | +₹76,294 | +₹46,738 | +₹99,870 | +₹190,218 | 13.13% | −₹6,127 |

## One account, no fresh annual capital or loss-budget reset

The original 15% initial-capital halt remains for every book; CUSHION adds a
stricter funded admission budget. Closed cash/risk history and CUSHION state
carry through year boundaries. This is a full candle-book replay with
its own admissions, not a sum of annual accounts or fixed-trade scaling.

| Book | Ending equity | Closed fall | Trades | Year contributions2023/24/25/26 |
|---|---:|---:|---:|---|
| N08 | ₹212,419 | 15.08% | 56 | −₹37,581 / +₹0 / +₹0 / +₹0 |
| S_VOL | ₹212,026 | 15.24% | 66 | −₹37,974 / +₹0 / +₹0 / +₹0 |
| VOL_CLOCK | ₹212,026 | 15.24% | 66 | −₹37,974 / +₹0 / +₹0 / +₹0 |
| CUSHION | ₹384,310 | 13.13% | 202 | −₹32,684 / +₹23,723 / +₹49,770 / +₹93,501 |

## Frozen verdict; no moved goalposts

- **VOL_CLOCK:** risk route FAIL (failed: continuous_end_not_worse, annual_drawdown_not_worse); profit route FAIL. This is an all-seen development screen.
- **CUSHION:** risk route PASS; profit route FAIL. This is an all-seen development screen.

Risk route: retain>=90% aggregate profit; worst day>=20% smaller; worst annual
closed fall no larger;2024-26 positive; continuous end>=never-restartedN08;
double-extra-cost aggregate positive. Profit route separately requires more
aggregate profit/no worse worst day/worst annual fall/2023/no worse continuous
end/positive double cost. No result qualifies a strategy for deployment.

**Opportunity cost:** CUSHION sacrifices ₹12,066 of aggregate
annual profit. Its 2025 closed fall is 4.85%
versus N08's 4.70%: it does not
dominate N08 on every year's risk. The risk criterion concerns the worst annual
fall, as predeclared. All per-year returns and costs remain visible.

## Where the difference comes from

Exact match requires entry timestamp, contract, signal bar, original stop and
target. Changed quantity is shown separately from removed/added opportunities.
New/missed trades can follow changed cash and native brakes; these are not
proof of new predictive signals. Each row's components reconcile to its delta.

| Book/year | Matched | Resized | Matched delta | Missed winners/count net | Avoided losses/count net | Added wins/losses | Total delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| VOL_CLOCK 2023 | 56 | 11 | +₹8,359 | 0 / +₹0 | 0 / +₹0 | 2 / 8 | −₹393 |
| VOL_CLOCK 2024 | 29 | 0 | +₹0 | 0 / +₹0 | 0 / +₹0 | 0 / 0 | +₹0 |
| VOL_CLOCK 2025 | 75 | 15 | −₹6,327 | 0 / +₹0 | 0 / +₹0 | 0 / 0 | −₹6,327 |
| VOL_CLOCK 2026 | 51 | 0 | +₹0 | 0 / +₹0 | 0 / +₹0 | 0 / 0 | +₹0 |
| CUSHION 2023 | 56 | 11 | +₹8,359 | 0 / +₹0 | 0 / +₹0 | 1 / 4 | +₹4,897 |
| CUSHION 2024 | 29 | 0 | +₹0 | 0 / +₹0 | 0 / +₹0 | 0 / 0 | +₹0 |
| CUSHION 2025 | 74 | 15 | −₹6,327 | 1 / +₹5,582 | 0 / +₹0 | 0 / 0 | −₹11,909 |
| CUSHION 2026 | 51 | 1 | −₹5,054 | 0 / +₹0 | 0 / +₹0 | 0 / 0 | −₹5,054 |

## Costs and uncertainty

These are separate complete replays: zero/double refers only to EXTRA stress.
Current charges and modeled adverse quotes remain; none measures actual costs.

| Book | Zero extra stress, annual net sum | Double extra stress, annual net sum |
|---|---:|---:|
| N08 | +₹252,981 | +₹163,687 |
| VOL_CLOCK | +₹249,919 | +₹159,802 |
| CUSHION | +₹246,401 | +₹152,165 |

- VOL_CLOCK: paired weekly t -0.543; 4-week block bootstrap total-delta interval −₹28,717 to +₹13,539. Descriptive, all-seen; not a new significance/qualification pass.
- CUSHION: paired weekly t -0.861; 4-week block bootstrap total-delta interval −₹36,691 to +₹10,555. Descriptive, all-seen; not a new significance/qualification pass.

## Repeated bad-year diagnostic

All256 ordered four-year sequences with replacement, fixed1lot N08 no-brake
admission universe. Entry/exit clocks are preserved; still a PORTFOLIO_PROXY:
no regenerated market decisions, risk-sized lots or complete native brakes.
CUSHION here is the floor component at1lot; VOL_CLOCK cannot change1lot size.
Do not compare these rupee levels to the full continuous replays above or infer
probabilities of future ruin from256 reused historical sequences.

| Rule | Worst ending equity | Lowest equity | Median ending equity |
|---|---:|---:|---:|
| NONE | ₹211,290 | ₹211,290 | ₹367,877 |
| ANNUAL | ₹128,867 | ₹128,867 | ₹367,877 |
| SHADOW | ₹130,136 | ₹130,136 | ₹367,877 |
| CUSHION | ₹215,291 | ₹214,546 | ₹342,954 |

CorrectedSHADOW helps54,
hurts12, is unchanged on
190 versusNONE. CUSHION also sacrifices
strong paths: hurts100 of256. Its
maximum opportunity cost is−₹133,400.
Protecting capital has a real price; no selective reporting of the weak years.

## Verification and limitations

- Pre-score source 4245670, exact-control/stress reportingc5351a7.
  Frozen2hypotheses;60 completed annual books;12 exact controls/675 old trades.
  An audit caught fresh terminal states keyed only by policy; later independent
  years overwrote earlier terminal snapshots. Original per-trade/admission
  evidence and unique continuous state survived. Post-score correctionc6bbcb9
  and freeze-v2 are disclosed in SOURCE_CORRECTION.md/json. All actual trading
  function ASTs/config/rules/acceptance stayed unchanged.24 fresh-namespace
  replays exactly reproduce old economic trades AND complete decision/admission
  receipts and retain every full-window terminal state.84 executions total,
  not84 independent experiments; the original60 remain the scored experiment.
- 55 focused checks:21 N09.1,23 N09,11 native exit/replay. No full-suite claim.
- A subsequent checker-only comparison used sub-paise tolerance against the
  native two-decimal opening display. CHECKER_CORRECTION.md documents the
  0.0029-rupee example and one-paise display comparison; economics unchanged.
- Independent audit:{"annual_books": 60, "budget_decisions": 1904, "financial_lifecycles": 2798, "funded_full_premium_admissions": 846, "immutable_budget_admission_bindings": 1571, "independent_floor_clock_reconstructions": 1179, "persisted_cash_state_checks": 32}.
  Price checks:5596 modeled entry/exit prices.
- 945 source and972 cached-input/old-receipt hashes bound before scoring.
  Frozen cached candles are reused; no fresh broker data/2022/download calls.
- Normalized65-unit lots/current fees are NOT dated historical broker returns.
  Original clipped candles and known gaps remain; at least one old N08 trade
  touched a clipped session. No IV/depth/Greeks explanation is invented.
- Drawdowns are CLOSED-equity drawdowns. No claim about worst intratrade marks,
  future loss limits or guaranteed trade execution. No out-of-sample claim.
- N08/N09/checkpoints/application source preserved. Production stays unchanged.

## Next

Retain N08 as the aggregate-profit reference. Treat any passing N09.1 risk screen
as a candidate for prospective evidence, not a replacement proved to make money.
Freeze and build keyed broker-free forward shadows, recording every budget
decision, missed winner, costs, cash and floor. Test actual charges/fills only
when authorized observations exist. Keep2022 unopened until a complete test
rule and coverage contract are fixed. No automatic live floor reset or lot rise.

Reproduction/commands: VERIFICATION.md. Detailed machine evidence: results.json,
audit-results.json, control-parity.json, price-audit-*.json and stress-results.json.
Mechanism references and limits: SOURCES.md. OriginalPLAN and freeze preserved.

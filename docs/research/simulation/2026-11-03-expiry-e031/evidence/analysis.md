# E03.1 — smaller losses, a modest fitted improvement

November 3, 2026. **Built in Dev as a disabled paper experiment. Not deployed,
not financially qualified. It does not substantially surpass E03.** Both test
years were already used to design E02 and E03; the results below are fitted.

## What changes

E03.1 keeps E03's entry, strike choice, lots, ticket/day reserves and runner.
It changes two things **before** the split runner starts:

1. Initial stop: **35%**, from 40%.
2. When the observed peak bid reaches **1.5x entry**, raise the trigger floor
   to at least **1.1x entry**. The existing trailing stop can raise it further.

Everything else stays E03's: up to three lots inside Rs 1,250, at most two
tickets with Rs 2,500 original premium/fees reserved per day, own Rs 25,000
cash, drawdown brakes, four-strike reach limit, eight-minute clock, partial
sale at 2x and the existing runner thereafter. No risk increase or leverage.

**A stop is a trigger, not a guaranteed sale price.** Fees and gaps can still
turn a ticket with a raised floor into a loss. The runner is financed by a
partial sale; calling it "free" does not establish a guaranteed profit. This
matches the exchange's warning that rapid price moves can defeat orders intended
to limit loss. [NSE risk disclosure](https://nsearchives.nseindia.com/content/circulars/insp11184.htm).

## What the same cash book earns in the model

NIFTY 105 expiry afternoons in 2024/2025, current 65-unit lot and current native
fees, next-bar executions. **Cash and brakes continue through the year boundary;
there is no annual refill/reset.** These are modelled paper results, not returns
that could have been earned with each historical year's lot/tax schedule.

| Continuous 2024 + 2025 | E03 | E03.1 |
|---|---:|---:|
| Ordinary fills, after fees | +11,956.35 | **+12,426.71** |
| Adverse fills, after fees | +11,114.83 | **+11,497.60** |
| Severe next-high buys / next-low sells | -3,153.55 | **-3,234.08** |
| Worst day, ordinary | -568.26 | **-478.01** |
| Worst day, adverse | -562.38 | **-537.55** |
| Realized drawdown, ordinary / adverse | 1,464.76 / 1,630.42 | **1,373.93 / 1,387.14** |
| Sampled marked drawdown, ordinary / adverse | 1,929.68 / 2,178.45 | **1,838.85 / 1,935.17** |
| Ordinary net without best day | +6,106.39 | **+6,576.75** |
| Closed tickets, ordinary / adverse | 41 / 41 | 41 / 41 |
| Charges, ordinary | 2,099.90 | 2,100.79 |

Ordinary extra profit is **Rs 470.36, about 4%**, from six sessions; all six
improve in that scenario. Remove its biggest incremental day and the extra is
Rs 288.71; remove the two biggest and Rs 214.10 remains. This extra does **not**
come from extending the March 28 hero: that trade is unchanged. Adverse extra
profit is Rs 382.77, with five improved and one worsened session; Rs 168.68 remains
without its largest increment. Most days still have no entry. Twenty of the 41
ordinary tickets lose; the strategy is not a steady daily-income machine.

Per-year ordinary/adverse, each started independently at Rs 25,000:

| Year | E03 | E03.1 |
|---|---:|---:|
| 2024 | +8,567 / +8,132 | **+8,898 / +8,271** |
| 2025 | +3,389 / +2,983 | **+3,529 / +3,226** |

The positive ordinary/adverse totals happen to equal the continuous totals here.
**Severe totals do not:** independent annual E03 books lose Rs 3,273; the
continuous book loses Rs 3,154 because its brakes inherit 2024's losses. Never
mix these capital bases when comparing strategies.

## What failed, and what it teaches us

The bounded search recorded **55 individual mechanism changes and 149 new unique
combinations** with two seeded genome runs. The earlier studies' thousands of
trials still count as prior fitting; this is not a fresh 204-trial discovery.
All trials and the two pre-stress finalists are retained.

| Idea | Observed result / decision |
|---|---|
| Stop a stalled ticket after 2–5 minutes | Several later winners start quietly; most settings make 2025 negative. Rejected. |
| Chase less at entry | Misses profitable moves as well as losers; all four tighter caps underperform. Rejected. |
| Extend a profitable ticket while spot and future agree | Helps 2025, hurts 2024. A combined finalist looks better when years reset, but loses Rs 722 ordinary / Rs 945 adverse **relative to E03** with continuous cash. Rejected. |
| Tighten stops aggressively to 20–30% | Shakes out winners; the 20% stop cuts 2025 adverse net to Rs 456. Rejected. |
| Longer trend/futures confirmation | Fewer entries without a consistent benefit. Rejected. |
| Pick the best rule on one year, trade the other | Both cross-year selections underperform E03. Expanding quarter selections also usually trail it. No adaptive selector shipped. |
| Modest 35% stop + winner floor | Smaller, more distributed gain; retained only as the E03.1 paper hypothesis. |

Some stopped tickets later become heroes. On September 12, 2024 a losing ticket
later reaches about 6.6x its entry. That is visible **afterward**; this study did
not find a causal rule that distinguishes it from the many tickets that keep
decaying. Removing stops because of that example is not an improvement.

## How far to trust E03.1

- **Both years are seen.** No untouched pass, profitability promise or zero-loss
  claim. NIFTY 2023 remains protected; no new download/API request was made.
- **Severe execution is negative, and slightly worse than E03.** With one extra
  minute before both entry and exit, E03.1 also underperforms E03 in 2024 despite
  remaining positive. Timing sensitivity is not solved.
- **Local improvement is mixed:** 8 of 16 coarse neighbours pass the full strict
  improvement screen. Several preserve profitability but do not beat E03.
  The exact 35% stop and 1.1x floor are hypotheses, not universal constants.
- **Bootstrap is conditional:** four-expiry block resampling gives a 95% interval
  of about Rs 101–947 ordinary / Rs 23–905 adverse for the incremental gain.
  Those intervals exclude parameter-selection uncertainty and cannot establish
  statistical significance after all the searches on these same years.
- **Higher friction:** keeping the original entries/exits/quantities and adding
  1% **plus** one tick to each side leaves E03.1 at +10,995 ordinary / +10,072
  adverse. This fixed-trade sensitivity does not rerun brakes or claim fill parity.
- **Native warmup:** starting from the actual 12:59 recording window, signals
  can first occur about 13:11. E03.1 remains positive and above E03 in both
  years/scenarios. Minute candles still differ from ten-second sampled live bars.
- **Coverage:** NIFTY 2024/2025 recorded minute chains only, with four-strike
  selection and a 20%-of-bar-volume capacity proxy. No historical bid-depth,
  queue or intraminute execution proof. Existing 2026/SENSEX files cannot replay
  the entire strike-selection universe; neither is newly qualified here.
- **Five existing 2026 recordings:** the same quote-to-bar proxy used by E03
  gives one ticket, +Rs 93.54 ordinary / +Rs 64.32 adverse, for both versions.
  These dates were already inspected, the adapter approximates execution, and
  E03.1 was disabled. This is a sanity check, not new forward paper evidence.

## Implementation, verification and status

New paper identity `expiry-e031-v1`, play `E031`, own
`<DB_PATH>.expiry-e031.db`, `EXPIRY_E031_SHADOW_ENABLED=false`. It reads the same
existing archive; no added provider request, order, message or ledger write.
Each ticket stores its own policy. Flag-off still manages existing exposure;
restart preserves cash and daily reserves. E02/E03 settings and behavior remain
unchanged; N11/N11T, primary A/B/C and Production are unchanged. No `.env` edit or
migration of existing databases. The new store is created only by later enable
or isolated tests.

Forward comparisons must report both the whole separate books and matched
tickets: an earlier exit can change subsequent admission/cooldown or drawdown
brakes, so identical entry *rules* do not guarantee identical future tickets.

- Baseline: all **99** E03 position/event histories and all day/summary records
  reproduce exactly across the independent years and three fill scenarios.
- Native paper exits and fees: **391 position replays, 407 exit slices, zero
  mismatches**, including continuous books and severe fills. Repeated paths are
  counted as replays, not 391 independent market trades. Network connections are
  explicitly blocked in this audit; no attempt occurred.
- Focused checks: **43 passed** (E02, E03, E03.1 and causal mechanism tests).
- Full engine suite: **6,118 passed, 4 skipped, 53 warnings**, 694.61 seconds,
  exit 0. Existing deprecation/AsyncMock warnings and the deliberately broken
  Penny writer fixture's shutdown logging error are retained, not suppressed.
- Atlas regenerated: 295 modules.

A stress-label mistake is preserved and corrected: the first fixed-entry stress
used `max(1%, tick)` but its description said `1% + tick`. The stronger intended
calculation is in `friction-audit-v2.json`; no strategy or finalist was changed.

Next: a separately authorized GitHub rollout could collect paired E03/E03.1
paper tickets and execution evidence. At least 20 **new closed tickets**, spread
across regimes, would support another review; that count alone does not prove an
edge. E03.1 is not a replacement for C, and no switch is turned on by this study.

Full record: [study and continuation](research/simulation/2026-11-03-expiry-e031/README.md).

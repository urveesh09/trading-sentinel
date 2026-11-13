# SN92–SN100: frozen plan (written and committed before any scoring run, Nov 13, 2026)

Owner (Nov 13): take the other agent's SN92–SN100 proposal and component review, "develop that, test it for various fixed or growth wallets, wallet limits, wallet caps, various starting amounts ... and let's see if it improves drastically the current Gold."

Inputs read first: `docs/SN92_SN100_RESEARCH_PROPOSAL.md`, `docs/SN_COMPONENT_RESEARCH_REVIEW.md` (other agent, uncommitted, not edited here), `docs/SN_STRATEGY_HISTORY.md`, `docs/SN_TESTING_PROCEDURE.md`, `docs/SN_PROBLEM_STATEMENT_EMPTY_DAYS.md`, N012 rounds 14/18/21/22/30/31/32–35.

**New fact found while planning:** the component review assumed no intraday constituent data exists. It does: the Oct 5 Kite snapshot (`docs/research/kite/2026-10-05-momentum-h1/_local/raw`, 15-minute bars, Jan 1 – Jul 31 2026, ~490 NSE names incl. every current NIFTY 50 name) and Production's read-only `intraday_cache` export (`docs/research/simulation/2026-11-08-momentum-m01/_local/prod_15m_aug_nov.csv.gz`, 15-minute, Aug 11 – Nov 6 2026, bars to 14:30). Momentum M01 used them for stock trading; no NIFTY-options rule has used them. SN96 tests the component idea on them.

Everything is research only: no runtime code, no Production, no Kite/ICICI calls, frozen Gold harnesses untouched (`gold_v5.py` verified first).

## Common rules (all SN92–SN100)

- **Data:** the 742 sealed non-expiry 1-minute sessions (2023 – Oct 28 2026, `sn01` caches), N11 + R0.85 stored entries, daily ADX (`sn06`), India VIX daily closes (N012 `_local/india-vix`), the 15-minute stock bars above, SN10's 56 expiry days of 10-second opening-ATM options. All seen data: results are development evidence; the selection procedure is what is scored.
- **Fills:** the house model (buy at the ask, sell at the bid, half the P75 spread, stop-market on the bid low with gap-through at the open, stop wins ties, time exits at the close bid, flat 15:10). A trade needs a printed minute at entry. Entry is at the signal minute's close (the house convention); robustness adds 1 minute of delay.
- **Costs:** `fno_costs` (today's Zerodha NFO rates) on every leg + ₹205 per lot per trade (single leg). Multi-leg: ₹100 per leg-lot (house) and also ₹205 per leg-lot (strict). Robustness at +₹400.
- **Day limit:** 20% of the wallet, as a stop price that spends the remaining room after charges and stress. One position at a time.
- **Causal Gold-free day:** yesterday's daily ADX < 30 (Gold can still trade such a day: 65 of 582 had Gold trades). "Gold-empty" (the day's final Gold outcome) is used only for attribution tables, never for a rule.
- **Selection:** leave one year out (`sn03_run.loyo`, objective "profit") over the small fixed grid of each study, with the same procedure run on the controls. Chronological split where only 2026 data exists (SN96, SN98).
- **Pass (companion):** LOYO held-out net > 0 at the house stress, ≥ 3 of 4 held-out years positive, held-out beats the direction NULL and the matched baseline; then +₹400 and 1-minute-late entries stay positive. Anything else: NOT PROVEN.
- **Pass (Gold change, SN97a / SN99):** LOYO held-out sum beats v5 at C ₹30k and G3, and the held-out year-by-year result is ≥ v5 in at least 3 of 4 years at both; worst day not worse than v5 by more than 10%; survives +₹400 and 1-minute-late entries.
- **Wallets:** every study reports A ₹15k 1 lot, B ₹20k 1 lot, C ₹30k sized, G0/G2/G3/G5 from ₹15k, and (SN99/SN100) the deployed ₹30k start fixed and growing (stop after 3 and 5), plus starts ₹15k/₹20k/₹30k/₹50k growing (stop after 3). Per year: net, refilled, won / lost / no-trade days, worst day; net at the end = won − refilled.

## SN92 — where the money goes (description, no pass/fail)

1. Gold v5's trades at A and C: per setup (SHIPPED / OR20 / EFF / TPB) × book (N11 / R0.85) × side × year: trades, net, net per lot, win %, share of the best 5 trades; costs split into spread (entry ask − close, half spread at exit), charges, stress; how much the extension, ITM and scale-in contributed.
2. The empty-day opportunity map: at 09:45, 10:30, 12:00 and 13:30 on every session, buy the ATM call and the ATM put (1 lot, at the ask) and sell at the bid after 15 / 30 / 60 / 120 minutes and at 15:10. Report, for causal Gold-free days split by the attribution label (Gold-empty / Gold-traded) and for ADX ≥ 30 days: mean net of the call, the put, the straddle, and the hindsight best side (a ceiling, not a strategy); the share of cases where even the right side nets > 0; the index move needed to cover costs.

## SN93 — slow up-drift specialist (calls, causal Gold-free days)

At completed 15-minute block ends from 10:29 to 14:00: the drift state = at least `need` of the last `N` blocks closed up, progress since the open ≥ `prog`, the futures VWAP rising over the block and the index above it, and the pull-back from the session high ≤ 40% of the high's advance over the open.
- Entry `simple`: buy the ATM call at the first block end in drift state. Entry `pullback`: once in drift state, the first later minute (while the state holds at each block end) whose low touched EMA21 + 0.25 ATR and whose close is above the prior minute's high and above EMA9.
- Exits: `E1` index stop and trail 4 × 1-minute ATR from the best; `E2` 6 ATR plus exit at a block close below the futures VWAP. Both: 25% premium backstop, day limit, flat 15:10. One trade a day.
- Grid: (N, need) ∈ {(4,3), (6,4)} × prog ∈ {0.15%, 0.30%} × entry ∈ {simple, pullback} × exit ∈ {E1, E2} = 16.
- Controls: direction NULL (same day and minute, random side); matched days (a call at the same minute on a random other Gold-free day of the same year); plain calls at 10:30 and 12:00 on every Gold-free day with each exit.

## SN94 — confirmed failed breakout (both sides, causal Gold-free days)

Opening range 09:15–09:45. The first close beyond it by `buf` × ATR after 09:45 is the break; a close back inside within `W` minutes is the failure (the break's extreme X recorded).
- `retest`: after the failure, within 30 minutes, a minute that comes within 0.5 ATR of the broken edge without closing beyond it, then a close beyond the prior minute's low/high in the fade direction; entry there. Without retest: entry at the close back inside. Cancelled if price closes beyond X first.
- Trade toward the interior: target = the range middle (`mid`) or the opposite edge (`far`); index stop X + 0.5 ATR; 90-minute clock; 35% premium backstop; flat 15:10; skipped when the target is < 20 index points away (the cost hurdle ≈ 8–9 points).
- Grid: buf ∈ {0, 0.5} × W ∈ {15, 30} × retest ∈ {yes, no} × target ∈ {mid, far} = 16.
- Controls: the unconditional fade (fade the first break at the break minute, same exits), direction NULL.

## SN95 — remaining movement against the option price

At clock t ∈ {10:00, 11:00, 12:30}, ATM strike K: implied per-minute σ from the straddle mid, σ_imp = P / (0.7979 F √τ), τ = trading minutes left to expiry + 125 minutes per night (a fixed declared overnight allowance). Two "cheapness" ratios: `R_today` = σ of today's 1-minute index returns since 09:20 / σ_imp; `R_atr` = yesterday's daily ATR% / (1.6 √375) / σ_imp. Admission by a causal expanding quantile (all prior sessions at that clock, ≥ 60 of them).
- Buy: the ATM straddle (1 lot each) when the ratio is in the top q; sell: an iron fly (short ATM straddle, long ±200 wings, defined risk) when in the bottom q. Exits: hold to 15:10, or 60 minutes; day-limit stop on the combined position.
- Grid per side: feature ∈ {R_today, R_atr} × clock (3) × q ∈ {0.20, 0.33} × exit (2) = 24; 48 total. Scored on causal Gold-free days (main) and all days.
- Controls: the same structure, clock and exit every day (unconditional); random admission at the same rate (NULL).
- Margin for the fly is not broker-verified (max-loss proxy); labelled.

## SN96 — components inside NIFTY (2026 only, 15-minute)

Panel: today's NIFTY 50 names (`SN96_NAMES` in the script; a partial-history pilot because membership is today's). Weights fitted by non-negative least squares of NIFTY's 15-minute returns on the names' returns over Jan 2026 only (causal for everything after).
Features at each completed block (10:00–14:00): index block return and return since the open; breadth = share of names up − share down (block and since open); weighted agreement = Σw r / Σw|r|; bank/financial contribution minus the rest; largest single share; 3-block breadth persistence.
1. **Information test:** development Feb – Apr 2026, test May – Oct 2026 (chronological). OLS of the next 30 (and 15) minutes' index return on the index-only features, then with the component features. Report test-period error and correlation, the incremental correlation of residual breadth (breadth not explained by the index's own move), with a day-clustered bootstrap 95% interval.
2. **Trading test:** at block ends 10:00–14:00 on causal Gold-free days: call when residual breadth ≥ the development 80th percentile and the index is up since the open; put mirror (`broad`); and `diverge`: put when the index is up since the open but residual breadth ≤ the 20th percentile (call mirror). Exit 30-minute clock or a 3-ATR index trail. 1 lot. Controls: the same rule on the index's own block return (no components), direction NULL. Scored once on May – Oct 2026.
3. **Exit test (description):** Gold's 2026 trades held through block ends: exit when weighted agreement against the position for 2 blocks.

## SN97 — futures volume and scheduled events

1. **Gold sizing by futures volume:** rel_vol = futures volume of the 15 minutes before entry / the median of the same clock window over the prior 20 sessions. Size rules: full lots when rel_vol ≥ x (replacing the volatility-day rule), when both, or when either; x ∈ {1.2, 1.5, 2.0} = 9 variants vs v5, LOYO, the Gold pass rule.
2. **Companion confirmation:** SN93's and SN94's per-year picks with rel_vol ≥ x at entry (x ∈ {1.2, 1.5}).
3. **Events (description):** Gold v5 on RBI decision days (N012 round 31's dated list) and Union Budget days. RBI follow/fade was already tested (N012 R31: follow negative without its best five); no new event rule.

## SN98 — expiry mornings priced (10-second, 56 days)

Buy the opening-ATM straddle at 09:20 when the price ratio PR = straddle / (index × yesterday's ATR% × √(225/375)) is low (`cheap`, below the choose-half median) or always; or one leg in the direction of 09:15–09:30 when cheap. Exits 13:00 or +40% of the combined premium. Day limit. Choose on Sep 2025 – Mar 2026, score on Apr – Sep 2026 (SN10's split; the score half was seen once by SN10, so this is development evidence only). Random NULL.

## SN99 — Gold's capital allocation

Variants on top of v5 (only sizing changes, so A and B are unchanged by construction):
- per-setup: full lots only for a subset of setups (all 15 non-empty subsets of SHIPPED/OR20/EFF/TPB), else half (min 1), on volatility days as v5; LOYO picks the subset on 3 years;
- drop one setup entirely (4);
- option cheapness at entry: full lots when `R_today` at the entry minute ≥ / ≤ the causal median, with or without the volatility-day rule (4);
- India VIX: full lots when yesterday's VIX ≥ / ≤ its prior 60-session median, with the volatility-day rule (2);
- C wallet equal capital: one 2-ITM lot instead of 2 ATM-ish lots on volatility days (1).
Gold pass rule above. Robustness for any pass: +₹400, 1-minute-late entries.

## SN100 — one shared account

Gold v5 (plus any SN97/SN99 pass) with each companion's per-year LOYO picks (SN93, SN94, SN96 if it passed its information test) inside one chronological ledger: Gold has priority; a companion position is closed at the bid at the minute a Gold signal arrives, then Gold enters; companion losses consume the day room; one position at a time. Report every wallet in the list above, Gold alone vs combined, and the companion's attribution on Gold-empty days. Pass: combined held-out net > Gold alone at ₹30k fixed and ₹30k grow-3, worst day inside the 20% limit. A forward check is frozen only for something that passes.

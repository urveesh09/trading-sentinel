# November 5 F&O and expiry follow-up

## Scope

Compare deployed regular N11 and N11T, investigate winner management and earned exposure, and compare E03.2 with an independently funded legacy breakout challenger. November 5 is a seen diagnostic session. Use Production snapshots read-only, and keep paper results separate from partner cash and the defined-risk book. No live or deployment changes.

## Contracts

- NIFTY 2022 is opened once for the unchanged N11 and final N11T under the existing historical candle model. Add the original N11 exam controls where the same window and inputs support them. Use the June to December observations already available, preserve gaps, and report the registered 200-session target separately. The candidate must have higher net after fees and fixed stress, positive net excluding its best incremental day, no worse closed drawdown or worst day by more than ₹1,000, and at least ten actual tolerance decisions for a directional conclusion. A smaller sample is a partial comparison. Use only earlier paper outcomes and earlier daily bars. No variant selection on this window.
- Regular F&O exit challengers on seen evidence are a trend-dependent profit lock and a two-lot bank-and-runner. Use native hard stops, clocks and fee schedule. Additional lots must meet the same capital, concurrency, premium and stop-risk limits. Compare the existing N11 earned lot with at most one causal continuation rule at a time. Where only held-position observations exist, admit no new trade and report exits with missing tails as unresolved. Baseline replay must match recorded reasons, timestamps, and P&L before reporting a paired result.
- Expiry baseline replays E03.2 from 10-second sampled packets and independently reconciles today's legacy A result. Diagnose signal, option eligibility and executable fill separately. Compare with a single A-style breakout/retest at the same ticket reserve and execution rules. Test a second version only after documenting the first version's failure. Do not promote an arm with thin or single-day support.
- Development evidence includes prior published 2023–26 regular and 2024–25 expiry studies and fresh archived packets where available. The separately frozen 2023 expiry exam stays closed. Closed results require an observed exit or an explicitly labeled settlement assumption.

## Checks and delivery

Record exact source and input hashes, availability, parity, fees, worst day, drawdown, net excluding best, and the date count. Run the simulation helper report and verify for November 5. If a strategy does not clear the checks, preserve it as a rejected or unqualified research arm. A Dev-only operational change needs tests, atlas and guide updates, and an opt-out or a removal path. Production source, capital and orders are outside scope.

# Can two new entries fill the main F&O book's gaps?

**O31g, 31 October 2026. No new strategy passed. Production and the application
are unchanged.** The main-book control and the existing TPB-put complement
reproduced their earlier results. This is research on already-seen data.

The rules, analysis, tests and input bindings were committed and pushed as
**`86a4fd0` before any of the 24 new replays**. See [PLAN.md](PLAN.md),
[configuration.json](configuration.json), [freeze.json](freeze.json),
[results.json](results.json) and [crosschecks.json](crosschecks.json).

## What was tested

Both additions operate only on days when yesterday's daily ADX is below 30.
The main book operates at or above 30. Unknown daily inputs admit neither
complement. No final daily high/low, winning-day label or later outcome chooses
which strategy trades.

1. **A trend forming during the day:** five-minute ADX/DMI and a six-bar price
   break, aligned with session VWAP. This tests whether yesterday's quiet
   regime hides a tradable trend today. It is a rising intraday ADX rule, not
   a claim that every signal is a fresh ADX threshold crossing.
2. **A sharp move followed by confirmed recovery:** an unusually large,
   directional five-minute candle, followed by two opposite closes and a
   recovery through its midpoint. Both upside and downside versions are
   tested; a recovery call is not bought merely because the market fell.

Existing opening-range retests, failed breaks, squeezes, gap fades, CPR and
last-hour momentum had already been tried. These two entries add different
decision logic instead of changing their thresholds again. The research
motivation and its limits are in [SOURCES.md](SOURCES.md). The papers describe
mechanisms in other markets; they do not validate these NIFTY-option rules.

## The results

**Complete combined books, each year restarted with Rs250,000**, existing lot
limits and shared cash/brakes. These are hypothetical rupee results, after
brokerage/taxes and the previous study's extra cost formula
`(200 + 5*lots)*lots` per round trip. They are not a Rs15,000 live-trial result.

| Book | 2024 | 2025 | Jan–Oct 28, 2026 |
| --- | ---: | ---: | ---: |
| Current Dev main | +16,371 | +5,710 | +30,540 |
| Main + intraday trend | +10,053 | −34,454 | −38,704 |
| Main + shock recovery | +2,681 | −566 | +57,149 |
| Existing main + TPB puts control | +15,337 | +47,892 | +77,233 |

**Standalone one-lot diagnostics**, after broker costs and another Rs200 per
trade. Risk brakes are disabled in these diagnostics, so they are not a
deployable account simulation. Lot size is normalized to 65 in every year.

| Complement | 2024 | 2025 | 2026 | Trades, all years |
| --- | ---: | ---: | ---: | ---: |
| Intraday trend | +1,795 | −40,300 | −37,112 | 138 |
| Shock recovery | −6,376 | −5,301 | +10,932 | 44 |

**Why each fails:**

- Intraday trend is negative in five of six half-years. Its only positive
  year becomes −10,857 after removing that year's best day. Combined annual
  realized-equity drawdown reaches 19.3%, against the main's worst 7.5%.
  A rising intraday trend-strength reading was insufficient in this setup.
- Shock recovery earns in 2026, including both halves, but loses in both
  earlier years. The 2026 result has only **nine trades**. It adds Rs26,609 to
  the combined 2026 book while subtracting Rs13,690/6,276 in 2024/25. Its
  standalone three-year net is −Rs746, weekly t −0.07; at Rs300 extra cost it
  falls to −Rs5,146. This is not a narrowly missed profitable supplement.
- Neither passes the fixed standalone AND combined rules. No thresholds,
  direction choices, exits or sample rules were changed after these results.

The existing TPB-put control remains the stronger lead, but is **not newly
qualified**: it underperforms main in 2024 and its earlier specialist test
missed its fixed statistical bar. Its favourable total is not sufficient to
promote it. Reproducing its result here is a parity check, not independent
evidence: the same data and strategy were reused.

## What this teaches us

**The put advantage is specific to the entry logic.** Intraday-trend puts lost
Rs29,958 in 2025 and Rs23,093 in 2026 despite the main book's puts doing well.
Buying puts on every day the main book skips would not solve the problem.

**A plausible recovery is not enough.** Shock-recovery calls earned in 2025
and 2026 but lost in 2024; its puts lost in the first two years. Neither a
universal ban on calls nor a direction switch is justified by this test.

**Inactive days and losing active days are different problems.** These
complements have no direct overlap with main losing dates because their
daily gates are disjoint. They cannot hedge losses on main-active days. Their
integrated replays nevertheless include changes to later sizing and brakes;
we did not add separate-book profits to manufacture a portfolio result.

We have eliminated two more plausible hypotheses. We have not improved live
profitability, and no test establishes that nothing else can ever work.

## Checks and fidelity

- **24 new offline replays**, eight books × three years: main exact/raw,
  existing TPB-put exact/raw control, two complements alone and combined.
- **60 stored random closed-day replays reused**, all fingerprints checked.
  They are a reference distribution, not new independent tests. The best
  random book was −Rs8,372 across the three years after Rs200/lot/trade.
- **62 focused checks passed:** 13 new causal/mechanics checks, the prior
  weak-spot checks and main-book/policy-replay regression tests. This was not
  a full application-suite run; no application source changed.
- Main annual rupee parity exact: +16,371/+5,710/+30,540. Raw main total parity:
  +43,170. TPB-put combined parity exact: +15,337/+47,892/+77,233.
- Independent reconciliation of **1,087 closed records across independent
  arms**: no unresolved positions, finite whole-lot quantities, entry/exit
  ordering, day caps, daily gates and member attribution. Maximum trade-net
  discrepancy below Rs0.00005. This count is not one portfolio's trade count.
- Source hashes, all three dataset hash trees, private daily snapshots,
  named-signal memos and random-control files match the freeze. No candidate
  bar closes after 13:30; fills use the existing minute-observation clock
  (seconds :59). Original entry and hard-flat boundaries remain unchanged.
- Windows Python3.11.9, existing `python-engine/winvenv`; three workers, guarded
  by the existing shared-machine memory limits. Slices completed in
  112/120/98 seconds. Network disabled in workers; no broker/API acquisition,
  order, notification or scheduler execution. Production health reads HTTP200.
- Atlas regenerated: 291 modules, no atlas diff. No config/migration impact.

**Limits:** 699 archived sessions (248/248/203). Real option minute prices are
used, but bid/ask is modelled from the archive's spread assumptions, not
historical executable depth. Fills, lot65 normalization, realized-equity
drawdown and Rs200/lot costs are assumptions; the Rs300 diagnostic does not
rerun the cash path. Stops and account brakes are not guaranteed loss bounds.
There is no shared multi-module/system portfolio or continuous three-year
account in this study.

Read-only quality scan of the actual sealed inputs found **56 negative-volume
bars in the 2025 snapshot**, on June20/27 and July4/11, including two futures
bars. None in the sealed 2024/2026 snapshots. This differs from the larger raw
download's 162 flagged bars because the sealed replay uses a narrower
contract/date scope. No repair, interpolation or favourable-date exclusion
was made. Existing index/contract gaps and special-session limits remain.
These prevent treating replay gains as qualified profitability.

The frozen **2023 intraday/options exam is unchanged and unscored**. Existing
daily warmup supplied by the earlier replay machinery is used; this is not a
claim that all pre-2024 daily prices are absent. All strategy-scored 2024–26
windows were already seen. t statistics are not adjusted for the many earlier
searches.

## Concrete next work

1. **Keep both new complements out of runtime.** Preserve their failed records;
   do not tune their thresholds against these losses.
2. **Run the already-frozen 2023 exam once, unchanged**, after a future day's
   owner login, a small availability probe, the download and data checks.
   Today's acquisition allowance is already spent. Do not add these failed
   candidates to that exam. It can test the existing TPB-put lead without
   inventing a new pass rule after seeing another year.
3. **Repair/verify input defects and measure real costs** before relying on
   positive replay results. A passing exam still needs fresh paper outcomes
   and reconciliation; the main strategy is not proved by these old years.
4. **If a separate new study is authorized:** test option expression rather
   than another large indicator grid. Compare the same fixed recovery or TPB
   entries as single long options versus fully funded debit spreads. It needs
   both legs' contemporaneous prices, missing-leg refusals, two-leg fees and
   fills, shared cash and a suitable lifecycle adapter. First reproduce a
   matched baseline; freeze at most two candidates and a fresh evaluation
   sample. Buying a cheaper spread is not automatically better: extra costs,
   capped winners and execution risk must be scored. No short naked options,
   extra borrowing or new real-order authority is proposed here.

## Reproduce / evidence packaging

Use `python-engine/winvenv/Scripts/python.exe`. For each year use the existing
`docs/research/fno/run_slice.py`, setting `O30F_YEAR=2024` OR
`O30C_YEAR=2025/2026`, and run `lab_gap.py run --jobs 3`; then
`analyze_gap.py`. `freeze.json` must remain committed and every binding must
match. The complete raw trades, daily inputs, run logs and keys are local in
`_local/`, intentionally excluded from Git. Shareable results contain derived
statistics, not raw option prices or credentials.

The root `request.json`/`policy-freeze.json` are the initial helper inventory
at checkout `416984f`, before the study-source freeze commit. The authoritative
pre-run study contract is `freeze.json` at `86a4fd0`. A separate helper report
under `_local/evidence-report/` packages the completed, committed study and
hash-verified private evidence; it is a post-run consistency check, not a
replacement for the pre-run freeze or financial/causal verification.

Research/source status: frozen source and results are pushed to Dev. No
application changes, merge, deployment, capital activation or Production edits.

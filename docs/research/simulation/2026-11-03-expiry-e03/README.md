# E03: E02's entry with a free runner, after a zero-to-hero search — November 3, 2026

Owner request (November 3): E02 R3's returns are too small. Search for the expiry
"zero to hero" trade (an option going 3-10x) and the volatility of that moment, keep
the risk bounded, try E02.1, improve it, use the genome if useful, and call the
satisfactory result E03. Also test E01.1 (the main paper C) on the new data, find why
it loses and what it missed, and improve it without overfitting.

**Result: E03 = E02 R3's entry unchanged, up to three lots inside E02's own Rs 1,250
ticket reserve, strikes within four steps, and at E02's 2x sale only half the lots are
sold; the rest run free on a floor at cost, keep half the peak and are sold at 10x.**
Over NIFTY 2024 and 2025 it earns Rs 11,956 at ordinary fills and Rs 11,115 at worse
fills, against E02's Rs 6,901 / Rs 6,260 on the same four-strike pick (Rs 6,329 /
Rs 5,669 as E02 reported it). Worst day, ticket reserve and day reserve are E02's.
**Both years were already seen; this is in-sample.** Severe fills lose (Rs -3,273).
Every hero idea that changed the entry lost money and was rejected.

Dev branch `codex/production-correction-hedge-p0`, starting at `d12f6fe`. No Production
edit, no Breeze/Kite call, no N11/N11T, A/B/C, capital or `.env` change. The 2023
expiry chain in the E02 source file is never opened: every query is bounded to 2024 or
2025 in SQL.

## Data and what was already seen

- NIFTY expiry-day minute chains, 2024 (52 sessions) and 2025 (53), with index, front
  future, every strike within four steps of the day's low/high, volume and open
  interest: E02's `_local/2024.sqlite` and `2025.sqlite`. Both years were fitted by
  E02 R3, so nothing here is an untouched exam.
- Production's own ten-second NIFTY records, October 6, 13, 19 and 27 (E01's export),
  plus November 3 copied read-only after the close: never used to fit E02 or E03.
- No 2026 expiry minute chain exists, and SENSEX has opening-strike files only, so
  neither can replay E02's or E03's strike choice.

## What the market shows (diagnosis, `census.py`, `surface.py`, `slice.py`, `slice2.py`)

- **Hero moves are common in hindsight, rare per ticket.** Half the afternoons had some
  cheap option (Rs 1-20, within four strikes) that went 5x or more (27 of 52 in 2024, 32
  of 53 in 2025; 15 a year went 10x). But only 9.3% / 6.1% of all such tickets reached
  5x.
- **Afternoon movement is predictable from movement so far:** the 13:00 sixty-minute
  realized volatility correlates 0.54 / 0.53 with the afternoon range in both years.
- **Buying cheap OTM tickets and waiting loses in both years.** Per ~Rs 1,000 ticket,
  held to 15:28: -Rs 139 (2024) and -Rs 473 (2025); the cheapest (Rs 1-2) lose most
  (-Rs 248 / -Rs 832), the longshot bias. Lower implied/realized volatility is better
  in both years, but at the day level no threshold is positive without its best day
  in both years, and the reading mostly measures distance (correlation 0.72 with reach).
  Trend strength and the size of the morning move help in 2024 and reverse in 2025.

## Every rule tried (ledger `trials-explore.csv`, 34 book runs, each on both years and two fill levels)

| Idea | Result | Verdict |
|---|---|---|
| E02.1: let E02's one-lot ticket run (no 2x sale, idle clock only before +40%) | 2024 +3,361 (ex-best -1,784), 2025 -1,573 | rejected |
| Same with a 50% runner keep, or 2-3 cheaper lots with a cost-recovery bank | 2025 -1,856 to -2,160 | rejected |
| One-lot ratchet: no sale at 2x, floor 1.5x / 1.8x | +3,714 / +4,658 (2024), +2,128 (2025): below E02 | rejected |
| **Split: sell half the lots at 2x, runner on a floor at cost** | 2024 +7,843 to +8,021, 2025 = E02 (no two-lot ticket reached 2x) | **kept** |
| Runner neighbours: keep 40/50/60%, floor 1.0/1.2/1.5/2.0x, 5x/10x/no target | every one at or above E02 in both years | robust |
| E02's 2x sale moved to 1.5x or 3x | both worse (3x: ex-best -3,207 in 2024) | 2x stays |
| Implied/realized volatility filter on E02's entries (<= 1.5, <= 1.2) | fewer trades, 2025 lower | rejected |
| One Rs 2,500 ticket a day instead of two of Rs 1,250 | +10,093 / +5,679, but 2024 ex-best -1,678, worst day doubles | rejected |
| Hero kicker: an extra Rs 250 ticket 1-3 strikes further out (`kicker.py`) | ex-best negative in both years at every distance | rejected |
| "Gamma blast": first close through the largest-OI strike (`gamma.py`) | quick estimate positive, but it sold at the decision close; in the book: 2025 -4,328, 2024 +1,239 (ex-best -6,783) | rejected |

The two `gamma.py` and three `kicker.py` estimates are diagnostics beside the book, not
book runs; their printed figures are recorded above.

**A defect found on the way:** E02's lab allows strikes up to 400 points away, but the
download holds every strike only within four steps (200 points) of the day's range, so
a farther strike exists only on a day the index later moved toward it. It happened once
(2024, a losing trade). E03 caps at four steps; E02's results on that cap are
+3,514 (2024) and +3,387 (2025) ordinary. E02's paper code keeps its own 400 points
unchanged.

## E03's final evidence (`final.py` → `final-results.json`)

| | E02 R3 (four-strike) | **E03** |
|---|---:|---:|
| 2024 ordinary / adverse | +3,514 / +3,234 | **+8,567 / +8,132** |
| 2025 ordinary / adverse | +3,387 / +3,026 | **+3,389 / +2,983** |
| Severe fills (next bar's high/low), 2024 + 2025 | -2,868 + -899 | -2,651 + -621 |
| Without the best day, 2024 / 2025 (ordinary) | +2,201 / +2,184 | +2,717 / +2,187 |
| Worst day 2024 / 2025 | -568 / -550 | -568 / -550 |
| Realized drawdown 2024 / 2025 | 922 / 569 | 922 / 895 |
| Trade profit factor 2024 / 2025 | 2.38 / 2.90 | 3.66 / 2.61 |
| Tickets | 20 / 21 | 20 / 21 |

- **Where the gain is.** Two lots alone (no runner) give +4,595 / +3,225. The runner
  adds +3,972 in 2024, almost all on 2024-03-28: two lots at 7.60, one sold at 18.85,
  the runner sold at 87.65 (11.5x), +5,850. In 2025 no two-lot ticket reached 2x, so the
  runner never fired; 2025's +3 over E02 is three-lot losses in Q1 (-326) balanced by
  three-lot wins in Q3 (+329).
- **The runner cannot add a loss beyond its own lot's gain:** its floor is the ticket's
  cost after half the lots were sold at 2x.
- **Random-entry control (40 seeds):** E03's exits on random entries average -834
  (2024) and -997 (2025); E03 beats 100% / 95% of them; E02 beats 97.5% / 97.5%. The
  money comes from the entry plus the exits, not from the exits alone.
- **Production's own records (Oct 6, 13, 19, 27 and Nov 3):** one trade, the same for
  both (Oct 27, +94 ordinary); no signal on Nov 3. Too few to judge; E02's signal fires
  about 21 times a year.
- **Paper code parity (`parity.py` → `paper-parity.json`):** all 82 lab positions
  (both years, ordinary and adverse) replayed through `expiry_e02.action`/`sell_base`:
  same decisions, clocks, lots, prices and money, zero mismatches. While building it,
  the lab's runner was found to start one bar before its partial sale filled; it now
  starts at the fill like the paper code, and no result changed.

## E01.1 on the new data (`e011_2024.py` → `e011-2024.json`)

E01.1's rules were frozen on November 2, before any 2024 price was opened, so NIFTY 2024
is a clean test of them (the minute-chain C proxy of the November 3 year study, same
code, 2024 source):

| 46 tickets, 2024 | Ordinary | Adverse | Ordinary without best day | Worst day |
|---|---:|---:|---:|---:|
| C (old) | -8,441 | -29,650 | -35,775 | -2,310 |
| E01 | -18,669 | -31,214 | -24,276 | -1,239 |
| **E01.1** | **-9,012** | **-28,887** | **-14,567** | **-1,239** |
| E01.1, no sale at 3x | -15,348 | -32,455 | -20,823 | -1,239 |

With the year study's 2025 (-20,638 over 53), E01.1 lost about Rs 29,650 over 99 NIFTY
expiries at ordinary fills. It is the least bad lottery exit, but C's box-break entry
has no edge: most tickets never move (the year study: median losing ticket peaks at
1.09x). E03 is E01.1's own idea, taking the cost back and letting the rest run on a
floor, applied to E02's entry, which beats random entries. On November 3, the first
Production day with E01.1 as C, its ticket (23850 CE at 6.45, five lots) hit the 25%
stop in ten minutes: -Rs 700.92.

## In the engine (Dev only, disabled)

`expiry_e02.py` gains a `Variant` (E02 unchanged, E03 new), `policy_for`, `sell_base`
and `_lots`. E03 has its own `<DB_PATH>.expiry-e03.db`, cash Rs 25,000, play `E03`,
version `expiry-e03-v1`, flag `EXPIRY_E03_SHADOW_ENABLED=false`. The scheduler runs each
variant after the primary tick; a disabled variant's open leg still exits; both open
legs stay in the existing quote batch (no extra request). No message, order, ledger or
primary-store write. Tests: `tests/test_expiry_e03.py` (8) with E02's 21, 29 passed.
Full engine suite: 6,110 passed, 4 skipped, 0 failed (661.8 s), run before a one-line
fix that makes `run_tick` report each variant's own version; the 29 pass after it.

## Plan slice

- Problem: E02's small returns; the owner wants hero upside without unbounded losses.
- Contracts: E02's signal/strike band/reach/stops/brakes; E03 adds lots <= 3 inside
  Rs 1,250, distance <= 200, `TARGET_BASE` partial sale (latches nothing), runner
  `RUNNER_TRAIL` / `HERO_TARGET`, policy frozen on the position at entry.
- Acceptance (met): E02 behaviour and tests unchanged; E03 positive in both seen years
  and both fill levels, ex-best positive, worst day no worse than E02, every runner
  neighbour at or above E02; lab-paper parity zero mismatches.
- Rollout: owner's decision. Merge and rebuild, then set `EXPIRY_E03_SHADOW_ENABLED=true`
  (with E02's flag too, for the paired comparison). Rollback: flag false (open legs keep
  their exits), or revert the commit; the E03 DB is separate.
- Remaining: forward paper evidence (20 closed E03 tickets, paired with E02 on the same
  entries); SENSEX needs a full-chain study; a fresh full-chain expiry exam (2023 stays
  protected until the owner assigns it).

## Commands (from this folder, Dev venv)

```text
python census.py            # hero census -> census.json
python surface.py           # ticket surface -> _local/surface.csv; then slice.py, slice2.py
python explore.py v01.json  # ... v06.json: book runs, appended to trials-explore.csv
python kicker.py; python gamma.py
python controls.py 40       # pre-cap control (controls.json); final.py supersedes it
python final.py 40          # final-results.json
python native.py            # native-results.json
python e011_2024.py         # e011-2024.json
python parity.py            # paper-parity.json
```

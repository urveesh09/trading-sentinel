# E03.2 research record — November 3, 2026

Plain report: [EXPIRY_RESEARCH_E032.md](../../../EXPIRY_RESEARCH_E032.md). Plan written before any
morning score: [PLAN.md](PLAN.md); late slice: [PLAN_LATE.md](PLAN_LATE.md).

**Result: no E03.2 rule beats E03.1. Two never-scored time slices were tested frozen and both failed;
six in-sample directions and a leave-one-year-out genome failed too. One execution change helps, and
only when fills are bad: never pay more than 7-8% above the decision ask (E03/E03.1 allow 10%).
Nothing in the runtime changed.** E03.1 (65cccb7) remains the best expiry candidate, disabled and
not deployed. Both afternoon years were seen before this study; every afternoon figure is in-sample.

Dev branch `codex/production-correction-hedge-p0`, starting at `374384f`. No Production edit, no
Breeze/Kite call, no download, no engine, config, `.env`, schema, N11/N11T, A/B/C, E02, E03 or E03.1
change. NIFTY 2023 is never opened: the lab reads only the 2024/2025 tapes.

## Data

NIFTY expiry-day minute chains, 2024 (52 sessions) and 2025 (53), 09:15-15:29, index, front future,
every strike within four steps of the day's range (E02's `_local` tapes). E02, E03 and E03.1 all chose
their rules on 13:00-15:00 only (E02's genome allowed starts of 13:00/13:30 and ends of 14:30/15:00).
The history database holds **no 2026 same-day-expiry option minutes for NIFTY or SENSEX** (checked by
count; the 2026 option requests are for days before expiry, about eight strikes near the money). The
ten-second 2026 export holds one opening-ATM strike per day. Neither can replay E03's strike choice.

## Frozen tests on never-scored slices

| Test (freeze commit) | Arm | 2024 ord / adv | 2025 ord / adv | Verdict |
|---|---|---:|---:|---|
| Morning 09:30-13:00 (`68db264`) | E02 | -3,136 / -3,240 | -3,539 / -3,690 | |
| | **E03** | **-3,221 / -3,257** | **-3,505 / -3,669** | **FAIL, every check** |
| | E03.1 | -3,257 / -3,302 | -3,668 / -3,706 | |
| Late 15:00-15:15 (`2494709`) | **E03** | **+1,240 / +1,139** (3 tickets) | 0 tickets | **FAIL** (ex-best -767, 2025 empty) |

- Morning: 22 tickets in 2024 and 24 in 2025 (independent books), two winning days each year. Random
  entries in the same window lose less (median -2,563 / -2,550); E03's morning signal sits at the 25th /
  18th percentile of them. In the continuous book (27 tickets, brakes on) 24 tickets end on the
  eight-minute clock: every hour from 09:00 to 12:00 loses. The commit message of `2494709` says
  "2 winners of 22 and 24 tickets"; those were winning **days**.
- Late: three 2024 tickets, one winner; no 2025 signal found an eligible ticket.
- **Learning: E02's entry has its edge only between 13:00 and 15:00.** Before that the cheap option does not
  move enough in eight minutes; after 15:00 there is almost nothing to buy in the band.

## In-sample directions (every run in `trials.csv`, `genome-trials.csv`, `diagnostics.json`)

| Idea | Runs | Result vs E03.1 (+12,427 ord / +11,498 adv, continuous) | Verdict |
|---|---:|---|---|
| House-money roll: at the 2x sale, a share of its profit buys a further-OTM option | 144 | median -584 ordinary; 17% help at both fills; after one-lot sales -1,615 on average | rejected: the 2x is usually the end of the burst |
| Earned ticket: the day's reserve grows with the book's profit | 6 | +9,858 to +16,742, not monotone; worst day to -879 | rejected: lot rounding makes it noise |
| Same signal, near-the-money option, one lot (Rs 6,500 reserve) | 24 | all lose: -2,546 to -4,576; worst day -2,175 | rejected |
| Prefer a strike where two or three lots fit Rs 1,250 | 8 | all below (best +12,238) | rejected: cheaper strikes are dearer per rupee |
| Signal reversed / signal minute with a random side | 2 + 80 | reversed: -635 / -3,025 (2024/2025); random side: +3,505 / -134 mean | learning: direction and timing both count |
| Leave-one-year-out genome over 19 mechanisms, two seeds each way | 677 | top picks earn less than E03.1 on the unseen year in all four runs | rejected; family positive (below) |
| Most paid above the decision ask: 4-10% | 20 | 7-8%: same ordinary and adverse, severe -2,486 (E03.1: -3,234) | **kept as learning** |
| Whole book scaled 1-20x | 10 | per Rs 25,000: 12,427 (1x), 12,398 (4x), 7,718 (10x) | learning: size is the lever |

- **Two tickets a day are rare:** 6 of 35 trading days; an open runner never blocked a later signal, so
  running tickets side by side changes nothing.
- **E03.1's tickets** (`diagnostics.json` `tickets`): 2024 earns on 2x sales and the one hero; 2025 earns
  on small gains sold by the eight-minute clock (15 tickets, +3,222). No hour, price or lot split repeats
  across the two years.
- **Genome family:** of the 677 settings, 85% (fit 2024) and 99.7% (fit 2025) are positive on the year they
  did not see; 75% and 71% stay positive without that year's best day; 15% and 26% beat E03.1 there. The
  E02/E03 family is broadly positive around its centre, but searching harder does not pick a better point.
- **Buy limit:** ordinary results do not change until 4.5%, adverse until 6%; below 6% the adverse 2024 hero
  fill is refused (-2,207). 6% would be fitted to keep that fill, so the safe middle of the plateau is 7-8%.
  E03 shows the same: 7-8% leaves +11,956 / +11,115 and severe -2,502 (from -3,154). Severe stays
  negative in 2024 (-2,436).
- **Capacity:** the lab's lot cap (10 lots) and 20% volume share bind beyond about 4x; that is a model
  limit, not a measured market limit. At 4x (Rs 1,00,000) the book earns +49,591 ordinary over the two
  years, worst day -2,166, drawdown 5,249: the same percentages as Rs 25,000.

## Why no runtime variant

The only rule that helped differs from E03.1 on spike fills only. A third disabled paper book identical
in normal fills would produce forward tickets that cannot tell the two apart. The decision: record
the 7-8% buy limit for whichever variant the owner promotes, as part of that promotion's frozen version.
Any E03.1 paper ticket already shows it: compare its fill to its decision ask.

## Plan slice

- Problem: the owner wants E03.2 to clearly beat E03/E03.1 with small losses, or a learning.
- Contracts: E02/E03/E03.1 rules and engine unchanged; research only in this folder.
- Acceptance (PLAN.md): improve E03.1 each year at both fills, ex-best positive, worst day >= -1,250,
  drawdown <= 2,500, random control beaten, not confined to one setting. **No candidate met it.**
- Rollout / rollback: none, no runtime change. Docs only.
- Remaining (owner's decisions): (1) a fresh, untouched test: NIFTY 2026 same-day-expiry chains are not
  in the database. The download shape the owner approved for E01.1's exam (`EXAM_YEAR.md`, 18 legs around
  the 13:00 ATM) can also test the E03 family on days that stay within about 100 points of 13:00; its rules
  are frozen now in [EXAM_E03_FAMILY.md](EXAM_E03_FAMILY.md). SENSEX needs its own download; NIFTY 2023
  stays the protected exam. (2) Forward paper: switch on E03 /
  E03.1 after merge and rebuild. (3) Size: only after forward evidence, at the same percentage risk.

## Commands (from this folder, Dev venv `../../../../python-engine/winvenv/Scripts/python.exe`)

```text
python morning.py score     # refuses unless freeze-morning.json is committed and every hash matches
python late.py score        # same for freeze-late.json
python e032_lab.py          # E03 and E03.1 reproduce day by day, all three fill levels
python trials.py baseline|earn|roll|atm|prefer   # appends to trials.csv
python genome.py            # genome-trials.csv, genome-results.json
python diagnostics.py       # diagnostics.json
```

`morning.py`/`late.py` re-verify their freezes; `PLAN.md` and the scripts are hashed, so editing them
makes a re-score refuse. `trials.py` and `genome.py` append; rerunning adds duplicate rows.

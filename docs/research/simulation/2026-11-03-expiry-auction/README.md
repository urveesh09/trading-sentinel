# The closing auction and the seller's side — November 3, 2026

Plain report: [EXPIRY_RESEARCH_AUCTION.md](../../../EXPIRY_RESEARCH_AUCTION.md). Plans frozen before scoring:
[PLAN.md](PLAN.md) (auction drift, `b7c90bd`, v2 `bd2a31d`, see [FREEZE_NOTE.md](FREEZE_NOTE.md)) and
[SELLER_PLAN.md](SELLER_PLAN.md) (`176e7b5`).

**Result: nothing tradeable for a buyer in the closing auction, and no robust seller edge.** Both
were the two perspectives no study here had tested. Research only: no engine, config, `.env`, schema,
Production, N11/N11T, A/B/C/D or E-variant change. No download; NIFTY 2023 not opened. Production
recordings were read from the read-only copies earlier studies made.

## Why the closing auction

Since August 3, 2026 expiring options settle at the closing-auction close. F&O stocks stop continuous
trading at 15:15; Kite's index stays frozen at its 15:15 value until about 15:29; options trade on to 15:40.
Every earlier expiry study used 2024/2025 data, from before this rule.

## Data

27 closing-auction-era expiry days, August 4 to November 3, 2026:
- 9 Production recordings (NIFTY Oct 6, 13, 19, 27, Nov 3; SENSEX Oct 8, 15, 22, 29): every 10 s, index,
  future, 34 strikes' five-level books;
- 18 Breeze ten-second export days (NIFTY Aug 4 - Sep 29, SENSEX Aug 6 - Oct 1): last trades of the
  opening-ATM call and put to 15:29:50, index and future minutes from the history database.
Eight export days lack the 15:20 or 15:35 index minute: unavailable, never zero. October 6 suggested the
hypothesis and is reported apart. 18 unseen days were usable.

## The auction drift (frozen test, `results.json`)

| Measure at 15:22 (18 usable unseen days) | As frozen | Verdict |
|---|---|---|
| H1: the options' drift points the way the auction closes | 12 of 14 signalled days (86%) | pass |
| H2: more move still to come after 15:22 | mean +4.4 points, median -2.0, 50% positive | **fail** |
| Trade on 8 Production days (buy the in-the-money side at 15:22, sell from 15:31) | +2,657 over 5 trades, 2 wins, -2,077 without the best | **fail** |
| Controls: opposite side / hold to settlement | -4,099 / +2,776 | |

**A data finding that weakens H1:** from 15:20 the Breeze history shows an indicative auction index on 8 of
the 10 usable export days while Kite's stays frozen (Sep 15 NIFTY: frozen 23,172.35, 22,880.20 at 15:20,
final 23,118.60; Sep 3 SENSEX: frozen 76,510.32, 74,373.29 at 15:20, final 76,152.86). The plan read the
frozen level at 15:20, so on those days it read the indicative value. Read at 15:15 (`corrected.py`,
`corrected.json`; a diagnostic after the score, not a pass): at 15:22 the drift agrees with the close on 60%
of 15 days and the remaining move has median -33 points; from 15:16 to 15:20 it agrees on 36-45%; only at
15:27-15:29 does it agree on 88-100%, too late to matter. The options track the auction as it forms and
were closer to the final than the indicative index (Sep 3: index 1,780 points off at 15:20).

**The auction's size is overpriced too.** Production's own plays, re-valued with their settled legs (the
`net_pnl` of a settled leg holds only its charges; the value is in `assumed_pnl`): B (strangle bought
15:13:30) -3,007 over five days; BH (the same strangle held through the auction) -6,313 over four, every
day negative. Same export: A +4,709, C -1,341, D -1,007.

## The seller's side (frozen test, `seller-results.json`)

An iron butterfly: sell the at-the-money call and put, buy cover 2 or 4 strikes away, at 13:00 or 14:00,
held to 15:28 or stopped when the cost to close reaches 1.5x or 2x the credit. 12 arms, one lot.

- All six 13:00 arms lose in both years (-5,264 to -34,762 a year at ordinary fills).
- **One arm passes:** 14:00, cover 4 strikes, stop at 2x credit: 2024 +20,049 / +13,373 (adverse), 2025
  +16,723 / +12,050; positive without the best day; worst day -6,044; 35 of 52 and 34 of 53 days win;
  severe fills -14,911 (2024) / -830 (2025). Production's 9 days: +7,473, 6 wins, worst -3,899.
- **Rejected on its neighbourhood** (`seller_diag.py`, `seller-diagnostics.json`, in-sample): cover 3-5
  strikes and stops 0.75x-none stay positive in both years, but **2025 is positive only at exactly 14:00**,
  with or without the stop (13:45: -6,327 / -5,782; 14:15: -8,175 / -10,229). 2024 is positive from 13:15
  to 14:15. Whether selling paid depended on the year's afternoon regime, not on a stable edge.
- On the 9 Production days, closing after the auction (+7,473) beat closing at 15:14 (+2,701).

## What this says

On expiry day the price already carries what the market knows: the auction's direction within minutes of
15:20, its size richly, cheap far options above their payoff. The buyer's edge found in this repo remains
E02/E03's 13:00-15:00 trend pullback. A seller's results swing with the year. Neither the auction nor the
seller side earns a runtime change.

## Plan slice and status

- Contracts: research only in this folder; frozen plans before every score; failures and the crash kept.
- Acceptance: as in the two plans; nothing passed robustly. Rollout/rollback: none.
- Remaining (owner): the frozen E03-family exam on the approved download; forward paper for E03/E03.1
  (and D keeps measuring the seller's side on paper). A faster auction study would need streamed
  exchange-timestamped quotes and is not justified by these results.

## Commands (Dev venv `../../../../python-engine/winvenv/Scripts/python.exe`, from this folder)

```text
python auction.py score      # refuses unless freeze-v2.json is committed and every hash matches
python corrected.py          # post-score diagnostic, frozen level read at 15:15
python seller.py score       # refuses unless freeze-seller.json is committed and every hash matches
python seller_diag.py        # in-sample neighbourhood
```

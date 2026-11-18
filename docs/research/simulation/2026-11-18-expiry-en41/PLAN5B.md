# Round 5b: EN41 / EN42 on real order-book packets, and a resting-bid fill check (frozen before any score)

Nov 18, 2026. The owner authorised a read-only extraction of TR01's depth packets from Production: "If only data extraction is what you're doing, then sure go ahead."

## Data (count-only facts gathered before this plan)

**The export:** `C:/Users/Urveesh/sentinel-operations/tr01-export-20261118/`.
- It holds the two complete recorder days, 2026-11-16 and 2026-11-17, copied with `docker cp` from the Production container (read-only on the source).
- Nov 18 is still recording and is not an expiry day, so it is not exported.
- `tr01.verify()` re-hashes all 802 chunks against the recorder's manifests and all match. The days hold 10,222,859 and 10,455,753 packets, with no disconnections between 09:00:40 and 15:41.
- The exported packets do not include BANKNIFTY.

**Coverage audit** (NIFTY front future, NIFTY26NOVFUT, 09:15–15:30):

| | Nov 16 | Nov 17 |
|---|---:|---:|
| Occupied one-second bins | 75.9% | 81.5% |
| 10-second windows with ≥ 8 of 10 seconds occupied and the last packet ≤ 2 s old | 1,086 of 2,250 | 1,556 of 2,250 |

- Receipt lag behind the exchange stamp: median 0.6–0.8 s, 99th percentile 1.1–1.35 s; no timestamp is in the future.
- The top book is always valid (bid < ask, quantities > 0).
- The feed is Kite "full" snapshots, about one per second for the future, not every exchange event. So the order-flow numbers are a **delivered-snapshot proxy**, as the auditor's specification says.

**Eligibility, fixed now with the auditor's thresholds:**
- A session must have ≥ 80% occupied one-second bins for the front future. **Only Nov 17 qualifies**, and it is also the only expiry session. Nov 16 is excluded and that is reported.
- Every signal window must itself pass the 10-second validity test.

**Expiring options:** 82 recorded contracts (41 strikes × CE/PE). Between 13:00 and 15:00 the median contract has a packet in 92% of seconds.

**Activity counts on Nov 17, taken before freezing; no returns were looked at:**
- 1,391 standardised windows; 91 with |z| ≥ 2; 9 consecutive same-sign pairs;
- **EN41 events: 2**; EN42 events: 0;
- price-progress-only events: 475; EN42 fade-control episodes: 0.

The rules are not changed to raise these counts.

## EN41: persistent book pressure (the auditor's specification, unchanged)

**Windows:** 10-second windows from 09:15:00, by receipt time. Snapshot OFI per packet comes from best bid/ask and quantities:

`e = 1(b≥b₋)·qb − 1(b≤b₋)·qb₋ − 1(a≤a₋)·qa + 1(a≥a₋)·qa₋`

The window OFI is the sum of e over the window, divided by the window's mean top quantity. It is standardised against the previous 60 windows, excluding the current one; this needs ≥ 30 valid windows and a positive standard deviation.

**Signal**, at the end of window k (k−1 and k both valid):
- z ≥ 2 in the same direction d in both windows;
- the future mid moved d × 0.10–0.50 ATR10 from the start of window k−1.

ATR10 is the mean true range of the last 10 completed one-minute future-mid bars. Decisions run 09:45–14:45.

**Contract:** E03.2's native selector on the expiring chain.
- The nearest OTM strike of side d whose fresh best ask is Rs 5–20.
- Within min(200 points, 1.0 × index ATR10 × √minutes left).
- The quote must be ≤ 2 s old at the decision.

**Size:** the most lots (≤ 3) whose limit, together with fees and one order charge per lot, fits Rs 1,250. The limit is 1.04 × the walked decision ask, tick-rounded down.
- One open position at a time, at most two parents a day, a Rs 2,500 daily reserve.
- NFO fees, charged per fill.

**Fill:** the first packet of that contract with receipt ≥ decision + δ, walking the ask depth. It must be at or below the limit; otherwise the next packet is tried, up to decision + 20 s; otherwise the ticket is missed.
- δ = 1 s is primary (the measured lag is about 0.7 s). 3 s and 10 s are stress runs.

**Exits**, checked every second from the fill. The first trigger wins:
- two successive windows of OFI opposite to d;
- a future-mid move of 0.50 ATR against the position from entry;
- the option's best bid ≤ 0.65 × entry;
- 3 minutes;
- 15:14.

The sale walks the bid depth at the first packet ≥ trigger + δ, retried on later packets. If no packet can fill it by 15:29, the ticket is unresolved and loses its whole premium.

**Controls (descriptive):**
- the same decision times with a random side (40 seeds);
- price-progress-only events (the move condition without OFI);
- the EN41 events taken one window later.

**Mechanism report:** for every EN41 event, traded or not, the future-mid change d × (mid(t + 30 / 60 / 180 s) − mid(t)) in ticks. Price-progress-only events and all valid windows serve as baselines.

## EN42: pressure that fails to move price (the auditor's specification, unchanged)

**Candidate**, at the end of window k: all of these must hold:
- both windows have |z| ≥ 2 in direction d;
- the mid displacement over the two windows is ≤ 0.10 ATR;
- at least 3 distinct snapshots in the 20 seconds show the defending best price (the ask when d = +1, the bid when d = −1) within 2 ticks of its episode-start level, with its quantity higher than in the previous snapshot.

**Signal:** freeze the 20-second episode's mid high and low. Within the next 3 windows (30 s), a valid window must close beyond the opposite boundary by ≥ 1 tick, with OFI of sign −d. Then buy side −d at that window's end. One plan per episode.

**Exits:** the first of:
- the future mid goes back beyond the episode's adverse extreme + 0.10 ATR;
- the future reaches 0.75 ATR of favourable progress;
- the premium stop;
- 3 minutes;
- 15:14.

Entry, size and fills are as in EN41.

**Controls:** a simple fade at the episode end, and a random side.

## Q28: do resting bids really fill? (EN28's open question)

**Order:** every 60 s from 13:00:00 to 14:59:00, for both sides, take the nearest OTM expiring contract with a fresh ask of Rs 5–20. Rest one lot (65) at the best bid B₀, joining behind the displayed quantity Q₀ already there.

**Conservative fill:** cumulative traded volume at packets whose LTP ≤ B₀, from the decision on, reaches Q₀ + 65.

**Optimistic fill:** any later best ask ≤ B₀, or an LTP ≤ B₀ − 0.05.

**Minute-candle proxy:** what round 4's EN28 assumed, i.e. the low of the next minute's LTPs ≤ B₀ − 0.05.

**Reported** at 10 s and 60 s:
- fill rates under each rule;
- the mid change 60 s after the decision for filled against unfilled orders (adverse selection).

## Verdicts

**EN41 and EN42 (trading):** with one eligible expiry session, the support floor of 30 funded tickets on 20 expiries cannot be met. The trading verdict is therefore **INCONCLUSIVE** by construction, and that is stated before scoring. The scored output is the trades at δ = 1 / 3 / 10 s, the controls and the mechanism report.

**The mechanism** is described with mean, t-statistic and count, never a pass.

**Q28** is a measurement with no pass or fail. It answers whether the minute-candle fill assumption matches packet evidence on this session.

**Recorder sessions after Nov 18** are a later cohort. The code reruns on a new export with a new freeze.

## Files

| File | Role |
|---|---|
| `tr01.py` | Loader and hash verification |
| `en5b.py` | Audit, EN41, EN42 and Q28 |
| `PLAN5B.md` | This plan |
| `freeze5b.json` | Hashes of the files and the export's manifests |
| `results5b.json` | Written once |

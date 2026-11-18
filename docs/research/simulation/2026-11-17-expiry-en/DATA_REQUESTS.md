# Expiry data requests: slots held open until the data arrives (Nov 18)

The owner will arrange missing data from Nov 18. The slots below were run on stand-in data or not at all, so they are **held open as reminders**. When a request lands, rerun the slot's frozen definition (`PLAN3.md` / `en_lab3.py`) on the new data with a new freeze, scored once.

Breeze downloads go only through the `breeze-history-download` skill. The stock data (request 4) is not on Breeze.

| # | Data | Exact scope | What it unlocks | Priority |
|---|---|---|---|---|
| 1 | **NIFTY 2026 expiry afternoons** (Breeze) | Every NIFTY weekly expiry day, Jan–Nov 2026 (about 45 days); see the coverage note below | **The only unseen NIFTY year:** a real exam of E03.2 and of the parts worth keeping (EN21 scale-in, EN25 resting bid, EN14 second wave, EN12 runner against full sale at 2x) | 1 |
| 2 | **SENSEX expiry afternoons** (Breeze) | Every SENSEX weekly expiry day, Oct 2024 – Nov 2026 (about 105 days; the weekday changed over the period); coverage as in request 1 at 100-point strikes | **E03.2 runs live on SENSEX but has never been tested on SENSEX history.** Every EN slot was NIFTY-only | 2 |
| 3 | **Next weekly expiry on expiry days** (Breeze) | On each NIFTY expiry day 2023–2026: the following week's expiry, ATM ± 2 strikes, CE + PE, 1-minute, 12:45–15:30 | **EN16** on 3+ years instead of 19 recorded sessions | 3 |
| 4 | **NIFTY 50 constituents, 1-minute** (Kite, not Breeze) | The 50 names in `en15_breadth.py` (membership dated if available), NIFTY expiry days 2024–2026, 12:00–15:30 | **EN15** at the 1-minute horizon it was designed for (the 15-minute stand-in failed) | 4 |
| 5 | **1-second data for the strikes E03.2 actually buys** (Breeze) | NIFTY expiry days 2026, 13:00–15:30, expiring OTM strikes 100–300 points from spot, CE + PE | **EN11's speed measurement** at E03.2's real strikes (the Jan–Mar file held only the open's ATM pair) | 5 |
| 6 | NIFTY 2020–2022 expiry afternoons (Breeze) | Every weekly expiry day, coverage as in request 1 (about 155 days) | Extra history for any survivor | 6 |

**Coverage for requests 1, 2 and 6:** the same as the existing 2023–25 export:
- every strike within 4 strikes of the day's high–low range, calls and puts;
- 1-minute bars, 09:15–15:30;
- plus the index and the front future.

The full day is needed, because EN13, EN17 and EN23 read the morning.

**Not purchasable (no action needed from the owner):**
- **Real bid/ask depth history** (EN18, EN25 fill rate) exists only in our own recorders: the forward-panel quote export and the TR01 tick recorder.
  - I export sealed copies before TR01's 35-day rotation.
  - Each new expiry adds to them.

**Status (Nov 18, after the download):**
- **Requests 1 and 2 arrived** (opening at-the-money ± 10 strikes, 12:00–close) and were **scored once** in round 4 (`PLAN4.md`, `ANATOMY4.md`).
  - Used: NIFTY Jan 6 – Oct 27, 2026 (43 days) and SENSEX Jul 29, 2025 – Oct 8, 2026 (63 days).
  - The NIFTY 2026 exam and the SENSEX test are **done**. E03.2 failed test 7 on both.
- **Still missing from requests 1 and 2:**
  - Breeze index and futures for NIFTY Nov 3, 9 and 17, and for SENSEX Oct 29, Nov 5 and Nov 12 (the options are there);
  - SENSEX futures for Oct 15 and 22 (thin);
  - SENSEX expiry afternoons before Jul 29, 2025 (Jul 22 partial).

  These days are also seen through live paper or forward quotes, so they would add history but not an untouched exam.
- **Still held open:**
  - **EN16-R** (request 3);
  - **EN15-R** (request 4, Kite);
  - **EN11-R** (request 5), which round 4's EN26 also needs, sub-minute;
  - NIFTY 2020–22 (request 6).
- **Round 4 needs these forward only, from TR01's depth recorder:** EN28's real fill rate and EN26's sub-minute confirmation.

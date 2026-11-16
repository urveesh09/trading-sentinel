# SN286–SN300: the auditor's brief, tested (Nov 16, 2026)

**Owner (Nov 16):** "test it out see if you can agree to it … improve it … slots till 300."

**Source:** `docs/SN286_SN300_RESEARCH_BRIEF.md` (the auditor's brief, committed with the plan).

**Plan:** `PLAN.md`, frozen at `d5cfb8f1` before any number. Every script was frozen before it ran.

## Verdict on the brief

**Agreed and confirmed:**
- **The holiday calls were overstated.** One trade carried the in-wallet gain. Saturday sessions were wrongly admitted, and two 12:30 sessions booked 15:10 exits they could not have had.
- **The partner's +1.51% first minute** is a mid-price move that does not survive executable prices.
- **Order flow and slow repricing** can only be judged on tick data. That exists only from the tick recorder, live since today.

**Changed:**
- The real-quote archive is one snapshot a minute, so SN288 and SN290 run at minute resolution.
- Today is a development day, never scored.
- The forward window and verdict are fixed in code before the first window day.
- SN294 and SN295 are diagnostics; SN292 and SN297 are deferred.
- Partner analysis is shares and ratios only, with no live copying (that would need the partner's consent, and the edge is under a minute).

## Results so far

| SN | Study | Result |
|---|---|---|
| **286** | Corrected holiday replay: weekday full sessions before a weekday market holiday only (derived holidays all match the engine's 2026 NSE list); executable 15:10 exit | Admissions 45 → 40 on DEV (4 Saturdays and Jan 30 2026 removed), 17 → 15 on EXAM-S. ITM call: DEV +22,932 (40), TEST +5,464 (2), EXAM-N +10,050 (9), EXAM-S +12,010 (15). **Without its best day:** +4,176 / −3,030 / −5,097 / −14,410. Matched ordinary days: −35,875 / +6,758 / −7,919 / −1,269. In Gold's wallet: +18,016 over 33 calls, **−741 without the best**; positive months 25 → 28. **A lumpy effect carried by a few big pre-holiday rallies: a cheap forward ledger (SN298), not money** |
| **287** | Where the partner's green days were lost (7 sessions, real minute quotes, shares only) | The give-back alert fired on 4 of 7 sessions. After it, **later entries made 145% of the change; positions already open at the alert gained**. "No new entries after the alert" beat the actual outcome in 3 of 4 sessions (and its random-clock control in 3 of 4); "close everything" in 2 of 4. **Coaching lesson: after the alert, stop adding trades; managing what is open is fine** |
| **288** | The partner's first minute at executable prices (193 buy events, 6 sessions) | Fill → real bid ≥ 60 s later: **−0.22% vs +0.09%** for random entries in the same contract and clock bucket. At 1 minute: +0.08% vs −0.08%. After costs per lot −₹320 vs −₹281. Fills a median **0.35% above the snapshot ask**. Partner beats control in 2 of 6 sessions (sign test p = 0.89). **The timing edge is not tradable after costs** |
| **289** | Tick-recorder qualification | Built (`fw.qualify`): futures minute coverage, max gap, ATM CE/PE coverage, events. Development day Nov 16 (to 09:30): 499 instruments, future gaps ≤ 9 s, ATM coverage 100%. Full-day checks run with the forward window |
| **290** | The real cost hurdle (41 sealed days, one lot) | Round trip (spread + charges): **ATM CE ₹90, PE ₹100, straddle ₹190**; the model is ₹4–9 conservative. A one-minute delay moves the result ±₹310–410 per lot (mean −₹10 to −₹53): noise, not a fixed cost. A 60-second trade needs > ~₹300 per lot of movement with the ₹205 stress |
| 291, 293 | Forward candidates A (futures pressure that persists) and B (the strike that lags the chain) | Frozen in `fw.py`. Development-day plumbing: 6 impulses, a 1.0 s median fill latency, 9 lag triggers, none admitted. **Not scored** |
| 294, 295, 296 | Next-expiry and SENSEX diagnostics; the imbalance-reversal exit challenger | Frozen in `fw.py` on SN291's events |
| 292, 297 | Replenishment fade; expiry mornings | Deferred (unused) |
| 298 | Corrected holiday shadow | Frozen: Dec 24 2026 is the next qualifying date (Nov 23 is NIFTY's shifted expiry) |
| 299 | One-wallet contract for a forward survivor | Written in `PLAN.md`; runs only after an SN300 pass |
| 300 | Forward verdict | Frozen in `fwd.py`: the first 20 qualified NIFTY sessions from Nov 17. Expected around Dec 17–19, scored once. The recorder keeps 35 days, so `python fwd.py collect` must run before ~Dec 20 |

## How to finish (any session)

1. On any evening (and before Dec 20): run `python fwd.py collect` in this folder (research venv).
   - It copies new day folders from the Production container, read-only there, and saves per-day JSON. It prints only qualification.
2. When 20 sessions have qualified: run `python fwd.py verdict` **once**. It writes `results-sn300.json` and reads Gold's gap days from Production, read-only.
3. PASS → SN299 in `ow.py`, then a paper module on the owner's word. FAIL / INSUFFICIENT → record it; no reruns.

## Files

- **Plan:** `PLAN.md`.
- **Code:** `sn286.py`, `sn287_288.py`, `sn290.py`, `tk.py` (packet decoder, a verbatim copy of the recorder's), `fw.py` (qualification and the scorers), `fwd.py` (collect / verdict).
- **Results:** `results-sn286.json`, `results-sn287-288.json`, `results-sn290.json`.
- **Logs:** `logs/` (git-ignored; `sn290-v1-crash.log` kept).
- **Local data:** `_local/` (git-ignored: tick copies, forward JSON).
- **Disclosed fix:** `sn290.py`'s first run crashed before any number (the old export manifest is gone). The day list now comes from SN101's sealed per-minute caches.

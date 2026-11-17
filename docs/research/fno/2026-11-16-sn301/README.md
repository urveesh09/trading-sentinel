# SN301–SN315: protect the forward test, audit Gold's own losses (Nov 16, 2026)

**Owner (Nov 16):** "use these 15 slots to make me a better strategy … ensuring that the losses are cut and nothing unreasonable is happening."

**Source:** the auditor's review, `docs/SN301_SN315_RESEARCH_AUDIT.md`.

**Plan:** `PLAN.md`, frozen at `94c772cd` before any number. Section 0 says where I agreed and where I did not.

## Results

| SN | Study | Result |
|---|---|---|
| **301** | Verified nightly archive (`fwd2.py collect`) | Built. A closed session is copied to a temporary folder, every manifest chunk is checked (bytes, SHA-256), and the copy is published with a receipt (hashes, completeness, events, coverage, Gold label). A failed copy is discarded and retried. Plumbing on Nov 16's live folder: 98 chunks verified, `complete=false` flagged (still recording) |
| **302** | Executable fill / exit / stop contract (`fw2.py`) | Built:<br>• two-sided fresh books (exchange clock, offset 0.63 s);<br>• depth walk for one lot;<br>• exits on time within 10 s, late up to 120 s, otherwise unresolved (the premium lost);<br>• the stop is triggered causally and booked at the next executable bid.<br>8 synthetic cases pass, including the original `fw.hold` defects (a zero-quantity bid filled, a missing exit booked early) |
| **303** | Gold day labels | GOLD / FLAT / UNKNOWN from `sn_gold_days` close rows and `sn_gold_positions` (read-only). Nov 13 = FLAT; a day without a 15:20 close row = UNKNOWN |
| **304** | Matched controls | SN291: the nearest non-candidate impulse of the same sign and similar size (±50%, within 60 min). SN293: the repriced strike with the closest hedge ratio. Each pair is compared at ₹205 and needs ≥ 20 pairs |
| **305** | Affordability | Per trade: the debit; whether it fits the strict ₹3,000 (diagnostic); whether it fits the one-wallet rule (≤ Gold wallet − ₹15,000); whether Gold was open or entering; whether the day's room was used up |
| **300a** | The amended verdict (decides) | Cannot pass on missing evidence. It is INSUFFICIENT when there are UNKNOWN Gold days, fewer than 8 FLAT sessions, fewer than 30 trades on 10 sessions, or fewer than 20 pairs. 4 synthetic verdict tests pass. The original verdict is still reported, as superseded |
| **306** | Where the delay loss happens (SN290's 748 real-quote cases) | Entry one minute late: CE +₹10–19, **PE −₹50–56**, straddle −₹37–39 (absolute ₹259–313 a leg). Exit one minute late: −₹19 to +₹37 (absolute ₹189–245). **Delay is mostly noise; the systematic cost is at the entry, on puts.** Forward latency grids are built into `fw2.py` |
| 307, 308, 309 | Price cap, order-flow change, premise-fail exit | Frozen in `fw2.py`, reported at SN300a (no gate) |
| **310** | Gold v5's loss waterfall (156 trades, Jan 2023 – Oct 2026; parity with the lab exact, ₹8,50,882) | **Losers (86 trades, −₹6.00 lakh):**<br>• first piece −₹5.01 lakh, added piece −₹0.99 lakh;<br>• 78 of the 86 are N11's own exits, 8 are stops;<br>• stop overshoot ₹988 in all; no exit at a minute with no trades.<br>**Winners (70 trades, +₹14.51 lakh):**<br>• added piece +₹2.77 lakh, so adds are worth **+₹1.77 lakh** net;<br>• the 3-ATR extension adds **+₹232** over 16 trades (neutral).<br>**Costs:** fees + stress ₹1.98 lakh.<br>**Concentration:** the best 10 trades are 71% of the net. Puts +₹7.81 lakh, calls +₹0.70 lakh. **Gold's losses are trades whose entry signal failed, capped at the day room, not an execution problem** |
| **311** | The scale-in cash test | Gold v5 **never** commits more than its wallet (0 of 62 adds), so G1 = G0 exactly. G2 ("true cash": 6 more adds) makes +₹62,562 at ₹205 (top 10 +₹55k; months, worst month, worst day unchanged), but only +₹5,724 at ₹400 and less in 2023–24. **Fails the frozen rule: not a candidate; Gold v5's rule stays** |
| **312** | Gold's contracts at real prices (41 sealed days) | ATM to 3 strikes in the money, 1–6 lots at once: the real round trip is ₹0.6–6.5 a lot **cheaper** than the model (weighted by Gold's mix: −₹3.8). No-depth share 0–0.2%. Gold's own trades inside the window: 5 of 10 exit minutes have no snapshot (gaps in the archive); where one exists, the bid depth is 2,080–9,360 units against 390 needed. **The model is confirmed; no contract challenger** |
| **313** | The give-back alert, order by order (frozen partner extract, shares only) | 4 alert sessions; after the alert, 76 new-trade orders and 76 adds. New trades after the alert lost in 3 of 4 sessions (pooled share of the post-alert change: new trades 155%, open inventory −48%). "No new trades after the alert" beat the actual session in **3 of 4**; also "no adds" in 3 of 4. **Supports the coaching line "after the alert, stop opening new trades; manage the open ones"** (the owner's call) |
| **314** | The Dec 7 clock change | See `SN314_CLOCKS.md`. From Dec 7: F&O closes at **15:45**; expiring index contracts stop at **15:30**; the cash auction is 15:30–15:45. About 15 engine files assume 15:40, including the partner companion's windows, the F&O tick, the quote collector, the expiry cutoffs and the tick recorder (15:41). Gold, WK-H and the forward window are unaffected. A runtime fix is a separate Dev slice, on the owner's word |
| **315** | Replication | Frozen in `fwd2.py`: a PASS only opens a second block of L = max(20, ⌈30 / trades per session⌉) sessions (at most 40), scored once |

## Calendar and how to finish

- **Window:** the first 20 verified, qualified NIFTY sessions from Nov 17. Expiry days and the Nov 24 holiday are skipped, so with every day qualifying session 20 is **Dec 23**.
- **Retention:** the recorder deletes day folders after 35 days; Nov 18 lasts until Dec 23.
- **Steps:**
  1. Any evening after 15:50, and at least once before Dec 23: `python fwd2.py collect` (research venv, this folder).
  2. When 20 sessions qualify: `python fwd2.py verdict`, **once**.
  3. A PASS opens SN315's second block. Otherwise record the result; no reruns.
- `python fwd2.py recheck DAY` re-copies a day and compares its hashes.
- `sn286/fwd.py collect` is superseded; do not use it.

## Files

- **Plan:** `PLAN.md`.
- **Code:**
  - `fw2.py` (amended scorer), `fwd2.py` (collector / labels / verdict), `test_fw2.py` (12 tests);
  - `gw.py` (instrumented Gold walk), `sn310_311.py`, `sn312.py`, `sn306.py`, `sn313.py`.
- **Results:** `results-sn306.json`, `results-sn310-311.json`, `results-sn312.json`, `results-sn313.json`, `SN314_CLOCKS.md`.
- **Logs and local data:** `logs/` and `_local/` are git-ignored.
- **Verification:**
  - `python -m pytest -q -p no:cacheprovider test_fw2.py` → 12 passed;
  - SN310's parity is asserted in-script (742 days, max diff ₹0.00).

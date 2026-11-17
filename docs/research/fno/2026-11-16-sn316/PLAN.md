# SN316–SN330: the partner's chart sequence, Gold's entry failures, the 2019–2020 history and Gold V8 (plan, frozen before any number; Nov 16, 2026 ~13:30 IST)

**Owner (Nov 16):** the auditor's ten slots SN316–SN325 (`docs/SN316_SN325_RESEARCH_BRIEF.md`, committed with this plan) plus five of my own, to SN330. "Gold V8 … should be something that we are focusing to develop in real life." Gold v6 and v7 need about ₹5 lakh of margin for WK-H, so they stay on paper.

**Carried over:**
- Gold v5's ₹30,000 starting wallet, its priority, the shared 20% day room, growth and refills;
- the companion rule: premium ≤ wallet − ₹15,000, a ₹3,000 stop inside the day room;
- bought options only, whole lots;
- no margin;
- Production read only, no orders, partner shares only;
- no forward P&L opened before its verdict;
- the SN300a cohort blind.

## 0. Agreements, changes and one correction

- **A correction for the owner:** SN301–SN315 found **no** Gold improvement. "True cash" adds failed the frozen ₹400 test, so Gold v5 is unchanged. Gold V8 starts from Gold v5 as it is.
- **Agreed:** the order of work (archive seal; the clocks on the same events; the Gold baseline before any Gold filter); the 2019 transfer test; the 2020 crash exam once sealed; the five-second chart as a timing rule, not a new signal; counting runaways; testing a Gold filter only on an observable failure, charged for its missed winners.
- **Changed:**
  - **The new packet candidates are scored on the same 20 forward sessions as SN300a, at the same moment** (after session 20, Dec 23), not on a later block. Nothing is opened before then, so both stay blind. A month's wait for a separate block buys little, because any pass must still repeat on SN315's second block.
  - **The one-second history decides the chart-sequence question first.** The development set is the seen Apr 6 – Nov 12 2026 one-second archives; the test is the unused Jan 16 – Apr 2 2026 one-second data, scored once. Packets later confirm execution. SN78's old reservation of that window (its two picks) is discharged first: they are scored there once, exactly as frozen, before SN320 is opened.
  - **The setup level for Gold's entries is N11's own underlying stop** (`initial_stop_underlying`, stored with every N11 trade). It needs no new level definition.
- **Lot size and costs on old years:** 2019–2020 contracts were 75 units. The tests run on today's contract (65 units, today's Zerodha charges, ₹205 / ₹400 stress), so they answer "would today's rule have worked in that market". The 75-unit result is shown as a sensitivity.

## 1. The slots

### Data first

- **SN316: seal the new history by permitted use.** Counts only, no prices:
  - **Data:** NIFTY Jul–Dec 2019 (minutes), Jan–Sep 2020 (minutes) and Jan 16 – Apr 2 2026 (seconds), read from the history database read-only into a sealed copy.
  - **Per quarter:** sessions, expiries, sessions without the at-the-money pair, halts (Mar 13 2020: no 09:30 bar), option minutes at 15:15 for the WK-H strike, and futures minutes at each 15-minute hedge mark;
  - **plus:** the Apr 2 2020 expiry that came back empty (the expiry moved to Apr 1 for a holiday);
  - **plus:** lot sizes by date, and the SHA-256 of each sealed copy.
  - A gap is never filled forward.
  - **Uses:** 2019 → SN318 only; 2020 → SN317 only; Jan–Apr 2026 seconds → SN78's discharge, then SN319–SN322's test.
- **SN317: the WK-H crash exam** (`sn231/CRASH_TEST_2020.md`, `sn248.py`, frozen), run once, as registered, after SN316.
  - A week whose 15:15 straddle or hedge marks are missing is reported as **unresolved**, never inferred (the Apr 1 2020 expiry week is the known risk).
  - Reported: March, the worst month, per-week admissions, and hedges that could not be placed during the halt.
- **SN318: does a one-minute break-and-hold transfer to 2019?**
  - **Rule (frozen):**
    - the level = the high / low of the 3 completed one-minute index bars;
    - an event = a completed minute closing outside the level, with the next completed minute also closing outside (held);
    - buy the at-the-money call (up) or put (down) at the following minute's modelled ask (house spread table);
    - hold 15 minutes with a ₹3,000 stop on the minute lows;
    - 09:30–14:30, non-expiry sessions, one event per 15 minutes.
  - **Control:** 200 random-clock books with the same number of trades per session and the same side mix.
  - **Reported:** development (NIFTY Apr 2022 – Oct 2026, seen) and each 2019 quarter separately (unseen), all sessions plus the quiet-day proxy (yesterday's ADX < 30, computed from the sealed minutes).
  - **Pass in 2019:** net > 0 at ₹205 and ₹400 in both quarters, and above the random median.

### The partner's chart sequence on one-second data (development Apr–Nov 2026, test Jan 16 – Apr 2 2026)

- **SN319: one event file across clocks.**
  - **Event:** the first completed 30-second index bar (aligned to :00 / :30) that closes outside the level of the 3 completed one-minute bars before it. Calls up, puts down; one event per 300 s; 09:30–14:30; non-expiry sessions; only when the opening-ATM strike (the archive's contract) is within 100 points of the index.
  - **Stored per event:** whether the move still held after 30 s; the five-second pattern; the same pattern on ten-second bars; and entries at +5 / +10 / +30 / +60 s. Each is priced with the same exit and costs.
  - **Diagnostic:** the bar grid shifted by 2 s, once.
- **SN320: the lead challenger, a held break then a five-second pullback.**
  - **A (break):** buy at the first second after the break bar completes.
  - **B (SN320):**
    - after the break, wait for the first completed five-second bar that closes against the move (a pullback) but whose extreme stays outside the level;
    - then the next completed five-second bar must close in the break's direction;
    - buy at the next second;
    - the lifetime is 120 s; otherwise no trade.
  - **C (delay control):** buy 30 s after the break, with no condition.
  - **Execution:** one lot (65); the modelled ask in, modelled bid out (the house table on the second's close); exit 300 s after entry, or the ₹3,000 stop checked every second on the bid of the second's low; Zerodha charges + ₹205 (₹400).
  - **Score:** net per original event (no trade = 0). Runaways are events B skipped while A's trade won; they are counted.
  - **Pass (test, once):**
    - B's net per event > A's and > C's at ₹205 and ₹400;
    - B's net > 0 at both stresses;
    - positive without its best day;
    - ≥ 30 trades on ≥ 10 sessions.
- **SN321: the second challenger, a premium-surge gate.**
  - At B's entry second, over the previous 30 s, at the opening-ATM strike: directional = (ΔC − ΔP) / 2, common = (ΔC + ΔP) / 2 (the closes as mids).
  - **B+G** skips the trade when common > 0 and common > 0.25 × |directional|.
  - Same events, same pass rule against B.
- **SN322: what was reachable.**
  - Per event: the hindsight ceiling (the best modelled ask-to-bid round trip within 120 s of the break and 300 s of holding, after costs).
  - Whether ₹750 net was reachable before the stop, for A and B.
  - The share of events that never offered an affordable ₹750.
  - A labelled ceiling, never a strategy.

### Gold (seen data, Gold v5 at ₹30,000 growing, 156 trades; `sn301/gw.py` parity)

- **SN323: when do Gold's entries fail?** For every trade, from N11's stored underlying stop and entry:
  - the minute the future first covers 25%, 50% and 100% of the distance to that stop;
  - the adverse and favourable excursion in the first 1, 2 and 5 minutes;
  - classes: failed within the first minute, within 5, later, never.
  - Reported for losers and winners, by expert and side.
  - Answers whether a failure signature is observable before a decision it would change.
- **SN324: one targeted Gold challenger, conditional on SN323.**
  - **Class:** the expert with the largest losing total among those with ≥ 15 trades (mechanical; TPB by SN310).
  - **Candidate:** that class's entries wait one minute and are cancelled if, at that minute's close, the future has covered ≥ 25% of the distance to N11's underlying stop against the trade. Otherwise they enter at that minute's ask with Gold's unchanged exits and risk.
  - **Control:** the same class always entering one minute late (Gold's existing `late` path).
  - **Promotion to a paper shadow** only if, against the control at ₹205 **and** ₹400:
    - the losses avoided exceed the winners missed;
    - net is higher;
    - refills are not higher;
    - positive months and the worst month are not worse;
    - all of these also hold in both halves (2023–24, 2025–26).
  - Also reported against Gold v5 on time.
- **SN325: the wallet and the wage shortfall** (forward, scored with SN300a after Dec 23). SN320-on-packets (`fw3.py`, frozen here) and SN291 / SN293 in one chronological Gold wallet:
  - net per eligible FLAT session including skips, withdrawals actually funded, sessions funded, the longest dry run, drawdown and refills;
  - Gold orders displaced;
  - the wage shortfall at ₹750 a session.
  - **SN320 on packets:** the futures mid replaces the index; the current front-weekly ATM option; `fw2`'s execution contract; the same pass rule as SN300a.

### My five

- **SN326: Gold v5 on a year it has never seen.**
  - N11's pre-registered 2022 exam (`simulation/2026-11-02-fno-n11/EXAM_2022_N11.md`, written Nov 2 before 2022 existed here) is run if the N08 → N11 pipeline can be pointed at the 2022 data within this round. Gold v5 is then replayed on that N11 / R0.85 stream with no change.
  - 2022's price rows were read by buyer studies (SN196, SN209), but never by N11 or Gold.
  - If the pipeline cannot be run safely (RAM beside Production, time), its blockers and a step plan are written instead.
- **SN327: Gold's real-money risk.** From Gold v5's day log:
  - the largest refills in any calendar month and in any 20 sessions, against the wallet then;
  - the longest losing run, and the worst month against the wallet.
  - Whether the owner's limit (a refill never more than the wallet's full amount) has ever been crossed.
  - If it has, a monthly cap (no new Gold trades for the rest of a month once refills reach the wallet) is replayed and reported, with what it costs.
- **SN328: the Gold V8 specification and real-money gates.** Gold V8 = Gold v5's rules plus only what passes here (SN324, SN320 / SN321 after their forward block), with:
  - the real-money execution contract (marketable limit with a price cap, stop orders, the scale-in, the 15:15 failsafe, reconciliation with Kite, kill switches);
  - the paper-to-real gates.
  - A document; building the real-money module is the next slice, on the owner's word.
- **SN329: the Dec 7 market-hours fix (Dev).**
  - Session facts by date: derivatives close 15:40 until Dec 4, 2026 and 15:45 from Dec 7; expiring index contracts stop at 15:30 on their expiry day from Dec 7.
  - Used by the modules in `sn301/SN314_CLOCKS.md`, with tests for both regimes.
  - Deployed only on the owner's word.
- **SN330: verified nightly collection.** A Windows scheduled task (weekdays 16:05 IST) runs `sn301/fwd2.py collect` and logs to `sn301/logs/`. It is read-only on Production and removable with one command. Plus this round's decision report.

## 2. Acceptance checks

- SN316's seal is written (counts, hashes) before any price row is read.
- SN323 and SN324 run on the `gw.py` replay with parity asserted (₹8,50,882).
- SN320 and SN321's code is committed before the Jan–Apr seconds test is opened; SN78's picks are scored there first.
- `fw3.py` is committed before Nov 18's session is collected.
- SN329's tests pass, and the engine suite's touched areas pass.
- Every result file is written once.

## 3. Rollout

- **Research:** in `docs/research/fno/2026-11-16-sn316/`.
- **Runtime:** SN329 is in Dev only (a separate commit); deploying it needs the owner's word.
- **SN330's task:** removed by `schtasks /Delete /TN SentinelTickCollect /F`.

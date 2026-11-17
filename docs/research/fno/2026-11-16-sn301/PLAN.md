# SN301–SN315: protect the forward test, audit Gold's own losses (plan, frozen before any number; Nov 16, 2026 ~11:00 IST)

**Owner (Nov 16):** "use these 15 slots to make me a better strategy … each SN slot should be utilised properly so that we are able to gain marginal learning at least if not success … ensuring that the losses are cut and nothing unreasonable is happening."

**Source:** the auditor's review `docs/SN301_SN315_RESEARCH_AUDIT.md` (written at Dev `7f8547d0`; committed with this plan, as received).

**Rules carried over:** research only in Dev; Production is read only (the tick recorder's folders and the SN Gold tables, through `docker exec`/`docker cp`, never written); no orders; no runtime change in this round; the partner's data as shares and ratios only; hashed policy files untouched; no forward P&L opened before its verdict.

## 0. Where I agree with the auditor, and where I do not

**Agreed, and fixed in this round (before the first eligible forward session, Nov 18):**
- **The verdict can pass on missing evidence** (`fwd.py`: a failed Gold query satisfies the gap test; an empty control is "beaten"). Fixed in SN303 / SN304 / SN300a.
- **The execution model is too kind** (`fw.hold`: a bid with zero quantity can fill a lot; the last packet is booked before the planned exit; any later bid counts as the planned exit; the stop fills at the detecting packet). Fixed in SN302.
- **The collector can freeze a partial copy forever.** Fixed in SN301.
- **Raw totals against a control traded at a different frequency** say nothing about the signal. SN304 adds matched, paired controls.
- **Affordability must be known before a pass means anything.** SN305.
- **Calendar:** with every recording qualifying, the 20th eligible session is **Dec 23**, not Dec 17–19 (Nov 17, Nov 23, Dec 1, 8, 15, 22 are NIFTY expiries; Nov 24 is a holiday). Nov 18 survives the recorder's 35-day pruning only through Dec 23, so the archive must be taken before then.
- **Gold's scale-in cash test values open lots at the new ask, not at what was paid.** SN310 / SN311 measure it on Gold's replay.

**Not agreed, or changed:**
- **The ₹3,000 "full-debit" reading of SN299.** SN299's text ("debit plus fees within the ₹3,000 sub-budget") is my wording error: it contradicts SN291's own ₹15,000 premium rule and the one-wallet contract every gap-day leg has used since SN251 (`ow.py`: premium ≤ wallet − ₹15,000; a ₹3,000 stop, 10% of the wallet, inside the shared 20% day room). The owner's limit is that a loss can never exceed what can be refilled (the wallet); a bought option with premium ≤ half the wallet meets it. **The decision uses the SN251 contract** (with the stop's real slippage, SN302). The strict reading (whole debit ≤ ₹3,000, i.e. an ask ≤ 46.15 points at 65 units) is reported beside it as a diagnostic, not as a gate.
- **The original freeze is kept and still reported.** `fw.py` / `fwd.py` (`d5168b0f`) stay byte-identical. Every day is scored by both the original scorer and the amended one (`fw2.py`); the original verdict is recorded as "original implementation, superseded", and **only the amended verdict (SN300a) decides**. Signals, thresholds, the start date and the economic gates are unchanged.
- **SN293's quote-age test** moves from receipt age to the exchange timestamp (the same 1-second threshold). This is a data-validity correction (a resent, unchanged book has a fresh receipt), not a new signal rule.
- **SN312 (a cheaper contract for Gold)** is done as a cost audit first: Gold buys 1–3 strikes in the money, where the house spread model (by premium) may be too kind. A contract challenger is replayed only if the audit says the model is wrong by more than ₹100 a lot (rule below).
- **SN313** is done as an order-level re-attribution of SN287 on the frozen partner extract (what the auditor asked for), plus a frozen protocol for the post-alert behaviour since the give-back stop went live (Nov 13). No wording trial: the wording is the owner's call.
- **Scheduling.** The verified collector can run any evening; a Windows scheduled task is offered to the owner, not registered by me.

## 1. The slots

### Protect the forward test (SN301–SN305, SN315), frozen before Nov 18

- **SN301: a verified nightly archive** (`fwd2.py collect`).
  - A day is taken only after its session (date < today IST, or now ≥ 15:50 IST).
  - It is copied to a temporary folder first. Every chunk named in `manifest.json` must exist with the manifest's bytes and SHA-256.
  - Then it is renamed into `_local/archive/<day>/` with a receipt `_local/receipts/<day>.json`:
    - file hashes (the manifest's, plus our own for `instruments.jsonl`, `events.jsonl` and `manifest.json`);
    - `complete`, connects and downs from `events.jsonl`;
    - SN289's coverage;
    - the Gold day label (SN303).
    - No money.
  - A copy that fails verification is discarded and retried on the next run.
  - A day verified with `complete=false` (the recorder never saw its own close) is kept and flagged; SN289's coverage decides if it qualifies.
  - A second copy of a verified day must reproduce the receipt's hashes (`fwd2.py recheck`).
- **SN302: the execution contract** (`fw2.py`), declared here:
  - **Valid book:** best bid > 0, best ask > 0, ask > bid (no crossed or locked book).
  - **Fresh book:** the packet's exchange timestamp is ≤ 2 s behind its receipt, after removing the day's clock offset (the median receipt − exchange time on the front future).
  - **Entry:** the first valid fresh option packet received 0.5–2.5 s after the decision whose five ask levels hold ≥ one lot. The price walks the ask levels for one lot. Otherwise "missed".
  - **Exit:** at a planned time T, the first valid fresh packet received ≥ T + 0.5 s whose five bid levels hold ≥ one lot, at the bid walk.
    - Within T + 10 s it is "on time".
    - Up to T + 120 s it is "late" (booked at that price).
    - After that it is "unresolved": booked as a loss of the whole premium plus charges, and counted.
  - **Stop:** triggered causally on a valid packet whose best bid makes the net ≤ −₹3,000. It executes as an exit order from that receipt (+0.5 s, depth, walk), so the slippage is booked.
  - **Clocks:** a decision at t uses only packets received ≤ t.
  - Costs: Zerodha charges + ₹205 / ₹400 per lot (unchanged).
  - Synthetic tests (`test_fw2.py`) must give the declared outcome for:
    - zero ask depth, zero bid depth;
    - a crossed book, a stale (resent) book;
    - a same-frame packet;
    - a missing exit;
    - a delayed and slipped stop;
    - an unresolved exit.
- **SN303: provable Gold day labels.** From Production's `sn_gold_days` (the 15:20 day-close row) and `sn_gold_positions`, read-only, captured each evening by SN301:
  - **GOLD** = a close row with trades > 0 and the same number of positions dated that day;
  - **FLAT** = a close row with trades = 0 and no positions;
  - **UNKNOWN** = no close row, or the counts disagree.
- **SN304: matched controls** (`fw2.py`).
  - **SN291:** each candidate trade is paired with the non-candidate impulse of the same session and sign nearest in clock (within 60 minutes) whose size is within ±50%. Each control is used once and traded with the same execution, independently of the candidate's busy state.
  - **SN293:** each candidate trade is paired with the repriced strike (ratio ≥ 0.7) whose hedge ratio β is closest to the target's, at the same decision time.
  - "Beats its control" = the mean paired difference (candidate − control, ₹205) > 0, with ≥ 20 pairs. The original controls (all impulses; the most-repriced strike) stay as activity references.
- **SN305: affordability at the front.** For every candidate decision:
  - the debit (walked ask × lot + buy-side charges);
  - "fits the strict ₹3,000 debit" (diagnostic);
  - "fits the one-wallet contract" (debit ≤ that day's Gold wallet − ₹15,000; Gold's wallet from `sn_gold_days.wallet_before`);
  - "blocked: a Gold position is open" (from `sn_gold_positions` entry/exit times);
  - "liquidated by a Gold entry" (a Gold entry inside the hold sells the leg at that moment, at the SN302 exit).
  - SN299's wallet net = admitted trades only.
- **SN300a: the amended verdict** (decides; `fwd2.py verdict`, once).
  - **Window:** the first 20 sessions ≥ Nov 17 that SN301 verified and SN289 qualified (SN289's thresholds unchanged).
  - **INSUFFICIENT** when any of these holds:
    - any of the 20 sessions has an UNKNOWN Gold label;
    - fewer than 8 FLAT sessions;
    - fewer than 30 executed candidate trades on fewer than 10 sessions (unresolved trades count as trades);
    - fewer than 20 matched pairs.
  - **PASS**, for each of SN291 and SN293, needs all of:
    - net > 0 at ₹205 and at ₹400 (SN302 execution);
    - the mean paired difference against the matched control > 0 (SN304);
    - positive without its best session;
    - the FLAT-session subset > 0, with net per FLAT session reported (zero-trade sessions count);
    - the SN299 wallet net on FLAT sessions > 0.
  - Otherwise **FAIL**.
  - Also recorded: the original verdict (fw.py rules on the same 20 days, labelled superseded); entry and exit fill rates; missed and unresolved counts; the CAS 2.0 tag (sessions before / from Dec 7).
- **SN315: replication before anything is built.**
  - A PASS in SN300a only opens a second block: the next L qualified sessions after the 20th, scored once by the same code.
  - L = max(20, ⌈30 / (block-1 candidate trades per session)⌉), capped at 40. It is computed from block 1's counts only, never its P&L.
  - Promotion to a paper module needs a PASS in both blocks and the owner's word.
  - The decision report gives, per block:
    - net per FLAT session, the worst three days, the direct leg net;
    - Gold P&L foregone (liquidations);
    - the most cash the leg had open.

### Forward comparisons on the same events (SN306–SN309; reported at SN300a, no gate)

- **SN306: where the delay loss happens.**
  - **Now, on the sealed minute archive (SN290's 748 cases):** the entry alone one minute late, and the exit alone one minute late, against on time. Signed mean, absolute mean, 5th / 95th percentiles per kind and hold.
  - **Forward:** for SN291 / SN293 candidate decisions, entry latency 0.5 / 1 / 2 / 5 s with the exit on time, and exit latency 0.5 / 1 / 2 / 5 s with the entry on time. Misses stay in the denominator.
- **SN307: a price-protected entry.** The same decisions. The order is cancelled when the walked fill price is above the decision-time best ask + ₹0.10 (two ticks). Net per original opportunity: skipped winners and losers both count as 0.
- **SN308: changing book pressure.** On SN291's impulses, the futures' best-level order-flow imbalance (Cont, Kukanov and Stoikov) summed over the 10 s before the impulse; the condition is that its sign equals the impulse's, with SN291's "not retraced by half at +5 s". This is compared with SN291's static imbalance condition and with both together, on the same execution. Sign only: no new magnitude threshold.
- **SN309: an exit when the premise fails.** On SN291's candidate fills, exit early on the first futures packet where either:
  - the 10-second mean imbalance has the opposite sign with |I| ≥ 0.20; or
  - the future's mid is back beyond the impulse's start.
  - The maximum hold is 60 s, the same as the fixed exit. Its own busy state; SN302 exits.

### Gold's own losses (SN310–SN312), on Gold v5's frozen replay (seen data; measurement and a correction test)

- **SN310: Gold's loss waterfall.** An instrumented copy of the lab's `walk` (byte-for-byte the same rules; the frozen files are not edited). It must reproduce SN252's day nets for Gold v5 at ₹30,000 growing (stop 3), Jan 2023 – Oct 28 2026, to ₹0.01 before any attribution. Per trade:
  - the first piece's net and the added piece's net (each with its charges and the ₹205 stress);
  - the extension's contribution = the actual net − the net had every open piece been sold at N11's exit minute (trades that extended);
  - stop overshoot = (stop − fill) × quantity on stop exits;
  - exits marked without a traded minute;
  - by expert (EFF / OR20 / SHIPPED / TPB) and by side.
  - Losers and winners ranked by rupees, frequency and dependence on the top 10.
  - Production's paper ledger has no Gold trade yet (`sn_gold_positions` is empty on Nov 16), so it is stated, not reconciled.
- **SN311: the scale-in cash test.** Three arms on the same replay, the ATR trigger, the 20% room and the whole-position stop unchanged:
  - **G0** = Gold v5 as frozen: added lots n = max(1, ⌊W / (ask × lot)⌋ − open), allowed when (open + n) × ask × lot ≤ W.
  - **G1 "never more than the wallet"** = G0's rule, and also the cash actually paid for the open lots + the new lots + buy-side charges ≤ W. If not, n is reduced to what fits (≥ 1), else no add. This is what Gold v5 can really do in an account holding only its wallet.
  - **G2 "true cash"** = n = ⌊(W − paid − buy-side charges) / (ask × lot)⌋ ≥ 1, replacing G0's mark-to-market test.
  - Reported at ₹205 and ₹400, whole period and both halves (2023–24, 2025–26):
    - net, refills, positive months, worst month, worst day, maximum drawdown;
    - adds made / changed;
    - G0's over-wallet commitments (count and the largest excess);
    - the sum of the 10 best trades.
  - **Decision (frozen):**
    - G1 is the honest real-money form of Gold v5. If G0 ever commits more than the wallet, G1 replaces G0 as the reference for any real-money decision, whatever its P&L.
    - G2 becomes a Dev candidate only if, against G1, at ₹205 and at ₹400 and in both halves, all of these hold: net ≥ G1; positive months ≥ G1; worst month ≥ G1; refills ≤ 1.10 × G1; worst day ≥ 1.10 × G1's (no more than 10% worse).
    - Otherwise it is recorded and dropped.
- **SN312: Gold's contracts at real prices.** On the sealed minute archive (41 days, Sep 10 – Nov 12): NIFTY front-weekly calls and puts at ATM and 1, 2, 3 strikes in the money, every 15 minutes 09:30–15:00. Measured:
  - the real cost of buying and selling n = 1, 2, 3, 4, 6 lots at once (walking the five levels; "no depth" counted), against the model (half the P75 spread table each side);
  - plus Gold's own replayed trades inside the archive window, at their entry and exit minutes.
  - **Rule (frozen):**
    - If the real cost exceeds the model by > ₹100 a lot at the depth and lot count Gold uses, Gold v5 is replayed with that measured excess added per lot, against the same replay buying N11's strike (no in-the-money step).
    - The challenger is reported as a candidate only if it beats Gold v5 on net, positive months and worst month under the corrected costs.
    - Otherwise the model is confirmed and nothing is replayed.

### The partner and the clocks (SN313–SN314)

- **SN313: the give-back alert, order by order.**
  - **On the frozen partner extract (SN287's sessions):** every BUY after the reconstructed alert is classified as a new episode (no open position in that underlying and side) or an add to an open position; every SELL as a reduction. Each class is valued at the archive's executable bids to the session's end, with charges.
  - Reported as shares of the post-alert change only. It tests the coaching line "after the alert, stop opening new trades; manage the open ones".
  - **Forward protocol (frozen, read at SN300a's date):** for every give-back alert sent by Production since Nov 13, the partner's BUY orders in the hour before and after, and the session's later change, as shares and counts, against non-alert sessions at the same clock. Messages only; no order path.
- **SN314: the Dec 7 clock change (NSE CAS 2.0, FAQ updated Nov 6, 2026).**
  - **The FAQ says:**
    - from Dec 7 equity derivatives trade until **15:45** on all days;
    - on expiry days, expiring index contracts stop at **15:30**;
    - the closing auction runs 15:30–15:40, then 15:40–15:45, a transition to 15:50 and the post-close to 16:00;
    - final settlement stays the index from the constituents' VWAP of the last 30 minutes of continuous trading.
  - **Checked against the code** (Dev and the Production checkout, read only):
    - `market_calendar` (`DERIVATIVES_CLOSE_TIME` 15:40, the CAS phases);
    - the tick recorder's 15:41 stop;
    - Gold's 15:10 / 15:15 clocks;
    - WK-H's 15:15 entry and its expiry hedge close (15:24);
    - the paper books' closing marks;
    - the forward window (decisions end at 14:30).
  - Output: a list of what breaks or misses minutes from Dec 7. A runtime change is a separate Dev slice on the owner's word.

## 2. Acceptance checks

- `test_fw2.py` passes every synthetic case above, before any recorded day is scored.
- `fw2.run` on the development day (Nov 16, never scored) runs end to end and prints only counts.
- The SN310 replay reproduces SN252's day nets exactly before any attribution.
- G0 in SN311 equals Gold v5's frozen totals.
- Every result file is written once (a rerun refuses).

## 3. Rollout and rollback

Nothing is deployed. Every file is new and lives in `docs/research/fno/2026-11-16-sn301/` (code, results, README), apart from shared documents (history, guide, plan, handover entries). Rollback is deleting the folder.

# Independent review of EN71–EN85

Reviewed November 18, 2026, Dev HEAD `2173546391116be8b8ac5ac449dce858a2542d0b`.
Production checkout read-only: `55b5e9422d0262091719042daf4a72dbe9c94d6c`.
This is research verification and a new proposal, not a runtime/deployment audit.

## What was independently checked

`audit.py` and `verification.json` contain the reproducible receipt.

- All **39** source/input files in round 7's transitive source freeze match.
- **467** aggregate financial identities across **67** stored arm/index day views
  reconcile. Stored ticket-net totals reconcile where ticket detail exists.
- Fresh ordinary/adverse replays reproduce E03_env and EN75 on both indices and
  EN83 on NIFTY: **10 metric views**. Ordinary per-day net, trade count, fees,
  marked worst and minutes held agree. Two additional ordinary price-control
  replays also match the stored aggregate metrics.
- The signal functions and EN71/EN85 source paths were inspected. No new strategy
  was scored, no holdout opened and no original score overwritten.

| NIFTY arm | Ordinary net | Adverse net |
|---|---:|---:|
| E03_env | 3,006.43 | 2,245.82 |
| EN75 | 5,844.44 | -1,422.89 |
| EN83 | 4,722.49 | -3,886.23 |

SENSEX EN75 also reproduces: -19,200.14 ordinary and -22,183.82 adverse. The
published decision to promote none is supported. This review did not rerun the
entire score, ML training, 40-seed nulls, packet decoding, wallets, full parity
suite or engine tests. Those remain developer-reported evidence, not fresh checks.

## F1 — EN85 does not yet give EN83 a working forward OI source

`prep7.py:149–170` selects OI from the fixed sealed exam databases, including
`2026-11-17-expiry-en/_local/exam2026.sqlite` for every 2026 date. `fwd7.py` builds
new tapes from the separate operations history database but calls that unchanged
`oi83` reader. The new tape does not supply its OI to the reader.

A read-only source check for NIFTY Nov 17 finds **zero** positive-OI option rows
in the sealed exam and **97,628** in the operations store. That latter inventory
is across stored intervals/times, not the 8,700-row minute timing sample. The
important fact is the source separation. New post-exam dates cannot acquire OI
by downloading more index/futures minutes into the other database. The likely
outcome is all-NaN OI and zero EN83 signals, misreported as inactivity.

`mechanics.py` also exercises the reader on a minimal future-date tape: every
Nov 17 OI cell is missing, and a 2027 date raises `KeyError('2027')` because the
source map ends at 2026. This test does not fabricate a historical trade outcome.

Repair in a versioned runner: attach a sealed per-session OI panel to the tape
or explicitly pass its read-only snapshot/data identity. Require OI coverage for
OI-dependent arms. A real zero is not missing, and an unavailable OI panel is not
a valid zero-trade session. Regression: a synthetic future-date tape with a known
crossing must fire without changing the historical exam; missing OI must be
MISSING for EN83 while unrelated arms can remain eligible. Preserve the frozen
research files and log an infrastructure erratum; do not silently rewrite them.

## F2 — the forward receipt needs stronger completeness and recovery semantics

Source observations, not demonstrated corrupt-ledger incidents:

- `coverage` counts all future series together rather than the selected dated
  front contract. It accepts 150/210 minutes even if the decision window has a
  concentrated gap. Option count alone does not prove both needed strike sides.
- `discover` uses a short hard-coded calendar plus expiries already present in
  option data. Once the calendar ends, a completely undownloaded expiry can be
  invisible rather than MISSING. Read an authoritative dated calendar independently
  of whether that day's options were downloaded.
- MISSING rows enter the same `done` set as scored rows. If the runner is invoked
  before data arrive, a later invocation never retries that date. Define PENDING
  before a frozen acquisition deadline and MISSING after it. Late data can have
  a linked sensitivity receipt without silently changing the primary cohort.
- Plain JSONL append/read has no lock, atomic transaction or recovery for a final
  partial line. Sequential idempotence is useful but does not establish crash or
  concurrent-worker safety. Test crash-before/after commit, duplicate workers and
  truncated tails with a versioned transactional ledger.
- `status` reports review_due but has no review branch applying the promised
  forward classification/wallet analysis. Describe that part as still to implement.

These are prerequisites outside the ten strategy IDs. No Production edit is
needed to correct the research runner.

## F3 — EN71 loses unsold quantity in a partial-exit case

`frontier7.py:49` accepts the first sale with `fs > 0`, then values every bought
lot at its price. `_exe` can return fewer sold lots than requested.

Synthetic witness: buy two lots at 10; exit fills one at 9. The diagnostic reports
both lots sold, net -180.04, and no unresolved remainder. One lot is actually
unsold. Repair the quantity ledger, charge each actual exit order, retry remaining
lots and distinguish unresolved marks/assumptions. The same pattern also appears
in the older EN61 research label helper (`en_ml6._sell_from`/executors); audit
consumers rather than assuming parity proves correct mechanics.

Scope of impact checked: **7,246 NIFTY and 2,296 SENSEX** canonical actions at
delay zero, ordinary fills; **5,802 and 1,995** filled actions respectively. None
had a partial first sale. This witness therefore does **not** overturn those
checked historical actions. Delayed/adverse populations and old ML labels were
not scanned here. Keep this limitation explicit.

## F4 — the option-market information remains a lead, not an established edge

1. **OI does not identify the initiating side.** EN83 is an empirical put-minus-
   call OI-change statistic. Every open contract has a long and short. Calling it
   confirmed writer flow, dealer gamma or short covering is unsupported. Positive
   predictive information, if found prospectively, would not need that story.
2. **EN75's historical bid/ask intervals are synthetic.** `syn75` builds them
   around separate minute last-trade closes with a spread function. Nonzero
   minute volume does not synchronize call, put and future at the decision time.
   These are not observed executable parity violations. Nov 17's packet pilot
   is useful but one day cannot validate 2023–26 lead/lag effects.
3. **The control policies do not keep identical funded clocks.** EN75 has 177
   parents, its momentum control 163, with 148 shared day/minute clocks. EN83 has
   167 versus 163, with 161 shared clocks. Stops, sizing, admission and remaining
   room change subsequent opportunities. Their overall P&L difference is a policy
   comparison; it is not a pure estimate of the information in the side. Add a
   canonical matched-clock one-lot diagnostic, followed by the funded policy test.
4. Beating the 90th percentile of **40** random-side books is a preliminary
   screen, not strong discovery evidence after many adaptive rounds. Agreement on
   81/93 shared days is not independent confirmation from two sources. Examine
   aligned events, residual information and overlap, rather than multiply votes.
5. Aggregate event hit rates mix overlapping windows and signals outside funded
   admissions. Weight/cluster by expiry and report event population and funded
   population separately. The 56% figure is not automatically the probability of
   winning a financed option trade.

The official OI explanation and research disagreements are linked in the new
handoff. These caveats narrow the mechanism claim; the reproduced P&L is unchanged.

## F5 — the accuracy hurdle and test calibration are conditional

EN71 varies an oracle-informed predictor's errors independently of move size.
Its break-even interpolation is useful for that action library, clock, fills and
fixed horizon. A real predictor may be right on small moves and wrong on large
ones, or the reverse. There is no universal 61% requirement. Direction right is
also different from an option trade winning. Native E03 exits and the diagnostic's
fixed eight-minute hold are distinct policies.

One null rejection in 20 is compatible with 5%, but does not establish correct
false-positive size. A descriptive exact binomial 95% interval is **0.13%–24.87%**
(itself assuming independent calibration trials). The planted effect is **100 per
traded session**, not necessarily per trade: `harness` adds 100 if any trade occurred.
The reported 3/20 is a noisy power estimate under that random-entry control and
effect construction, not a universal detectability statement for every strategy.
Week sign flips require a suitable symmetry/exchangeability null; one-week blocks
do not by themselves solve regime dependence or cross-week autocorrelation.

Do not fix power by lowering the pass bar after observing these results. Show
power for the registered effect size, activity and calendar dependence; expand
calibration with synthetic skewed/heavy-tailed/dependent nulls before new evidence.

## F6 — the passive estimator's LOWER label is still too strong

`pk7.rest2` accepts a fresh best ask strictly below the order limit as a whole
fill, without checking offered quantity or a new trade. `mechanics.py` supplies
an old last trade, unchanged cumulative volume and one offered unit below a
65-unit order's limit. LOWER returns all 65 units filled. That quote does not
prove a whole-order exchange execution or establish a guaranteed lower bound.

Rename these as conditional proxy scenarios unless a genuine identified bound
can be defended. Treat visible crossing quantity as at most the observable
marketable opportunity, preserve whole-lot restrictions and distinguish a real
post-arrival traded-through witness from a quote opportunity. Even traded-through
evidence needs stated counterfactual/no-own-impact assumptions for a paper order.
Do not treat an aggressive cumulative-volume proxy as known executed volume at
one price. No historical affected-count or corrected P&L is claimed here. EN55's
registered strategy stays unchanged; estimator corrections need a versioned
sensitivity result, never a silent strategy or result replacement.

## Verification and state

Command, from Dev:

```powershell
& 'C:\Users\Urveesh\sentinel-ml-venv\Scripts\python.exe' -B docs/research/simulation/2026-11-18-expiry-review-en86/audit.py
```

Final exit 0, `FOCUSED AUDIT PASS`, 51.09 seconds. Python 3.11 scientific environment;
helpers use existing data read-only and temporary in-process function substitutions
for the synthetic quantity witness, restored immediately. No network/broker call.

The first audit-helper attempts exposed differences in stored detail schemas:
some controls have no stored ticket detail and selector rows omit fees. The helper
was corrected to check fields actually present and freshly replay the two controls.
Original results were never changed. This is not a strategy re-score or re-freeze.

Additional command: the same Python executable with
`-B docs/research/simulation/2026-11-18-expiry-review-en86/mechanics.py`, exit 0.
Its source-routing and one-unit passive witnesses are in `mechanics.json`.

All work in this review is new Dev research/documentation. Existing dirty shared
docs and other agents' files remain untouched. No runtime source, migration,
configuration or capital change; no commit, push or deployment performed.

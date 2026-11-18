# Versioned research corrections, before round8 financial scoring

The independent review is `../2026-11-18-expiry-review-en86/AUDIT.md`.
Earlier frozen files/results remain byte-for-byte unchanged. Corrections live
in this folder; these are research mechanics, not runtime strategy changes.

1. **OI routing:** data8.Source explicitly names the snapshot and capability;
   read_panel has no year-to-exam mapping and preserves true zero separately from
   missing. A 2027 synthetic read works. SENSEX's zero-filled provider field is
   not asserted to be actual OI. Historical source identities and array hashes
   are bound in freeze8.json.
2. **Quantity:** execution8.liquidate retries only remaining lots, charges each
   sell order and separates unresolved full-premium assumptions from simulated
   fill cash. Fixed-action labels use it. Main policies reuse the reconciled day
   loop, whose ordinary control orders match frozen round7 on 2,340 arm-days.
3. **Passive quotes:** execution8.passive_scenario is explicitly conditional.
   A one-unit ask never fills a whole lot. Quote opportunities are quantity-
   limited; post-arrival trade evidence is a separate volume-attribution proxy,
   never a confirmed exchange fill or guaranteed lower bound. Native EN55 remains
   the frozen minute-model reference; its registration/results were not replaced.
4. **Receipts:** forward8/runner8 provide explicit calendar/snapshot hashes,
   selected-contract/window coverage, missing-score handling, retryable PENDING,
   unique transactional final receipts and lease/crash checks. No direct repair
   to the old EN85 ledger and no Production scheduler registration.
5. **Inference:** the initial block4 bootstrap failed dependent-null calibration
   (115/1,000 false positives) before candidate financial scores were inspected.
   Its rejected receipt is preserved. The registered primary is long-group t,
   with bootstrap sensitivity only. Calibration is a finite diagnostic, not a
   distribution-free validity or profitability proof. Small-effect power is shown.

Pre-score tests also caught Windows SQLite handle leaks in the new helper/test
fixtures; connections now close explicitly. A packet-summary syntax error was
caught before scoring. These were implementation defects corrected before the
freeze, not post-result strategy adjustments.

The historical OI reader now respects genuine NIFTY zero values and only covered
prior dates enter its threshold history. That can change raw-EN83 events. Round8
shows its own explicit EN83 control and retains the published round7 figures as
their separate frozen experiment. Never attribute an input-contract change to
new strategy alpha. Warmup abstentions and partial source coverage are recorded.

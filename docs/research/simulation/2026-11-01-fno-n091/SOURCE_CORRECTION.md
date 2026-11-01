# Terminal snapshot identity correction

The independent audit after the original60 replays found that fresh independent
annual terminal states were written as `states/<book-digest>.json`. The same
book digest is intentionally shared across years. Later fresh years therefore
overwrote earlier terminal snapshots. Original per-trade economics and complete
per-admission cash/floor receipts remain; continuous book digests include carried
history, so those snapshots are distinct and intact.

This is a research artifact defect found after scores, not a new trading idea.
Preserve original freeze.json, all original evals and the failed audit evidence.
New full-window keys include dates. The carry-only digest alias remains for
existing state_from lookups; unrelated annual snapshots no longer write it.
The actual planner, entry wrapper, risk rule, candidate construction and books
have identical ASTs; no thresholds, fees, trading gates or acceptance changed.

SOURCE_CORRECTION.json binds the old source, original24 affected eval/receipt
hashes, untouched trading ASTs and corrected source. freeze-v2.json is explicitly
a POST-SCORE artifact correction, not a retroactive pre-score freeze. The original
pre-score source4245670 and original60 results remain the experiment record.

Run24 affected fresh candidate annuals in a NEW repair-evals namespace, installed
at module level so Windows workers cannot read the original cached results.
Require complete economic trade equality AND exact original decision/admission
receipt equality, then independently reconcile date-scoped terminal snapshots.
Full continuous16 replays retain their original identity; their state is audited
against all earlier closes and actual carried floor/high-water evidence.

The new test runs two independent windows through the actual state writer and
requires both terminal cash snapshots to survive. No market result is used to
choose or modify the rule. Total execution becomes60 declared plus24 mechanical
parity reruns. Counts must not describe84 independent experiments/hypotheses.

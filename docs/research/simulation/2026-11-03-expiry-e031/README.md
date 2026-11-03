# E03.1 research record — November 3, 2026

Plain report: [EXPIRY_RESEARCH_E031.md](../../../EXPIRY_RESEARCH_E031.md).
Owner authorizes autonomous iterations beyond E03, including failed ideas and
learning. Starting Dev 0a6d46e; committed finalist freeze **0c7f414** precedes
execution stress. No 2023 access, acquisition, live orders or Production edits.

## Evidence map and interpretation

- `PLAN.md`, `IMPLEMENTATION_PLAN.md`: contracts, acceptance and rollback.
- `initial-freeze.json`: inherited code, data SHA-256 and Production identity;
  owner original bytes and local data stay ignored in `_local`.
- `baseline-configuration.json`, `baseline.json`: exact original E03 reproduction,
  all 99 independent-year position/event histories (including severe fills),
  plus after-the-fact loss diagnostics. Later maxima are diagnostic ONLY.
- `sweep-configuration.json`, `sweep.json`: 55 mechanism changes, all scores.
- `genome-configuration.json`, `genome-trials.jsonl`, `genome.json`: two seeds,
  maximum 400 new combinations permitted, **149 actually scored**. Repeated or
  neutral genomes are not counted as new discoveries. No continued search after
  the finalist freeze. There are 204 candidate evaluations plus baseline, not
  204 independent pieces of evidence.
- `finalists-freeze.json`: DEFENSIVE and FOLLOW, frozen before additional stress.
- `robustness.json`: independent years AND continuous-cash books, latency,
  warmup, coarse neighbours, block-resampled increments and selection decay.
  FOLLOW's apparently larger reset-year gain fails continuous cash and is rejected.
- `friction-audit-v2.json`: corrected stronger 1%-plus-tick fixed-trade sensitivity;
  earlier max(1%,tick) output remains untouched and is labelled in the plain report.
- `native-parity.json`: network-blocked native exit/fee parity, 391 position
  replays/407 sale slices, no mismatches. Cash, fees, lot/volume capacity,
  reserves, causal execution clocks, and complete-bar marked NAV audited.
- `daily-results.csv`: 105 expiry dates for each of three arms and fill scenarios;
  `trades.csv`: native-audited E03/E03.1 ordinary/adverse/severe tickets.
- `engine-tests.json`, `_local/full-engine-suite.log`: actual full-suite status;
  focused E02/E03/E03.1/research suite 43 passed before full collection.
- `recorded-proxy-freeze.json`, `recorded-proxy.json`: the five already-seen
  2026 quote archives, one +93.54/+64.32 model ticket for both versions.
  Inherited sampled-bar/depth-as-volume approximation, not new forward tickets.

## Reproduction (from Dev root, use the existing venv)

Outputs are immutable: commands refuse to replace an existing result. Use a new
study directory to rerun scoring; do not delete historical failures or re-freeze
the inherited baseline. Existing `baseline.json`/`robustness.json` can be audited
without re-selecting rules. No credentials or runtime scheduler are needed.

```text
python-engine/winvenv/Scripts/python.exe docs/research/simulation/2026-11-03-expiry-e031/study.py baseline
python-engine/winvenv/Scripts/python.exe docs/research/simulation/2026-11-03-expiry-e031/study.py sweep
python-engine/winvenv/Scripts/python.exe docs/research/simulation/2026-11-03-expiry-e031/study.py genome
python-engine/winvenv/Scripts/python.exe docs/research/simulation/2026-11-03-expiry-e031/lock_finalists.py
# finalist commit 0c7f414, then (no further tuning):
python-engine/winvenv/Scripts/python.exe docs/research/simulation/2026-11-03-expiry-e031/robustness.py
python-engine/winvenv/Scripts/python.exe docs/research/simulation/2026-11-03-expiry-e031/friction_audit.py
python-engine/winvenv/Scripts/python.exe docs/research/simulation/2026-11-03-expiry-e031/native_parity.py
python-engine/winvenv/Scripts/python.exe docs/research/simulation/2026-11-03-expiry-e031/recorded_proxy.py
python-engine/winvenv/Scripts/python.exe -m pytest python-engine/tests/test_expiry_e02.py python-engine/tests/test_expiry_e03.py python-engine/tests/test_expiry_e031.py docs/research/simulation/2026-11-03-expiry-e031/test_lab.py -q
python-engine/winvenv/Scripts/python.exe docs/research/simulation/2026-11-03-expiry-e031/run_engine_tests.py
python scripts/build_system_code_atlas.py
```

Research-only classification: BOTH YEARS SEEN. Results normalize current lot65
and current native fees, use next-bar OHLC proxies and a bar-volume capacity cap.
They are neither broker executions nor a whole-system portfolio result. The
generic receipts must remain PARTIAL/BAR_LIFECYCLE/SHADOW. Unassessed calendar
dates are unavailable, not fabricated non-expiry or zero-profit results.

## Remaining work / promotion boundary

E03.1 is a SMALL defensive paper hypothesis, not a large profit breakthrough.
Severe execution loses and the increment is sensitive to entry timing. No
claim that floors guarantee money, or that fitted/bootstrap profits qualify it.
Keep E02/E03/C/N11 unchanged. NIFTY 2023 remains protected. Existing 2026 and
SENSEX evidence cannot support this full-chain selection; no API/quota expansion.
No `.env` or existing schema migration; new E031 paper DB only on future enable.
Rollback flag-off still closes saved exposure. New paired forward tickets and
execution evidence precede a separately authorized GitHub promotion decision.

Source implementation **65cccb7**, pushed/remote verified. Paper flag remains false, Production unchanged. Stock helper `evidence/REPORT.md` verifies four partial shadow modules. Use `verify_evidence.py` for pinned source verification after later doc commits; it does not alter the original guard/request/report. Push/verification packet: `completion-receipt.json`.

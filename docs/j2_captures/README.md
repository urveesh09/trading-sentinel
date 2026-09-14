# `docs/j2_captures/` — CAS-window broker-behaviour evidence

This directory is the **receipt** for the J.3 broker-behaviour
verification slice. Each entry is a captured JSON document emitted
by `tools/j2_cas_probe.py` against a real Kite session in staging,
plus a per-day summary of the review verdict.

## Layout

```
docs/j2_captures/
├── README.md                        -- this file
├── YYYY-MM-DD/
│   ├── RELIANCE_15_10.json          -- pre-CAS reference capture
│   ├── RELIANCE_15_17.json          -- 15:15-15:19 reference window
│   ├── RELIANCE_15_22.json          -- 15:20-15:24 order entry
│   ├── RELIANCE_15_27.json          -- 15:25-15:29 limit entry only
│   ├── RELIANCE_15_32.json          -- 15:30-15:34 matching
│   ├── RELIANCE_15_42.json          -- 15:35-15:59 CAS post
│   ├── HDFCBANK_15_17.json          -- (optional second underlying)
│   └── ...
├── review_log.md                    -- per-day verdict of j2_capture_review
└── SUMMARY.md                        -- overall J.3.x sign-off
```

## Manifest (operator records per capture)

For each `REL1ANCE_15_17.json`:

- **Probe invocation**: command line (with `--symbols`, `--observation-at`,
  `--eligibility-list` if used, `--require-eligible` if used, `--output`).
- **Kite session id / token age**: (operator-supplied; not stored in
  the JSON to avoid leaking credentials).
- **Wall-clock drift** between IST and the host's idea of UTC at
  probe time.
- **Review verdict**: exit code of `j2_capture_review.py` plus the
  JSON report.

## Review pass criteria

Per the J.3 runbook (`docs/2026-09-13-j3-capture-protocol.md`):

- `j2_capture_review.py <file>` exits 0.
- Six checks pass:
  schema, eligibility, classifier_phase, quote_present,
  circuit_limits, broker_extras.
- Cross-window OHLC-continuity:
  `j2_capture_review.py <15_17.json> --compare-with <15_10.json>`
  exits 0.

## What J.3 ships vs what arrives later

J.3 (this commit) ships the **scaffolding**:

- `tools/j2_capture_review.py` (the review instrument).
- `docs/2026-09-13-j3-capture-protocol.md` (the operator procedure).
- This `docs/j2_captures/README.md` (the receipt directory).

J.3.x (when the operator supplies captures) lands:

- The capture JSONs themselves under `docs/j2_captures/YYYY-MM-DD/`.
- `docs/j2_captures/review_log.md` (per-day review verdicts).
- `docs/j2_captures/SUMMARY.md` (overall J.3 sign-off or defect
  list).
- A new review post-commit that updates `docs/NEXT_AGENT_PLAN.md`
  J row IMPLEMENTING → TESTED_DEV (or returns to IMPLEMENTING with
  the captured defect).

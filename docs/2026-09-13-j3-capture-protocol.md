# J.3 — CAS-window broker-behaviour capture protocol (operator procedure)

## Purpose

J.2.2 shipped the **probe instrument** (`tools/j2_cas_probe.py`). J.3
makes the probe *run* — in staging, against a live Kite session, at
six operator-selected IST moments — and signs the result off via the
**review instrument** (`tools/j2_capture_review.py`).

The captures themselves are **operator-supplied artifacts**. Dev has
no live broker; only the scaffolding lands in this slice. Once the
operator runs the protocol and commits the capture JSON files, J.3.x
signs them off and the J series reaches its `TESTED_DEV` ceiling.

The probe is opt-in. The review is mandatory. Captures are reviewed
AND signed before they're ever cited.

## Goal

Capture and preserve, for at least one Phase 1 underlying
(RELIANCE is the J.3 default; the operator may capture more), at
six IST instants, the broker response that proves CAS-window field
shape. The capture must include:

1. A timestamp inside (or around) the CAS window: 15:10 (pre-CAS
   reference), 15:17 (reference window), 15:22 (order entry), 15:27
   (limit-only), 15:32 (matching), 15:42 (CAS post / derivatives close).
2. The instrument token Kite serves for that underlying at that moment.
3. The `last_price`, `ohlc`, `volume`, and `depth` fields as returned
   by Kite.
4. **Any extra / CAS-specific fields** the Kite feed appends during
   the CAS window (surfaced under `broker_extra_fields`).
5. The classifier's verdict for (symbol, observation_at) — proves the
   Python side agrees with operator expectations.
6. The CAS-eligibility verdict for the symbol — proves J.2.1's
   eligibility list is populated correctly.

## Prerequisites

- A staging environment with:
  - `KITE_API_KEY`, `KITE_API_SECRET`, fresh `KITE_ACCESS_TOKEN`.
  - The repo's `python-engine` checked out at the J.3 commit.
  - `CAS_PHASE1_FNO_UNDERLYINGS` set to at least one Phase 1
    underlying, e.g. `CAS_PHASE1_FNO_UNDERLYINGS="RELIANCE"`.
- An IST-aware clock. The probe accepts both `+05:30` and `Z`
  timestamps; naive timestamps are now an error (J.3.1 hardening).
- `python-engine/tools/j2_cas_probe.py` AND
  `python-engine/tools/j2_capture_review.py` available on PYTHONPATH.

## Procedure

### Step 1 — Sanity-check the wiring (Dev-friendly)

Even in Dev (no live Kite) the probe runs in `--dry-run` mode and
captures classifier + eligibility verdicts. Use this for one
end-to-end smoke test before staging:

```bash
cd python-engine
./winvenv/Scripts/python.exe tools/j2_cas_probe.py \
    --symbols "RELIANCE" \
    --observation-at "2026-09-14T15:17:00+05:30" \
    --eligibility-list "RELIANCE" \
    --dry-run \
    --validate
```

Expected JSON shape: `schema_version: 2`, `eligibility_source: "override_cli"`,
and one row with `is_cas_eligible: true` plus `classifier_phase:
"CAS_REFERENCE_PRICE_WINDOW"`.

If `is_cas_eligible` is `false` here, the probe is misconfigured —
`--eligibility-list` was empty or RELIANCE was misspelt.

The probe also supports `--require-eligible`: the exit code is 1
when no probed symbol returns True. Use this in staging to catch
the common mistake of forgetting to populate the env var.

### Step 2 — Pick the CAS-window grid

The five CAS sub-windows (IST):

| Window        | IST range     | Phase                            |
|---------------|---------------|----------------------------------|
| Pre-CAS ref.  | 15:10–15:14   | `CONTINUOUS_TRADING`             |
| Reference     | 15:15–15:19   | `CAS_REFERENCE_PRICE_WINDOW`     |
| Order entry   | 15:20–15:24   | `CAS_ORDER_ENTRY`                |
| Limit only    | 15:25–15:29   | `CAS_LIMIT_ENTRY_ONLY`           |
| Matching      | 15:30–15:34   | `CAS_MATCHING`                   |
| Post          | 15:35–15:59   | `CAS_POST`                       |

The **minimum viable capture grid** is **6 captures**: one pre-CAS
(15:10) and **all five CAS sub-windows** (15:17, 15:22, 15:27, 15:32,
15:42). Capturing more symbols (HDFCBANK, INFY) is welcome but not
required for the J.3 sign-off.

The OHLC-continuity check (cross-window) requires a pre-CAS capture
AND a CAS-window capture of the same symbol on the same trading day.
A live session produces close-to-close continuity per NSE/CMTR/72394.

### Step 3 — Run the probe in staging (broker live)

```bash
cd python-engine
mkdir -p /data/research/cas_captures/$(date +%Y-%m-%d)

# 15:10 pre-CAS
./winvenv/Scripts/python.exe tools/j2_cas_probe.py \
    --symbols "RELIANCE" \
    --observation-at "2026-09-14T15:10:00+05:30" \
    --require-eligible \
    --output /data/research/cas_captures/$(date +%Y-%m-%d)/RELIANCE_15_10.json

# 15:17 reference window
./winvenv/Scripts/python.exe tools/j2_cas_probe.py \
    --symbols "RELIANCE" \
    --observation-at "2026-09-14T15:17:00+05:30" \
    --require-eligible \
    --output /data/research/cas_captures/$(date +%Y-%m-%d)/RELIANCE_15_17.json

# ... and one per sub-window.
```

Notes for the operator:

- `--eligibility-list` is OPTIONAL here; the staging env's
  `CAS_PHASE1_FNO_UNDERLYINGS` env var is the source of truth. The
  flag is for Dev or non-staging sandbox reproductions only.
- `--require-eligible` ensures the staging mistake "I forgot to set
  the env var" is loud rather than silent. Without the flag, captures
  with `is_cas_eligible=False` are emitted but invalid.
- The output directory MUST exist. The probe refuses to create
  parent dirs (defensive — staging dir management is the operator's
  job).
- One invocation per IST moment is preferred over `--observation-at`
  with multiple values. The probe supports one observation per call,
  which matches the per-moment Kite quote semantics.

### Step 4 — Review each capture

Run the review tool against every capture before committing:

```bash
./winvenv/Scripts/python.exe tools/j2_capture_review.py \
    /data/research/cas_captures/$(date +%Y-%m-%d)/RELIANCE_15_17.json \
    --expected-eligibility "RELIANCE"
```

The tool exits 0 only when every check passes. For the cross-window
OHLC-continuity check (verifying that `ohlc.close` at 15:10 IST
equals `ohlc.close` at 15:17 IST, per the CAS reference-price VWAP
semantic):

```bash
./winvenv/Scripts/python.exe tools/j2_capture_review.py \
    /data/research/cas_captures/$(date +%Y-%m-%d)/RELIANCE_15_17.json \
    --expected-eligibility "RELIANCE" \
    --compare-with /data/research/cas_captures/$(date +%Y-%m-%d)/RELIANCE_15_10.json
```

Six-point checklist (the tool runs all six):

1. **Schema**: `schema_version: 2`, every row's `classifier_phase`
   in the documented enum.
2. **Eligibility**: every row's `is_cas_eligible` matches the
   operator-declared list (here: `RELIANCE`).
3. **Classifier phase**: recomputed from
   `(observation_at_utc, symbol, cas_eligible)` matches the row's
   classifier phase.
4. **Quote present**: live capture (not dry-run) carries a non-null
   `quote` object per row.
5. **Circuit limits**: `quote.upper_circuit_limit` AND
   `quote.lower_circuit_limit` are both present and non-zero (the
   ±3 % CAS band).
6. **Broker extras**: every CAS-window row's `quote` carries at
   least one entry under `broker_extra_fields` (CAS-window-specific
   keys from Kite).

### Step 5 — Commit the captures and the sign-off

Once every capture passes review:

1. Copy each capture under `docs/j2_captures/` with a date-stamped
   filename and a tag for the trading day.
2. Add `docs/j2_captures/README.md` listing every capture, its IST
   moment, and the review verdict.
3. Run the J.3.x sign-off slice (post-J.3 plan slice, deferred):
   write `docs/2026-09-13-j3-broker-behaviour-verified.md` with
   the per-capture summary and the overall verdict.
4. Update `docs/NEXT_AGENT_PLAN.md` J row:
   `IMPLEMENTING → TESTED_DEV` (or back to IMPLEMENTING with the
   defect noted if any capture fails).

## Failure handling

If any capture fails the review:

1. **Do NOT alter the classifier or any J code.** The probe and
   review are the diagnostic; if a capture fails, the broker is
   misbehaving OR the operator's setup is wrong.
2. Surface the failure in the J.3 sign-off doc as a known-issue
   line.
3. Re-run that capture at the next trading day. Do NOT edit it
   silently. Do NOT re-run with a different symbol (it masks the
   bug).
4. If two consecutive trading days fail on the same IST moment,
   open an issue referencing the F/G correction plan format and
   link the failed captures. J.3 stays at `IMPLEMENTING` until the
   broker-behaviour question is resolved.

## Honest scope

This doc is the **J.3 capture protocol**. It does not authorise any
CAS-aware trading behaviour. The captures themselves are evidence
the classifier agrees with the broker; **acceptance of the captures
is the next slice (J.3.x sign-off)**, not this one.

If a future slice (J.4, J.9) changes the classifier OR the probe,
this protocol is invalidated for the prior captures; the captures
must be re-run from scratch.

## References

- `python-engine/tools/j2_cas_probe.py` — the probe implementation.
- `python-engine/tools/j2_capture_review.py` — the review tool.
- `python-engine/tests/test_j3_probe_quality.py` — 38 unit tests for
  the probe (Dev-safe).
- `python-engine/tests/test_j3_capture_review.py` — 17 unit tests for
  the review tool (Dev-safe).
- `python-engine/market_calendar.py::classify_session_phase` — the
  classifier under capture (now accepts `cas_eligible=` kwarg).
- `docs/2026-09-13-j2-broker-behaviour-probe.md` — the prior J.2
  runbook. J.3 supersedes the "what to capture" guidance; the
  roll-call and exit-code semantics still apply.
- `docs/2026-09-13-workflow-j-deep-research.md` — verified NSE/BSE
  facts.

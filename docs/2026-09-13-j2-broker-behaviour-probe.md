# J.2 — CAS-window broker-behaviour probe (operator procedure)

## Purpose

The CAS-aware session classifier (J.1) labels a CAS-eligible
underlying's 15:15-15:35 window as a distinct session phase
(`CAS_REFERENCE_PRICE_WINDOW` / `CAS_ORDER_ENTRY` /
`CAS_LIMIT_ENTRY_ONLY` / `CAS_MATCHING` / `CAS_POST`).

Before any future slice (J.3 or any CAS-aware strategy) can trust the
broker-side of a CAS transaction, the operator must verify **what the
live Kite feed returns during that window**. This doc is the
step-by-step procedure.

**This probe CANNOT run in Dev** — Dev has no live Kite token, no
broker, and intentionally no I/O coupling to the broker. Run it in
**staging** (or any environment with a freshly-authenticated Kite
session) only.

**This probe is NOT exercised by automated tests.** It is a
documentation-only artefact in Dev — see
`python-engine/tools/j2_cas_probe.py` for the implementation. Tests
do not import it; CI does not run it. The "test" is the operator's
manual review of the captured JSON.

## Goal

Capture and preserve, for at least one CAS-eligible underlying, a
broker response that proves CAS-window field shape. The capture must
include:

1. A timestamp inside the CAS window (15:15-15:35 IST).
2. The instrument token Kite serves for that underlying at that
   moment.
3. The `last_price`, `ohlc`, `volume`, and `depth` fields as returned
   by Kite.
4. **Any extra / CAS-specific fields** the Kite feed appends during
   the CAS window.
5. The classifier's verdict for (symbol, observation_at) — proves the
   Python side agrees with operator expectations.
6. The CAS-eligibility verdict for the symbol — proves the J.2.1 list
   is populated correctly.

## Prerequisites (operator)

- A staging environment with:
  - `KITE_API_KEY` and `KITE_API_SECRET` set.
  - A fresh `KITE_ACCESS_TOKEN` (re-authenticated the morning of the
    probe).
  - `CAS_PHASE1_FNO_UNDERLYINGS` set to at least one Phase 1
    underlying, e.g. `CAS_PHASE1_FNO_UNDERLYINGS="RELIANCE"`.
- An operator-readable `/data/research/` directory (the named Docker
  volume). The probe writes JSON evidence there.
- An IST-aware clock. The probe accepts both `+05:30` and `Z`
  timestamps; naive timestamps default to IST.

## Procedure

### Step 1 — Sanity-check the wiring (Dev-friendly)

Even in Dev (no live Kite) the probe runs in `--dry-run` mode and
captures classifier + eligibility verdicts:

```bash
cd /c/Users/Urveesh/Desktop/trading-sentinel/python-engine
./winvenv/Scripts/python.exe tools/j2_cas_probe.py \
    --symbols "RELIANCE" \
    --observation-at "2026-09-14T15:17:00+05:30" \
    --dry-run
```

Expected JSON (abbreviated):

```json
{
  "rows": [
    {
      "symbol": "RELIANCE",
      "classifier_phase": "CAS_REFERENCE_PRICE_WINDOW",
      "is_cas_eligible": true,
      "quote": null
    }
  ],
  "dry_run": true
}
```

If `is_cas_eligible` is `false`, the operator's `.env` is missing
`CAS_PHASE1_FNO_UNDERLYINGS` or the probe is running with an empty
default. Stop and fix the config before proceeding.

### Step 2 — Pick a CAS-window timestamp

The five CAS sub-windows (IST):

| Window        | IST range     | Phase                            |
|---------------|---------------|----------------------------------|
| Reference     | 15:15–15:19   | `CAS_REFERENCE_PRICE_WINDOW`     |
| Order entry   | 15:20–15:24   | `CAS_ORDER_ENTRY`                |
| Limit only    | 15:25–15:29   | `CAS_LIMIT_ENTRY_ONLY`           |
| Matching      | 15:30–15:34   | `CAS_MATCHING`                   |
| Post          | 15:35–15:59   | `CAS_POST`                       |

Pick at least **two** of these (matching + order entry is a useful
combination) for the same instrument. Different sub-windows may
carry different broker response shapes — capture both.

Also probe one **pre-CAS** timestamp (e.g. 15:10 IST) so the
operator can see the field-shape delta across the 15:15 transition.

### Step 3 — Run the probe (staging, broker live)

```bash
./winvenv/Scripts/python.exe tools/j2_cas_probe.py \
    --symbols "RELIANCE" \
    --observation-at "2026-09-14T15:17:00+05:30" \
    --output /data/research/cas_probe_RELIANCE_15_17.json

./winvenv/Scripts/python.exe tools/j2_cas_probe.py \
    --symbols "RELIANCE" \
    --observation-at "2026-09-14T15:32:00+05:30" \
    --output /data/research/cas_probe_RELIANCE_15_32.json

./winvenv/Scripts/python.exe tools/j2_cas_probe.py \
    --symbols "RELIANCE" \
    --observation-at "2026-09-14T15:10:00+05:30" \
    --output /data/research/cas_probe_RELIANCE_15_10_pre_cas.json
```

`--output` accepts an absolute path. The parent directory must exist.
Without `--dry-run` the probe calls the live broker via the existing
`kite_client.get_quote()` wrapper (the same code path the engine uses
intraday).

### Step 4 — Review the JSON evidence

For each captured file, verify the following checks. They are the
"pass conditions" for J.2 Part 2.

1. **`is_cas_eligible: true` for every probed symbol.** If any
   symbol returns `false`, the eligibility list is wrong for that
   underlying. Operator must reconcile against the NSE contract
   master before any CAS-aware strategy is enabled.
2. **`classifier_phase` matches the IST window.** E.g. for
   `--observation-at "2026-09-14T15:17:00+05:30"`, expect
   `CAS_REFERENCE_PRICE_WINDOW`. For `15:32:00`, expect
   `CAS_MATCHING`. For `15:10:00`, expect `CONTINUOUS_TRADING`.
3. **`quote` is not null.** If `quote` is null with `dry_run: false`,
   the broker call failed. The probe captures the error in
   `quote_error`; surface this to the operator for triage.
4. **`quote.upper_circuit_limit` and `quote.lower_circuit_limit` are
   present and non-zero.** These are the ±3 % CAS bands for
   CAS-eligible underlyings. A missing or zero value is a regression
   signal — the broker may have stripped CAS-specific fields for
   that sub-window.
5. **`ohlc.close` matches the pre-CAS close at 15:14:59 IST.** The
   CAS reference price (per NSE/CMTR/72394) uses trades from 15:00-
   15:15; a quote during `CAS_REFERENCE_PRICE_WINDOW` should reflect
   that VWAP in the `last_price`/`close` fields.
6. **`broker_extra_fields` is non-empty.** Kite typically attaches
   additional keys during the CAS window (e.g. `auction_status`,
   `cas_state`, `call_auction_lower`, `call_auction_upper`, etc.).
   The probe surfaces them verbatim so the operator can decide which
   to consume in J.3.

### Step 5 — What to do with the evidence

The captured JSON is the receipt the J workstream consumes in the
next slice (J.3, or an equivalent CAS-aware-strategy decision). The
operator's checklist before any J.3 implementation:

- [ ] At least one pre-CAS (15:10-15:14) and one CAS-window
      (15:15-15:35) capture per Phase 1 underlying.
- [ ] All `is_cas_eligible` checks return `true`.
- [ ] All `classifier_phase` checks match the IST window.
- [ ] No capture has `quote_error` set.
- [ ] No capture has zero / missing circuit limits.

If any check fails:

1. Do NOT enable CAS-aware strategies. The classifier is the seam,
   not the strategy.
2. Open an issue (or cross-link to the F/G correction plan doc)
   with the failing capture attached.
3. Reproduce the failing capture at the same IST moment on a
   trading day to rule out a transient Kite outage.

## Negative / restart / timing tests are NOT applicable

The probe is a manual, broker-dependent evidence-collection tool. The
following categories from the standard plan-slice template do not
apply:

- **Negative tests** — there is no "expected failure" state. A
  broker call that returns a CAS-window quote is good. A call that
  returns a non-CAS quote at the IST 15:20 boundary IS bad.
- **Restart tests** — the probe is invoked on demand. Restart
  semantics belong to the engine, not the probe.
- **Timing tests** — CAS-window probes are slow by definition
  (broker latency + parsing). Tight timing assertions are not the
  point.

## Honest scope

This doc is **the J.2 Part 2 deliverable**. It is intentionally not a
strategy; it is a procedure. The probe exercises the broker,
captures the response, and surfaces the evidence. The classifier
(J.1) and the eligibility list (J.2.1) are unchanged by this slice.

**J.2 does NOT authorise any CAS-aware trading behaviour.** The
broker-behaviour verification captured here is the precondition for
J.3 (or any future slice) to safely depend on the classifier.

## References

- `python-engine/tools/j2_cas_probe.py` — the probe implementation.
- `python-engine/market_calendar.py::classify_session_phase` — the
  classifier under verification.
- `python-engine/market_calendar.py::is_cas_eligible` — the eligibility
  gate (consumes `CAS_PHASE1_FNO_UNDERLYINGS` from `config.py`).
- `python-engine/config.py::CAS_PHASE1_FNO_UNDERLYINGS` — the env-var
  surface for the operator.
- `docs/2026-09-13-workflow-j-deep-research.md` — verified NSE/BSE
  facts and hard-coded clocks inventory.
- `docs/2026-09-13-j2-next-session-prompt.md` — J.2 scope and rules.
- `docs/2026-09-13-inheritance-j2-handoff.md` — the prior-session
  handoff binder.

# Workflow C.F2 — Kite LTP fanout observability (F-2 from prod audit)

## Source

Per the 2026-09-15 production deep audit (F-2):
> 🟡 F-2 (MED, infra): Kite LTP fanout has stopped: 0 `ltp_raw_response` events today (vs. 57-179 in prior audits). The endpoint `/api/orders/ltp` was hit 31 times today but no fanout events. **Momentum/Penny/FNO scanners depend on this fanout for quotes** — if it's truly zero, the scanners would be using stale prices. **Investigate**: the ltp_raw_response is logged by the gateway when kite.quote() succeeds. 0 events = Kite LTP endpoint is failing silently OR the gateway log writer stopped.

The audit identified two possible failure modes:
1. Kite LTP endpoint failing silently.
2. Gateway log writer stopped.

Neither could be disambiguated from audit data. The bounded fix: **add explicit entry logs and pre-call rejection logs** so a future audit can attribute the missing `ltp_raw_response` events to one of three known paths:
- `ltp_call_started` (entry, fires on EVERY call)
- `ltp_call_skipped_token_invalid` (pre-call rejection, fires when token is invalid)
- `ltp_raw_response` (post-success, fires after Kite returns 200) — pre-existing

## What landed

| File | Type | Purpose |
|---|---|---|
| `node-gateway/server/services/kite.js` | source (extended) | New `ltp_call_started` entry log + `ltp_call_skipped_token_invalid` pre-call rejection log |
| `node-gateway/server/tests/unit/kite.test.js` | test (extended) | 3 new tests pinning the new observability contract |
| `docs/2026-09-15-workflow-c-f2-ltp-fanout-observability-done.md` | doc (new) | This file |

## The shift in defensive posture

Before this slice, the gateway's `getLTP` had this observable behavior:
- `ltp_raw_response` logged ONLY after `axios.get` succeeded with a Kite 200 response.
- `ltp_retry` / `ltp_all_retries_failed` logged on retryable failures.
- **The token-invalid early-throw (line 152) logged NOTHING.**

So if the token was invalid for the entire trading day, the audit would see:
- 31 calls to `/api/orders/ltp` (because the python-engine kept retrying every 5 minutes).
- 0 `ltp_raw_response` events (because the token was invalid).
- 0 `ltp_retry` / `ltp_all_retries_failed` events (because the early-throw happens BEFORE `axios.get`).

The audit couldn't distinguish "Kite is broken" from "token is broken" from "log writer is broken". All three produced the same symptom.

After this slice, the audit can:
- Count `ltp_call_started` events = number of times the gateway entered `getLTP`.
- Count `ltp_call_skipped_token_invalid` events = number of times the gateway rejected the call due to token.
- Count `ltp_raw_response` events = number of successful Kite responses.

The delta between these three counts is a precise diagnostic:
- `started - skipped - raw_response` = number of Kite failures (the `ltp_retry` / `ltp_all_retries_failed` events).

## Key design choices

- **Same logger discipline as existing `ltp_retry` / `ltp_all_retries_failed`** — pino JSON lines with `event_type` field, easy to grep and aggregate.
- **`ltp_call_started` carries `instruments` and `instrumentCount`** so the audit can attribute per-call (e.g. "scanner X made 31 calls for instruments [NSE:AAA, NSE:BBB]").
- **`ltp_call_skipped_token_invalid` is an ERROR level** (not warn) because it indicates a real auth failure, not a transient retry.
- **No new dependencies.** Uses existing pino logger.
- **Mirrors the existing `getQuote` / `getOrderHistory` patterns** (token-invalid is the same early-throw across all methods).

## Test discipline

- New `jest.mock('../../middleware/logger', ...)` setup follows the integration-test pattern (see `tests/integration/approved-snapshot.test.js:124`).
- 3 new tests pin the new observability contract:
  1. `ltp_call_started` fires on every entry.
  2. `ltp_call_skipped_token_invalid` fires when token is invalid.
  3. The two events fire in correct order (`started` before `skipped`).

## Defensive regression

| Test file | Tests | Δ |
|---|---|---|
| `node-gateway/server/tests/unit/kite.test.js` | 24 | +3 |
| Full Node-gateway surface (excluding pre-existing flake in `db.test.js`) | 402 | 0 (kite test was 21, now 24) |

The pre-existing `db.test.js` flake (12/12 fail even without my changes) is unrelated to F-2.

## What this does NOT solve

- The actual Kite LTP failure mode is upstream — Zerodha's API or the token lifecycle. This slice gives operators the observability to ATTRIBUTE the failure to one of three paths.
- Subsequent audits will be able to say "0 raw_response but 31 skipped_token_invalid → token is the problem" or "0 raw_response and 0 skipped and 31 started → Kite is the problem".
- The actual token-recovery or Kite-recovery work is operator-owned (I.4.G-style).

## What's still open on the audit

- **F-4** (penny stale warning flood) — DONE in `0ba14a9` (C.B.3).
- **F-7** (agent dedup file observability) — DONE in `04aa166` (C.B.2).
- **F-3** (concurrent finalize_prior_days race) — DONE in `7cf87c3` (C.B.1).
- **F-1** (dashboard bootstrap race) — DONE in `f186a22` + `5265c73`.
- **F-2** (Kite LTP fanout) — DONE in this slice (`<next-commit>`).
- **F-5** (features invisible) — OPEN, next slice.
- **F-8** (GRAVISSHO not booked) — OPEN, next slice.

## Critical invariants preserved

- No change to the actual `getLTP` semantics — same retries, same error handling.
- No change to the existing `ltp_raw_response`, `ltp_retry`, `ltp_all_retries_failed` events.
- All 21 pre-existing kite tests pass.

## Operator runbook

After deploy to PROD:
- A future audit can identify whether the missing LTP events were caused by token issues, Kite issues, or log writer issues by counting the new `ltp_call_started` and `ltp_call_skipped_token_invalid` events.
- The Dashboard LTP fanout panel can be extended to show the started/skipped/raw_response split (separate slice).

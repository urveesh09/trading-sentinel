# Intraday partner advisory implementation

Dev implementation of the 8 September intraday-only plan.

## Policy

NIFTY and SENSEX manual advisory cards now use only `INTRADAY` and
`partner-manual-intraday-v1`. The previous three-session horizon is rejected;
it is not relabelled as intraday evidence. New entries are bounded by the
configured 09:45–14:45 IST window, while management observation can continue
until 15:15 IST. Cards state the dated same-day management deadline and
“INTRADAY ONLY — do not carry overnight.”

## Implemented controls

- `partner_manual_advisory.py`: typed horizon/policy, dated entry and
  management deadlines, distinct quote-observed/received/validity facts,
  numeric thesis-level requirement, cost-inclusive profile limits, session
  retirement and one conditional exit reminder.
- `hedge_advisory.py`: final transport authorization rechecks profile session,
  intraday policy/deadline and the current qualification registry.
- `partner_orchestrator.py` and `config.py`: separate entry, reminder and
  management timing settings; management scheduler remains alive through the
  deadline.
- `routes_hedge.py`: effective settings reports intraday policy/profile state
  and its actual timing boundaries without secrets.

Qualification records must match the intraday policy and horizon, use a
non-future review timestamp and remain currently qualified. A qualification
is still not evidence of future profitability; its dataset reference must be
an actual operator-reviewed research artifact before a live record is made.

## Deliberate limits

No partner orders, fills, positions or realised P&L are accessed. Conditional
protection remains opt-in and cannot infer holdings. No automatic same-day
exit exists: reminders say “If you took idea X…”, and manual action remains
the partner's responsibility.

## Merge-readiness corrections

The follow-up merge-readiness review is addressed as follows:

- Invalidation checks precede the 15:10 reminder, and each event retains a
  distinct immutable deduplication identity. A previously delivered reminder
  therefore cannot hide a later invalidation.
- `run_intraday_session_lifecycle` is a minute-level scheduler task, separate
  from option-chain scanning. It can create a truthful clock-only reminder
  without a price claim and retires elapsed ideas after a missed close or
  restart, including on the next calendar day.
- Delivery rereads its injected clock after claim/service-state waits and
  again before transport intent. Entry quote/deadline and update-management
  deadline checks consequently use the live boundary time.
- Qualification now requires an operator-registered research artifact with a
  SHA-256 fingerprint; a free-form nonempty dataset label is insufficient.

The artifact registry preserves the implementation boundary, not a claim of
market edge. An operator must register a real reviewed intraday artifact for
each index/structure/policy before any matching qualification can be saved.

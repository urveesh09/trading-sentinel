# Workflow E.6 — partner advisory audit

## Source

Per Workstream E in `NEXT_AGENT_PLAN.md`:
> Improve cards around decisions a manual trader can take:
> ... Explain uncertainty and liquidity limits without
> overwhelming the message.

## Goal

A static audit tool that reads `partner_advisory_ideas`
from PROD's `cache.db` (read-only) and verifies each
advisory has a valid rendered card body. The audit catches:

  - Advisories with empty `rendered_card`.
  - Advisories whose `rendered_card` fails the renderer
    contract from E.4 (missing required pieces per the
    plan's checklist).
  - Advisories with `rendered_card` > `MAX_TELEGRAM_CHARS`.
  - Advisories with `status=DELIVERED` but no card
    (suspicious: delivery should always have a card).

This is NOT an audit-card-vs-sent-card. The PROD does not
persist the message body Telegram actually received -- only
delivery confirmations. So we audit the system's output
(rendered_card) and surface anomalies for the operator.

## What shipped

- **`scripts/audit_partner_advisories.py`** (new): CLI that
  reads PROD's `partner_advisory_ideas` and audits each row.
  Output is human-readable by default; `--json` emits
  machine-readable output for piping into the audit
  pipeline.

- **`scripts/tests/test_audit_partner_advisories.py`** (new):
  10 tests pinning the audit contract.

## Audit status taxonomy

| Status | Exit code | Meaning |
|---|---|---|
| `PASS` | 0 | Card is present, valid, and within Telegram's limit |
| `WARN` | 0 | Soft anomaly (e.g. queued card is empty string) |
| `FAIL` | 1 | Card is missing, malformed, or exceeds Telegram's limit |
| `BLOCKER` | 2 | DB file missing or table not present |

## Validation

Each row's `rendered_card` is validated against the renderer
contract from E.4 (`validate_rendered_card`). Failure
modes surfaced by the validator:

- Missing scope header.
- Missing data + valid_until line.
- Missing intraday warning.
- Missing manual action warning.
- Missing `Why now:` line.
- Missing structure header.
- Missing invalidation / management / uncertainty / evidence.
- Per-leg missing or malformed detail.
- `MARKET_SETUP` missing bounded price or max loss.
- `CONDITIONAL_PROTECTION` missing protection premium line.

## Operator usage

```bash
# Audit PROD's live database (read-only).
python scripts/audit_partner_advisories.py --db-path /data/cache.db

# JSON output for piping into the audit pipeline.
python scripts/audit_partner_advisories.py --db-path /data/cache.db --json

# Limit to recent advisories.
python scripts/audit_partner_advisories.py --db-path /data/cache.db --limit 50

# Filter by status.
python scripts/audit_partner_advisories.py --db-path /data/cache.db \
    --status DELIVERED
```

## Tests

- `scripts/tests/test_audit_partner_advisories.py`: 10/10 PASS.
- Combined scripts/ suite: 158/158 PASS.
- Agent regression: 338/338 PASS.

## Production untouched

This tool reads PROD's `cache.db` read-only via SQLite's
URI mode (`mode=ro`). No writes, no schema changes.

## What's still operator-owned

Comparing what the system generated
(`partner_advisory_ideas.rendered_card`) against what
Telegram actually received is operator-owned because the
PROD does not persist the message body Telegram received
-- only delivery confirmations. If/when the operator adds
that audit trail, E.6 can be extended to compare the two.

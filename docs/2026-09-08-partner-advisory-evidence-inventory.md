# Partner advisory evidence inventory

Date: 8 September 2026. Scope: Dev working copy only.

## Result

No preserved NIFTY or SENSEX historical intraday option-chain dataset with
contract mapping, contemporaneous bid/ask, executable depth and exit quotes
was found in the repository. Therefore no genuine execution-quality research
artifact or production qualification was created from this inventory.

This is an evidence result, not a failure hidden by a placeholder. The current
code supports registering a reviewed immutable artifact and its SHA-256 only
after such research exists.

## Inventory performed

| Area | Found | Qualification suitability |
| --- | --- | --- |
| F&O mechanics | `fno_defined_risk.py`, `fno_costs.py`, `fno_chain.py`, `fno_signal_scan.py`, `fno_backtest.py` | Useful deterministic structure/cost logic and synthetic tests; not historical executable option evidence. |
| F&O tests | `tests/test_fno_*`, `tests/test_partner_manual_advisory.py` | Software regression fixtures only; explicitly not strategy research. |
| Generic research | Proactive and penny research/replay modules; Markdown research notes | Different instruments/policies or explanatory material; cannot qualify NIFTY/SENSEX debit spreads by association. |
| Repository data | `python-engine/data/nifty500.csv`, penny-sector/universe files | No intraday NIFTY/SENSEX option-chain bid/ask/depth/contract/exit dataset found. |

## Exact evidence needed for a qualification

For each index independently, preserve a frozen chronological run containing:

1. underlying reference bars and point-in-time signal inputs;
2. option contract identity/expiry/lot mapping for the selected vertical;
3. entry and same-day exit bid/ask, depth and no-fill rules;
4. deterministic fees, slippage and manual-response delay assumptions;
5. fixed policy parameters and an untouched chronological evaluation period;
6. candidate, fill, no-fill, gross/net outcome, loss, drawdown and limitations;
7. a reproducible manifest and SHA-256 fingerprint of the preserved report.

Index-only candle movement can be used for an explicitly labelled modelled
signal study, but it cannot establish that a debit spread was executable at
the displayed price. MiniMax may assist prose interpretation but cannot
supply prices, data provenance or approval.

## Deployment implication

The non-delivering deployment candidate and fixed Telegram receipt diagnostic
can be prepared/tested independently. Automatic advice delivery must remain
explicitly disabled until genuine per-index research artifacts are reviewed,
registered and matched to `INTRADAY` / `partner-manual-intraday-v1`
qualifications.

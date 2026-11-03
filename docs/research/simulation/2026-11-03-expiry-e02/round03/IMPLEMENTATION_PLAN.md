# E02 R3 Dev paper incubator — adapter review plan

Problem: preserve a positive joint-fit hypothesis without claiming that its
failed untouched ancestor qualified. The latest 2024/2025 fitted pullback has
one-lot/ticket sizing and small sampled losses. It needs forward observations,
not another claim of historical out-of-sample success.

Files: new `python-engine/expiry_e02.py`, `tests/test_expiry_e02.py`; flag in
`config.py`; archive-observer hook in `scheduler_setup.py`; one-held-contract
addition to the existing quote batch in `expiry_paper._tick_underlying`.
Primary A/B/C and their money/exit functions stay unchanged. The held leg may
otherwise leave ATM+/-8; including it in the same batch adds at most one token,
no additional API call. Failure of its read cannot cost the primary its tick.

Contract: `EXPIRY_E02_SHADOW_ENABLED=false` by default; independent
`<DB_PATH>.expiry-e02.db`, additive `e02_state` and `e02_positions` tables. No
operational ledger or real orders, no messages, no main-rule swap. One NIFTY
lot65/ticket, at most two entries/day, original Rs2500 daily reserve, each
ticket <=Rs1250. Standalone starting cash25000, never refilled by restart/date
changes. Daily budget freezes the same realized-drawdown stance as research.
Entry limits are fixed before the next quote. Missing/stale/bad/depthless data
refuse fills; pending exits retry and survive disabling entries. Cash and peak
reconcile to closed journal rows. Fees/policy are frozen at entry. Prior-day
unresolved exposure blocks new entries instead of inventing settlement.

Archive bars use >=4 timely fresh index/future samples/minute and require12
consecutive completed bars. This is SAMPLED_10S_FORWARD, not historical exchange
minute OHLC. Recording begins12:59, so warmup can delay the first admission to
about13:11. No backfilled forward entries on late activation/restart. Paper
management uses completed bars, execution uses the latest fresh actual depth.
This basis/latency difference needs forward testing and prevents exact native
execution qualification from the historical proxy.

Acceptance: pure signal/exit parity on common historical bar inputs; native
cash/fee/position identities; no source writes or provider calls; no duplicate
entry/close on repeated ticks; late activation does not backfill; stale source
refused; flag off still manages open positions; held leg remains quoted;
wrong expiry/lot and bad cash fail closed; existing expiry/scheduler tests and
code atlas/document checks. Register all source and frozen candidate hashes.

Rollout: Dev implementation only, disabled; owner can review through GitHub.
No Production changes or deployment in this task. Before any future enable:
confirm archive basis and lot, then collect at least20 new NIFTY episodes with
positive fee/ex-best net, measured draws/losses and executable coverage. SENSEX
needs its own complete-chain research and is disabled/unqualified. The old
E01.1 multi-index qualification bar remains separate. Rollback: flag off blocks
new entries, held positions continue their exits; code revert through GitHub.
Existing evidence/records are never deleted.

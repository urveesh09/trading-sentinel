# Free-data research implementation

Date: 8 September 2026. Implemented in Dev only on `codex/production-correction-hedge-p0`; Production was not edited.

## Delivered

- `python-engine/research_archive.py` exports a consistent read-only SQLite snapshot of existing `fno_chain_oi` and `fno_fut_snap` records for NIFTY/SENSEX. It writes atomic JSONL files, schema and coverage manifests, SHA-256 checksums and explicit `OPTION_LTP_OI_SNAPSHOT` limitations. The export does not copy a live SQLite file or write to its source.
- `python-engine/fno_oi_store.py` now preserves eligible old OI rows before the existing EOD retention purge. If preservation fails, it logs a loud failure and skips deletion rather than silently destroying the only evidence. Normal operational cache retention is otherwise unchanged.
- `python-engine/fno_underlyings.py` archives each dated raw Kite NFO/BFO master, with a canonical contract catalogue. Its identity includes exchange, contract terms, expiry, lot and tick size; a reused token or changed lot becomes a distinct immutable observation.
- `python-engine/research_quote_collector.py` adds a bounded, advice-independent NIFTY/SENSEX collection job. It selects the front future plus two listed option expiries around ATM, records the actual REST full-quote response and five displayed book levels, timestamp/gap/missing/crossed-book facts, source mode and local receive ordering. REST data is explicitly labelled lower-frequency. It calls no order or partner-delivery API.
- `python-engine/scheduler_setup.py` registers `research_quote_collection` once per minute at second 25. It self-gates on market session/calendar/token availability, not partner profile, delivery or qualification gates.
- `python-engine/research_study.py` creates immutable, fingerprinted NIFTY underlying/modelled intraday reports using the existing deterministic backtest. It records the synthetic pricing assumptions and never registers or qualifies a strategy. It intentionally refuses SENSEX until a BFO-calibrated model is implemented rather than applying NIFTY strike/lot assumptions to the wrong market.
- `python-engine/market_data_sources.py` provides a source-neutral contract, explicit Kite capability report, and validated optional Breeze request fixtures. Kite historical candles/OI are deliberately not advertised as historical depth; the BFO request uses Breeze's `BSESEN` alias without confusing it with Kite symbols.
- `python-engine/partner_manual_advisory.py` pins every evaluated advisory candidate—including rejected candidates—with its exact displayed leg values and validation reasons. This is audit evidence only and does not change delivery eligibility.
- `GET /partner/advisory/research-readiness` provides an authenticated readiness view. It cannot enable delivery or qualification.

## Storage and rollout

Defaults use the existing persistent Docker volume: `RESEARCH_ARCHIVE_PATH=/data/research`. New configuration is enabled for passive collection, independently of advice delivery:

- `RESEARCH_ARCHIVE_ENABLED=true`
- `RESEARCH_QUOTE_COLLECTION_ENABLED=true`
- `RESEARCH_ARCHIVE_REQUIRED_BEFORE_FNO_PURGE=true`

The collector has no broker-order, partner-position or Telegram dependency. It needs the existing paid Kite market-data entitlement at runtime; no new data vendor is required. Its current REST fallback is not a WebSocket tick archive and must not be described as one. A supported Kite full-mode WebSocket producer can feed the same event format later.

Immediately after the GitHub deployment, run this inside the Python engine container once to preserve the current short-retention records before the normal EOD purge:

```text
python research_cli.py export-fno --source-db /data/cache.db --archive-root /data/research --underlyings NIFTY,SENSEX
```

It is a read-only SQLite export: it neither restarts the service nor changes the source database. Keep the printed archive path and manifest SHA-256 values with the rollout evidence.

Before promotion, ensure the Docker `trading_data` volume has more than the configured one-GiB operational reserve. This implementation refuses new archive writes below that reserve and never silently deletes report data to make room. Retention of finalised quote segments remains an operator-reviewed follow-up because no pinned-report index yet exists; automatic retention must not delete research inputs that may later be cited.

## Evidence status

The old cache export gives useful observed LTP/OI/volume context but no historical bid/ask or depth. Forward collection starts building quote evidence only after deployment and market operation. The modelled NIFTY report can test signal/exit assumptions now, but cannot prove fillability or profitability. SENSEX requires its own BFO-calibrated research model and is not inferred from NIFTY.

## Validation

Focused validation passed after implementation:

`61 passed` — archive/export, quote normalisation/collection, source capability/Breeze alias, purge safety, F&O instruments, partner orchestration/routes and configuration tests.

The scheduler and route characterization goldens were deliberately regenerated and reviewed for exactly one new job and one authenticated read-only route.

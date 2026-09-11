import aiosqlite
import pytest


@pytest.mark.asyncio
async def test_reconciliation_keeps_legacy_unlinked_and_proven_mismatch_visible(tmp_path):
    from fno_positions import init_fno_positions_db
    from performance import init_ledger
    from reconciliation_evidence import reconciliation_evidence_report

    db_path = str(tmp_path / "cache.db")
    await init_ledger(db_path)
    await init_fno_positions_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("INSERT INTO fno_positions(source,tradingsymbol,status,pnl) VALUES ('FNO_PAPER','NIFTYTEST','CLOSED',125.0)")
        await db.execute("INSERT INTO bankroll_ledger(timestamp,event_type,ticker,pnl,bankroll_before,bankroll_after,source,origin_ref) VALUES ('2026-09-10T10:00:00+00:00','TRADE_CLOSED','NIFTYTEST',125,0,125,'FNO_PAPER','fno_position:1')")
        await db.execute("INSERT INTO bankroll_ledger(timestamp,event_type,ticker,pnl,bankroll_before,bankroll_after,source,origin_ref) VALUES ('2026-09-10T10:01:00+00:00','TRADE_CLOSED','OLD',10,0,10,'FNO_PAPER',NULL)")
        await db.execute("INSERT INTO bankroll_ledger(timestamp,event_type,ticker,pnl,bankroll_before,bankroll_after,source,origin_ref) VALUES ('2026-09-10T10:02:00+00:00','TRADE_CLOSED','NIFTYTEST',120,0,120,'FNO_PAPER','fno_position:1')")
        await db.commit()
    report = await reconciliation_evidence_report(db_path, source="FNO_PAPER")
    by_reason = {row["reason"]: row for row in report["sheets"]}
    # A single stable origin cannot close twice.  The old matcher labelled one
    # duplicate clean merely because the copied amount happened to match.
    assert by_reason["multiple_ledger_rows_share_origin_ref"]["state"] == "UNRESOLVED"
    assert by_reason["stable_origin_ref_missing"]["state"] == "UNRESOLVED"
    assert len(report["source_sheets"]) == 5
    assert {sheet["source"] for sheet in report["source_sheets"]} == {"MOMENTUM", "EDGE_LIVE", "MOMENTUM_PAPER", "PENNY_PAPER", "EDGE_PAPER"}
    assert report["broker_reconciled"] is False

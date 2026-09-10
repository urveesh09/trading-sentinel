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
    assert by_reason["stable_origin_ref_and_pnl_match"]["state"] == "MATCHED_INTERNAL"
    assert by_reason["stable_origin_ref_missing"]["state"] == "UNRESOLVED"
    assert by_reason["origin_ref_pnl_difference"]["state"] == "UNRESOLVED"
    assert report["broker_reconciled"] is False

"""Emit only the scoped read-only Production evidence for the N012 control."""

from collections import defaultdict
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3


IDS = (55, 56, 57, 58, 59)
FIRST, LAST = "2026-11-03", "2026-11-05"
SETTINGS = (
    "FNO_PAPER_BANKROLL", "FNO_PAPER_BOOK_START", "FNO_N11_STAND_NEED", "FNO_N11_STAND_RATIO",
    "FNO_N11_LOW_TWO_LOTS_BEFORE_MIN", "FNO_N11_TOLERANCE_ENABLED", "FNO_N11_TOLERANCE_RUPEES",
    "FNO_N11_TOLERANCE_STOP_FACTOR", "FNO_MAX_RISK_PCT", "FNO_MAX_LOSS_PER_TRADE",
    "FNO_MAX_LOTS", "FNO_MAX_LOTS_PROVEN", "FNO_MAX_OPEN_PREMIUM_PCT", "FNO_STOP_PREMIUM_PCT",
    "FNO_ADAPTIVE_RISK_ENABLED", "FNO_RISK_CUT1_DRAWDOWN_PCT", "FNO_RISK_CUT2_DRAWDOWN_PCT",
    "FNO_RISK_UP1_MIN_TRADES", "FNO_RISK_UP1_MIN_PF", "FNO_RISK_UP2_MIN_TRADES", "FNO_RISK_UP2_MIN_PF",
    "FNO_RISK_NEAR_PEAK_PCT", "FNO_TWO_STRIKE_LOSSES",
)


def decision_rows(db):
    def rows(query, args):
        return [dict(row) for row in db.execute(query, args)]

    positions = rows("SELECT id,entry_time,risk_fee_reserve_rupees FROM fno_positions WHERE id BETWEEN ? AND ? "
                     "AND source='FNO_PAPER' ORDER BY id", (IDS[0], IDS[-1]))
    if tuple(row["id"] for row in positions) != IDS:
        raise ValueError("Unexpected Production ledger rows")
    positions_last = positions[-1]["entry_time"]
    return {
        "positions": positions,
        "adx": rows("SELECT session_date,adx14,threshold,side,last_bar,bars,recorded_at FROM fno_regime_gate "
                    "WHERE session_date BETWEEN ? AND ? ORDER BY session_date", (FIRST, LAST)),
        "volatility": rows("SELECT session_date,atr_pct,usual,vol_up,above_line,recorded_at FROM fno_n11_gate "
                           "WHERE session_date BETWEEN ? AND ? ORDER BY session_date", (FIRST, LAST)),
        "paper_history": rows("SELECT id,source,exit_time,net FROM fno_n11_paper WHERE status='CLOSED' "
                              "AND net IS NOT NULL AND exit_time<? ORDER BY exit_time,id", (positions_last,)),
        "second_lots": rows("SELECT position_id,reason FROM fno_n11_second_lot WHERE position_id BETWEEN ? AND ? "
                            "ORDER BY position_id", (IDS[0], IDS[-1])),
        "admissions": rows("SELECT r.position_ref,r.state AS reserve_state,r.worst_case_cash_rs,r.created_at,"
                           "r.resolved_at,d.state AS dispatch_state,d.claimed_at,d.outcome,d.tradingsymbol,"
                           "d.planned_premium_rs FROM fno_risk_reservations r JOIN fno_entry_dispatches d "
                           "ON d.reservation_key=r.reservation_key AND d.position_ref=r.position_ref "
                           "WHERE r.source='FNO_PAPER' AND r.book='SINGLE_LEG' AND r.position_ref IN (?,?,?,?,?) "
                           "ORDER BY r.position_ref", tuple(f"fno_position:{n}" for n in IDS)),
    }


def archived_oi(root):
    days = defaultdict(lambda: {"rows": 0, "positive_rows": 0, "snapshots": set()})
    manifests = {}
    unique = set()
    for manifest in sorted(root.glob("*/manifest.json")):
        raw = manifest.read_bytes()
        spec = json.loads(raw)
        coverage = spec["coverage"]["fno_chain_oi"]
        if not coverage["first_timestamp"] or coverage["first_timestamp"] >= "2026-10-29":
            continue
        data = (manifest.parent / "fno_chain_oi.jsonl").read_bytes()
        if hashlib.sha256(data).hexdigest() != spec["files"]["fno_chain_oi.jsonl"]["sha256"]:
            raise ValueError(f"Changed operational OI export: {manifest.parent.name}")
        manifests[manifest.parent.name] = hashlib.sha256(raw).hexdigest()
        for line in data.splitlines():
            row = json.loads(line)
            if row["underlying"] != "SENSEX" or row["snap_ts"] >= "2026-10-29":
                continue
            key = (row["snap_ts"], row["expiry"], row["strike"], row["opt_type"])
            if key in unique:
                continue
            unique.add(key)
            day = days[row["snap_ts"][:10]]
            day["rows"] += 1
            day["positive_rows"] += int(row["oi"] > 0)
            day["snapshots"].add(row["snap_ts"])
    return {"manifests_sha256": manifests, "dates": {day: {
        **row, "snapshots": len(row["snapshots"]), "first": min(row["snapshots"]), "last": max(row["snapshots"]),
    } for day, row in sorted(days.items())}}


def main():
    from config import settings

    with closing(sqlite3.connect("file:/data/cache.db?mode=ro", uri=True, timeout=2)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        evidence = decision_rows(db)
    evidence["settings"] = {name: getattr(settings, name) for name in SETTINGS}
    evidence["historical_oi"] = archived_oi(Path("/data/research/operational-fno"))
    print(json.dumps(evidence, sort_keys=True))


if __name__ == "__main__":
    main()

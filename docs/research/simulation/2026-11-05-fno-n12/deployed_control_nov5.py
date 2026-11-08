"""Reconcile recorded NIFTY and SENSEX paper exits and shared wallet clocks."""

import argparse
from collections import defaultdict
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace

from round25 import digest


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "python-engine"))
from fno_costs import calc_fno_costs, options_exchange_for
from fno_exit_paths import params_digest
from fno_exit_rules import evaluate_single_leg_exit
from fno_n11 import eff_clock


DAYS = ("2026-11-03", "2026-11-04", "2026-11-05")
IDS = (55, 56, 57, 58, 59)


def replay_held(row, marks):
    assert row["qty"] == row["initial_qty"] and row["lots"] == row["initial_lots"]
    entry = datetime.fromisoformat(row["entry_time"])
    position = SimpleNamespace(**row)
    position.trail_active = 0
    position.trail_stop_underlying = None
    position.best_underlying = row["entry_underlying"]
    position.best_premium = None
    exchange = options_exchange_for(row["underlying"])
    sign = 1 if row["direction"] == "LONG" else -1
    risk = abs(row["entry_underlying"] - row["stop_underlying"])
    static = marks[0]["params"]
    breach = None
    for index, mark in enumerate(marks):
        assert mark["token"] == row["token"] and mark["underlying"] == row["underlying"]
        at = datetime.fromisoformat(mark["at"])
        bid, future = mark.get("bid") or 0., mark.get("fut")
        basis = bid if bid > 0 else mark.get("ltp") or 0.
        params = dict(static)
        if row["strategy"] == "N11_EFF" and future:
            progress = sign * (future - row["entry_underlying"]) / risk if risk > 0 else 0.
            params["FNO_TIME_STOP_MIN"] = eff_clock((at - entry).total_seconds() / 60., position.trail_active,
                                                   bid, row["entry_premium"], row["qty"], row["lots"], progress,
                                                   exchange=exchange)
        assert params_digest(params) == mark["params_sha"], (row["id"], mark["at"])
        decision = evaluate_single_leg_exit(position, now_ist=at, fut_price=future, exit_px_basis=basis,
                                            hard_flat=at.hour * 60 + at.minute >= params["FNO_HARD_FLAT_MIN"],
                                            params=params, lock_breach_since=breach)
        breach = decision.lock_breach_since
        position.best_premium = decision.best_premium
        if decision.persist_trail:
            position.trail_active = decision.trail_active
            position.trail_stop_underlying = decision.trail_stop
            position.best_underlying = decision.best_underlying
        if decision.exit_reason and basis > 0:
            gross = (basis - row["entry_premium"]) * row["qty"]
            fees = calc_fno_costs(row["entry_premium"], basis, row["qty"], exchange=exchange)
            assert index == len(marks) - 1
            return at, basis, decision.exit_reason, gross - fees
    raise ValueError(f"Unresolved held path for {row['id']}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("export", type=Path)
    args = parser.parse_args()
    folder = args.export
    manifest_path = folder / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    database = folder / "fno-replay.sqlite"
    paths = [folder / "fno_exit_paths" / f"{day}.jsonl" for day in DAYS]
    for path in [database, *paths]:
        assert digest(path) == manifest["files_sha256"][path.relative_to(folder).as_posix()]
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        entries = db.execute("SELECT * FROM fno_positions WHERE source='FNO_PAPER' AND entry_date BETWEEN ? AND ? ORDER BY id",
                             (DAYS[0], DAYS[-1])).fetchall()
        assert tuple(row["id"] for row in entries) == IDS
        signals = db.execute("SELECT * FROM fno_signals WHERE accepted=1 AND leg='FNO_PAPER' AND substr(evaluated_at,1,10) "
                             "BETWEEN ? AND ?", (DAYS[0], DAYS[-1])).fetchall()
        spreads = db.execute("SELECT id,closed_at,pnl FROM fno_dr_positions WHERE source='FNO_PAPER' AND status='CLOSED' "
                             "AND substr(closed_at,1,10) BETWEEN ? AND ?", (DAYS[0], DAYS[-1])).fetchall()
    assert len(signals) == 5
    cash = [(datetime.fromisoformat(row["exit_time"]), row["pnl"]) for row in entries]
    cash.extend((datetime.fromisoformat(row["closed_at"]), row["pnl"]) for row in spreads)
    held = defaultdict(list)
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                mark = json.loads(line)
                if mark["source"] == "FNO_PAPER" and mark["position_id"] in IDS:
                    held[mark["position_id"]].append(mark)
    rows = []
    for entry in entries:
        at = datetime.fromisoformat(entry["entry_time"])
        pool = 250000. + sum(value for when, value in cash if when < at)
        signal, = [s for s in signals if s["bar_ts"] == entry["bar_ts"] and s["underlying"] == entry["underlying"]
                   and s["tradingsymbol"] == entry["tradingsymbol"]]
        assert signal["lots"] == entry["initial_lots"] and abs(signal["pool_at_eval"] - pool) < .01
        marks = sorted(held[entry["id"]], key=lambda x: datetime.fromisoformat(x["at"]))
        closed, bid, reason, net = replay_held(dict(entry), marks)
        assert (closed, bid, reason) == (datetime.fromisoformat(entry["exit_time"]), entry["exit_premium"], entry["exit_reason"])
        assert abs(net - entry["pnl"]) < .01
        rows.append({"id": entry["id"], "symbol": entry["tradingsymbol"], "underlying": entry["underlying"],
                     "lots": entry["initial_lots"], "lot_size": entry["lot_size"], "pool": round(pool, 2),
                     "entry": entry["entry_time"], "exit": closed.isoformat(), "exit_price": bid, "reason": reason,
                     "held_looks": len(marks), "net": round(net, 4),
                     "signal_log_delay_ms": round((datetime.fromisoformat(signal["evaluated_at"]) - at).total_seconds() * 1000., 3)})
    out = {"manifest_sha256": digest(manifest_path), "positions": rows,
           "singles_net": round(sum(row["net"] for row in rows), 2),
           "defined_risk_cash": [{"id": row["id"], "closed": row["closed_at"], "net": row["pnl"]} for row in spreads],
           "scope": "recorded admission and pool reconciliation with independently replayed held exits",
           "unsealed_days": [d for d in DAYS if d in manifest["unsealed_days"]]}
    output = HERE / "deployed-control-nov5.json"
    try:
        with output.open("x", encoding="utf-8") as handle:
            json.dump(out, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError:
        if json.loads(output.read_bytes()) != out:
            raise ValueError(f"Recomputed control differs from {output}")
    print(out["singles_net"], "positions", len(rows), "held looks", sum(row["held_looks"] for row in rows), flush=True)


if __name__ == "__main__":
    main()

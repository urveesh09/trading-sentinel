"""N08 diagnosis, step 1: every N07 trade on 2024-26 with what was known at its entry and how its path went.

Seen data only, and 2023 is never opened here. Run once per year; analyse with diagnose_tables.py. Writes _local/context-YEAR.json.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
YEAR = os.environ.get("N08_YEAR", "2026")
assert YEAR in ("2024", "2025", "2026"), "this diagnosis never reads 2023"
import n08_lab as N  # noqa: E402

A, Y, B, C = N.A, N.Y, N.B, N.C


def main() -> None:
    B.O27F.deny_network()
    B.L._init()
    keys = json.loads((A.HERE / "_local" / f"keys-candidate-{YEAR}.json").read_text())
    trades = json.loads((A.HERE / "_local" / "evals" / f"{keys['NORMAL|PREMIUM_STALL']}.json").read_text())["trades"]
    table = C.table("year")
    sides = N.di_sides()
    data = Y.dataset("year")
    packets = {}
    out = []
    for t in trades:
        day = t["entry_time"][:10]
        if day not in packets:
            packets[day] = data.observations(day)[0]
        row = table.get(day) or {}
        entry = datetime.fromisoformat(t["entry_time"])
        end = datetime.fromisoformat(t["exit_time"])
        risk = abs(t["entry_underlying"] - t["initial_stop_underlying"])
        sign = 1 if t["direction"] == "LONG" else -1
        rupee_r = t["initial_entry_premium"] * 0.25
        path = []
        for obs in packets[day]:
            if not entry < obs.at:
                continue
            qs = [q for q in obs.options.values() if q.contract.tradingsymbol == t["tradingsymbol"]]
            q = qs[0] if len(qs) == 1 else None
            if q is None or q.bid <= 0:
                continue
            path.append(((obs.at - entry).total_seconds() / 60, q.bid, sign * (obs.future.ltp - t["entry_underlying"]) / risk, obs.at <= end))
        held = [p for p in path if p[3]]
        rest = [p for p in path if not p[3]]
        out.append({
            "year": YEAR, "day": day, "time": t["entry_time"][11:16], "expert": t["entry_expert"], "origin": t["origin"], "direction": t["direction"],
            "lots": t["entry_qty"] // 65, "premium": t["entry_premium"], "exit": t["exit_reason"], "net": t["net_pnl"], "extra_cost": t.get("extra_cost", 0),
            "exit_time": t["exit_time"][11:16], "hold": (end - entry).total_seconds() / 60, "stretch": t.get("stretch"), "risk_points": risk,
            "adx": row.get("adx_value"), "adx_rising": row.get("adx_rising"), "gap_big": row.get("gap_big"), "gap_dir": row.get("gap_dir"),
            "dte2": row.get("dte2"), "event": row.get("event"), "don20": row.get("don20"), "di_up": sides.get(day), "weekday": entry.weekday(),
            "mfe_r": max(((p[1] / t["entry_premium"] - 1) / 0.25 for p in held), default=0.0), "mae_r": min(((p[1] / t["entry_premium"] - 1) / 0.25 for p in held), default=0.0),
            "mfe_prog": max((p[2] for p in held), default=0.0), "mae_prog": min((p[2] for p in held), default=0.0),
            "mfe_minute": max(held, key=lambda p: p[1])[0] if held else 0.0,
            "after_best_r": max(((p[1] / t["entry_premium"] - 1) / 0.25 for p in rest), default=None),
            "after_last_r": (rest[-1][1] / t["entry_premium"] - 1) / 0.25 if rest else None,
            "exit_r": (t["exit_premium"] / t["entry_premium"] - 1) / 0.25, "rupee_r": rupee_r,
            "n04_context": t.get("n07_exit_context"),
        })
    X = A.X
    X.write(N.LOCAL / f"context-{YEAR}.json", out)
    print("context", YEAR, len(out), flush=True)


if __name__ == "__main__":
    main()

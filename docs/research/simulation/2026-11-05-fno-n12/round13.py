"""Fixed-clock late-session feasibility screen, separate from the regular book."""
from collections import Counter
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess

import round1 as r
from anatomy import DATASETS, trades
from config import settings
from cost_schedules import options_cost_snapshot
from fno_costs import calc_fno_costs_from_snapshot

HERE = Path(__file__).resolve().parent
LOT = 65


def read_mark(conn, kind, expiry, at, strike=0., option=""):
    return conn.execute(
        "SELECT close, volume, oi FROM candles WHERE kind=? AND expiry=? AND strike=? AND opt=? AND datetime=?",
        (kind, expiry, strike, option, at),
    ).fetchone()


def verify():
    r.verify_freeze()
    path = HERE / "round13-freeze.json"
    config = json.loads(path.read_bytes())
    assert config == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{path.relative_to(r.ROOT).as_posix()}"], cwd=r.ROOT))
    for name, sha in config["files"].items():
        text = (HERE / name).read_text(encoding="utf-8")
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == sha, name
    assert config["costs"] == options_cost_snapshot() and config["min_oi"] == settings.FNO_MIN_OI
    return config


def evaluate(conn, manifest, config, controls):
    sessions = manifest["sessions"]
    weekly = manifest["weekly_expiry_calendar"]
    futures = manifest["future_expiries"]
    entered = {trade["entry_time"][:10] for trade in controls["trades"]
               if datetime.fromisoformat(trade["entry_time"]).strftime("%H:%M:%S") <= "14:45:59"}
    counts = Counter()
    directions = []
    positions = []
    for prev, day in zip([None, *sessions], sessions):
        if not r.WINDOW[0] <= day <= r.WINDOW[1]:
            continue
        counts["sessions"] += 1
        expiry = next((x for x in weekly if x >= day), None)
        if expiry == day:
            counts["own_expiry"] += 1
            continue
        if day in entered:
            counts["n11t_already_entered"] += 1
            continue
        if prev is None or (date.fromisoformat(day) - date.fromisoformat(prev)).days > 4:
            counts["prior_session_unavailable"] += 1
            continue
        length, low, high = conn.execute(
            "SELECT count(*), min(low), max(high) FROM candles WHERE kind='index' AND expiry='' "
            "AND strike=0 AND opt='' AND datetime BETWEEN ? AND ?",
            (f"{prev} 09:15:00", f"{prev} 15:29:00"),
        ).fetchone()
        close = read_mark(conn, "index", "", f"{prev} 15:29:00")
        morning = read_mark(conn, "index", "", f"{day} 09:44:00")
        if length != 375 or high <= low or close is None or morning is None:
            counts["prior_or_open_marks_missing"] += 1
            continue
        move = morning[0] - close[0]
        if abs(move) < .5 * (high - low):
            counts["small_opening_displacement"] += 1
            continue
        counts["signal"] += 1
        side = 1 if move > 0 else -1
        spot_in = read_mark(conn, "index", "", f"{day} 14:46:00")
        spot_out = read_mark(conn, "index", "", f"{day} 15:09:00")
        if spot_in is not None and spot_out is not None:
            directions.append(side * (spot_out[0] - spot_in[0]))
        fut_expiry = next((x for x in futures if x >= day), "")
        future = read_mark(conn, "future", fut_expiry, f"{day} 14:45:00")
        if future is None or expiry is None:
            counts["missing_front"] += 1
            continue
        strike = 50 * math.floor(future[0] / 50 + .5)
        right = "CE" if side > 0 else "PE"
        mark = read_mark(conn, "option", expiry, f"{day} 14:46:00", strike, right)
        if mark is None or mark[0] <= 0 or (mark[1] or 0) <= 0 or (mark[2] or 0) < config["min_oi"]:
            counts["missing_or_illiquid_entry"] += 1
            continue
        _, ask = r.Y.yeardata.bid_ask(mark[0])
        fees = config["costs"]
        reservation = ask * LOT + calc_fno_costs_from_snapshot(ask, 0., LOT, fees) + 400
        if reservation > 5000:
            counts["cash_limit"] += 1
            continue
        position = dict(day=day, expiry=expiry, strike=strike, right=right, ask=ask,
                        reservation=round(reservation, 2))
        exit_mark = read_mark(conn, "option", expiry, f"{day} 15:09:00", strike, right)
        if exit_mark is None or exit_mark[0] <= 0 or (exit_mark[1] or 0) <= 0:
            counts["unresolved_exit"] += 1
            positions.append(position)
            continue
        bid, _ = r.Y.yeardata.bid_ask(exit_mark[0])
        net = (bid - ask) * LOT - calc_fno_costs_from_snapshot(ask, bid, LOT, fees)
        positions.append({**position, "bid": bid, "base_net": round(net - 200, 2),
                          "adverse_net": round(net - 400, 2)})
        counts["settled"] += 1
    return {"counts": counts, "signed_index_count": len(directions),
            "signed_index_points": round(sum(directions), 4),
            "base_net": round(sum(p.get("base_net", 0) for p in positions), 2),
            "adverse_net": round(sum(p.get("adverse_net", 0) for p in positions), 2),
            "positions": positions}


def main():
    config = verify()
    dataset = DATASETS[r.YEAR]
    manifest = json.loads((dataset / "manifest.json").read_bytes())
    db = dataset / "breeze.sqlite"
    with db.open("rb") as handle:
        assert hashlib.file_digest(handle, "sha256").hexdigest() == manifest["files_sha256"][db.name]
    _, controls = trades(r.YEAR, "N11T")
    with sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True) as conn:
        result = evaluate(conn, manifest, config, controls)
    with (HERE / f"round13-{r.YEAR}.json").open("x", encoding="utf-8") as file:
        json.dump(result, file, indent=2, sort_keys=True)
        file.write("\n")
    print(r.YEAR, result["counts"], result["base_net"], result["adverse_net"], flush=True)


if __name__ == "__main__":
    main()

"""Price a fixed-clock one-lot futures substitute without assuming portfolio parity."""

from collections import defaultdict
from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from anatomy import DATASETS, trades


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
LOT = 65
WALLET = 250000.
BUFFER = 25000.
STOP_LIMIT = 2500.
MARGINS = (.10, .13, .16)
FILL_POINTS = (2., 4.)


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def costs(buy, sell):
    buy_value, sell_value = buy * LOT, sell * LOT
    turnover = buy_value + sell_value
    brokerage = min(20., .0003 * buy_value) + min(20., .0003 * sell_value)
    taxable = brokerage + (.0000183 + .000001) * turnover
    return taxable * 1.18 + .00002 * buy_value + .0005 * sell_value


def amount(entry, exit_, side, points):
    first, second = entry + side * points, exit_ - side * points
    buy, sell = (first, second) if side == 1 else (second, first)
    gross = (sell - buy) * LOT
    return gross - costs(buy, sell)


def selection(entry, stop, side, initial_qty, existing):
    if initial_qty != LOT or existing or not 0 < side * (entry - stop):
        return None, ()
    planned = -amount(entry, stop, side, FILL_POINTS[-1])
    eligible = tuple(margin for margin in MARGINS
                     if planned <= STOP_LIMIT and margin * (entry + FILL_POINTS[-1]) * LOT + BUFFER + planned <= WALLET)
    return planned, eligible


def mark(con, expiry, at):
    moment = datetime.fromisoformat(at)
    row = con.execute("SELECT close,volume FROM candles WHERE kind='future' AND expiry=? AND strike=0 AND opt='' AND datetime=?",
                      (expiry, moment.strftime("%Y-%m-%d %H:%M:00"))).fetchone()
    if row and row[0] > 0 and (row[1] or 0) > 0:
        return row[0]
    return None


def paired(row, entry, exit_, existing):
    side = 1 if row["direction"] == "LONG" else -1
    planned, eligible = selection(entry, row["initial_stop_underlying"], side, row["initial_quantity"], existing)
    return {"entry_time": row["entry_time"], "exit_time": row["exit_time"], "option_net": row["net_pnl"],
            "entry_mark": entry, "exit_mark": exit_, "side": side, "future_gross": side * (exit_ - entry) * LOT,
            "future_net": [amount(entry, exit_, side, friction) for friction in FILL_POINTS],
            "modeled_stop_loss": planned, "eligible_proxies": eligible}


def annual(year, native):
    folder = DATASETS[year]
    manifest = json.loads((folder / "manifest.json").read_bytes())
    receipts, missing = [], []
    with closing(sqlite3.connect((folder / "breeze.sqlite").resolve().as_uri() + "?mode=ro", uri=True)) as con:
        con.execute("PRAGMA query_only=ON")
        for row in native:
            assert row["status"] == "CLOSED"
            day = row["entry_time"][:10]
            assert day == row["exit_time"][:10]
            expiry = next((d for d in manifest["future_expiries"] if d >= day), None)
            entry, exit_ = (mark(con, expiry, row[f"{key}_time"]) for key in ("entry", "exit"))
            if None in (entry, exit_) or (entry, exit_) != (row["entry_underlying"], row["exit_underlying"]):
                missing.append({"entry_time": row["entry_time"], "priced": [entry, exit_],
                                "native_marks": [row["entry_underlying"], row["exit_underlying"]]})
                continue
            context = row["n091_entry"]["native_gate_context"]
            receipts.append(paired(row, entry, exit_, context["open_positions"]))
    return {"baseline": sum(row["net_pnl"] for row in native), "pairs": receipts, "missing": missing}


def summary(panels, margin, stress):
    annual_delta = {}
    daily = defaultdict(float)
    counts = {}
    for year, panel in panels.items():
        selected = [r for r in panel["pairs"] if margin is None or margin in r["eligible_proxies"]]
        counts[year] = len(selected)
        annual_delta[year] = 0.
        for row in selected:
            delta = row["future_net"][stress] - row["option_net"]
            daily[row["entry_time"][:10]] += delta
            annual_delta[year] += delta
    total = sum(annual_delta.values())
    best = sorted((p for p in daily.values() if p > 0), reverse=True)[:5]
    return {"changes": counts, "net_delta": round(total, 2),
            "annual_delta": {y: round(value, 2) for y, value in annual_delta.items()},
            "after_best_five": round(total - sum(best), 2), "worst_incremental_day": round(min([0., *daily.values()]), 2)}


def main():
    spec = HERE / "round25-freeze.json"
    frozen = json.loads(spec.read_bytes())
    assert frozen == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{spec.relative_to(ROOT).as_posix()}"], cwd=ROOT))
    for file, sha in frozen["source"].items():
        assert hashlib.sha256((HERE / file).read_text(encoding="utf-8").encode()).hexdigest() == sha
    panels = {}
    for year, folder in DATASETS.items():
        receipt, native = trades(year, "N11T")
        manifest = folder / "manifest.json"
        assert [digest(receipt), digest(manifest)] == frozen["inputs"][year]
        assert digest(folder / "breeze.sqlite") == json.loads(manifest.read_bytes())["files_sha256"]["breeze.sqlite"]
        panels[year] = annual(year, native["trades"])
    result = {"annual": panels, "coverage": {y: [len(p["pairs"]), len(p["missing"])] for y, p in panels.items()},
              "all_priced_gross": round(sum(r["future_gross"] for p in panels.values() for r in p["pairs"]), 2),
              "summaries": {"unrestricted" if margin is None else str(margin):
                            [summary(panels, margin, stress) for stress in range(len(FILL_POINTS))]
                            for margin in (None, *MARGINS)}}
    with (HERE / "round25-results.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "annual"}, indent=2))


if __name__ == "__main__":
    main()

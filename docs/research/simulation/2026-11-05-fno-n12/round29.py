"""Reconcile modeled crossing and separately booked costs for native N11T tickets."""

from collections import Counter
from contextlib import closing
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

from anatomy import DATASETS, trades
from round25 import digest, LOT


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
YEAR_SOURCE = ROOT / "docs/research/fno/2026-10-29-year-genome"
sys.path[:0] = [str(YEAR_SOURCE), str(ROOT / "python-engine")]
from cost_schedules import options_cost_snapshot
from fno_costs import calc_fno_costs_from_snapshot
from yeardata import bid_ask


def settlement_tickets(row):
    assert row["status"] == "CLOSED"
    assert row["initial_quantity"] == LOT * row["lots_at_exit"]
    assert row["entry_premium"] == row["initial_entry_premium"]
    yield (row["entry_time"], row["exit_time"], row["entry_premium"], row["exit_premium"],
           row["initial_quantity"], row["extra_cost"])
    for child in row["n10_children"]:
        yield child["at"], child["exit_at"], child["ask"], child["bid"], child["qty"], child["extra"]


def identity(symbol):
    match = re.fullmatch(r"NIFTY(\d{6})(\d+)(CE|PE)", symbol)
    assert match, symbol
    raw_expiry, strike, right = match.groups()
    return datetime.strptime(raw_expiry, "%y%m%d").date().isoformat(), float(strike), right


def print_before(con, contract, time):
    at = datetime.fromisoformat(time).strftime("%Y-%m-%d %H:%M:00")
    return con.execute("SELECT datetime,close,volume FROM candles WHERE kind='option' AND expiry=? AND strike=? AND opt=? "
                       "AND datetime>=? AND datetime<=? ORDER BY datetime DESC LIMIT 1",
                       (*contract, at[:10], at)).fetchone()


def crossing(con, contract, opened, closed, ask, bid, qty):
    buy = print_before(con, contract, opened)
    sell = print_before(con, contract, closed)
    if not buy or not sell or not buy[1] or not sell[1]:
        return "missing_model_print", None
    if bid_ask(buy[1])[1] != ask or bid_ask(sell[1])[0] != bid:
        return "modeled_quote_mismatch", None
    cost = ((ask - buy[1]) + (sell[1] - bid)) * qty
    return ("matched_positive_volume" if min(buy[2] or 0, sell[2] or 0) > 0 else "matched_zero_volume"), cost


def annual(con, rows, cost_snapshot):
    counts = Counter()
    total = dict(net=0., gross=0., charges=0., extra=0., crossing=0., crossing_positive_volume=0.)
    exceptions = []
    for row in rows:
        contract = identity(row["tradingsymbol"])
        gross = charges = extra = 0.
        for opened, closed, ask, bid, qty, stress in settlement_tickets(row):
            gross += (bid - ask) * qty
            charges += calc_fno_costs_from_snapshot(ask, bid, qty, cost_snapshot)
            extra += stress
            status, price_cost = crossing(con, contract, opened, closed, ask, bid, qty)
            counts[status] += 1
            if price_cost is None:
                exceptions.append((row["tradingsymbol"], opened, closed, qty, status))
            else:
                total["crossing"] += price_cost
                if status == "matched_positive_volume":
                    total["crossing_positive_volume"] += price_cost
        assert abs(gross - row["gross_pnl"]) < .002, row["entry_time"]
        assert abs(gross - charges - extra - row["net_pnl"]) < .002, row["entry_time"]
        total["net"] += row["net_pnl"]
        total["gross"] += gross
        total["charges"] += charges
        total["extra"] += extra
    return {"parent_trades": len(rows), "ticket_coverage": counts, "totals": total, "exceptions": exceptions}


def main():
    freeze = HERE / "round29-freeze.json"
    spec = json.loads(freeze.read_bytes())
    assert spec == json.loads(subprocess.check_output(["git", "show", f"HEAD:{freeze.relative_to(ROOT).as_posix()}"], cwd=ROOT))
    for path, value in spec["source"].items():
        assert hashlib.sha256((ROOT / path).read_text(encoding="utf-8").encode()).hexdigest() == value
    current_cost = options_cost_snapshot("NFO")
    assert current_cost == spec["option_cost_snapshot"]
    result = {}
    for year, folder in DATASETS.items():
        receipt, native = trades(year, "N11T")
        manifest, database = folder / "manifest.json", folder / "breeze.sqlite"
        assert [digest(receipt), digest(manifest)] == spec["inputs"][year]
        assert digest(database) == json.loads(manifest.read_bytes())["files_sha256"]["breeze.sqlite"]
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as con:
            con.execute("PRAGMA query_only=ON")
            result[year] = annual(con, native["trades"], current_cost)
    totals = {key: sum(panel["totals"][key] for panel in result.values()) for key in result["2022"]["totals"]}
    coverage = sum((Counter(panel["ticket_coverage"]) for panel in result.values()), Counter())
    out = {"windows": result, "totals": totals, "coverage": coverage,
           "twenty_percent_target_increment": .20 * totals["net"],
           "share_of_target_from_all_matched_crossing_pct": 100. * totals["crossing"] / (.20 * totals["net"])}
    with (HERE / "round29-results.json").open("x", encoding="utf-8") as handle:
        json.dump(out, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print(json.dumps({k: v for k, v in out.items() if k != "windows"}, indent=2), flush=True)


if __name__ == "__main__":
    main()

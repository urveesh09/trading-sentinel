"""Count cash- and risk-matched two-lot option alternatives before pricing exits."""

from collections import Counter
from contextlib import closing
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess

from anatomy import DATASETS, trades
from round25 import digest, LOT
from round29 import ROOT, bid_ask, calc_fno_costs_from_snapshot, identity, options_cost_snapshot
from round32 import Print
from fno_chain import RISK_FREE_RATE, years_to_expiry
from fno_n11 import backstop_points, stop_price
from options_math import delta, implied_vol


HERE = Path(__file__).resolve().parent
TWO = 2 * LOT
EXTRA = 210.


def strikes(future, right):
    direction = 1 if right == "CE" else -1
    anchor = math.floor(future / 50) if right == "CE" else math.ceil(future / 50)
    return tuple(50 * (anchor + direction * i) for i in (1, 2, 3))


def entry_quote(db, expiry, strike, right, now):
    assert now.second == 59 and now.microsecond == 0
    price = db.execute("SELECT close,oi FROM candles WHERE kind='option' AND expiry=? AND strike=? AND opt=? "
                       "AND datetime=? AND close>0 AND volume>=?",
                       (expiry, strike, right, now.strftime("%Y-%m-%d %H:%M:00"), TWO)).fetchone()
    return Print(*bid_ask(price[0]), price[1] or 0) if price else None


def geometry(row, ask, bid, abs_delta, fees):
    old_ask, old_delta, old_extra = row["entry_premium"], abs(row["delta_at_entry"]), row["extra_cost"]
    if abs_delta < .25 or 2 * abs_delta < 1.10 * old_delta:
        return "delta", None
    old_cash = old_ask * LOT + fees(old_ask, 0., LOT) + old_extra
    new_cash = ask * TWO + fees(ask, 0., TWO) + EXTRA
    if new_cash > old_cash:
        return "cash", None
    old_stop = row["n11_entry"].get("premium_stop", .75 * old_ask)
    risk = (old_ask - old_stop) * LOT + fees(old_ask, old_stop, LOT) + old_extra
    points = backstop_points(risk, ask, TWO, EXTRA, fees)
    if points is None:
        return "stop", None
    stop = max(stop_price(ask, points), stop_price(ask, .25 * ask))
    if stop >= bid:
        return "stop", None
    return "eligible", {"ask": ask, "bid": bid, "stop": stop, "new_reserve": new_cash, "native_reserve": old_cash,
                        "new_abs_delta_per_unit": abs_delta, "native_abs_delta_per_unit": old_delta,
                        "modeled_stop_loss": (ask - stop) * TWO + fees(ask, stop, TWO) + EXTRA,
                        "native_modeled_stop_loss": risk}


def annual(db, native, snapshot):
    counts, strike_notes = Counter(), Counter()
    eligible = []

    def fees(buy, sell, qty):
        return calc_fno_costs_from_snapshot(buy, sell, qty, snapshot)

    for row in native:
        assert row["status"] == "CLOSED"
        context = row["n091_entry"]["native_gate_context"]
        if row["initial_quantity"] != LOT or context["open_positions"]:
            counts["not_flat_one_lot"] += 1
            continue
        clock = row["entry_time"]
        expiry, _, right = identity(row["tradingsymbol"])
        assert expiry > clock[:10]
        now = datetime.fromisoformat(clock)
        time = years_to_expiry(date.fromisoformat(expiry), now)
        future = context["forward"]
        candidates = []
        for strike in strikes(future, right):
            quote = entry_quote(db, expiry, strike, right, now)
            if quote is None or not quote.entry_usable:
                strike_notes["entry_quote"] += 1
                continue
            iv = implied_vol((quote.bid + quote.ask) / 2, future, strike, time, RISK_FREE_RATE, right == "CE")
            if iv is None:
                strike_notes["iv"] += 1
                continue
            d = abs(delta(future, strike, time, iv, RISK_FREE_RATE, right == "CE"))
            status, data = geometry(row, quote.ask, quote.bid, d, fees)
            strike_notes[status] += 1
            if data:
                candidates.append({"entry": clock, "expiry": expiry, "right": right, "strike": strike, **data})
        if not candidates:
            counts["no_risk_matched_alternate"] += 1
            continue
        counts["eligible"] += 1
        eligible.append(max(candidates, key=lambda x: (x["new_abs_delta_per_unit"], -x["new_reserve"])))
    assert sum(counts.values()) == len(native)
    return {"counts": counts, "strike_funnel": strike_notes, "eligible": eligible}


def main():
    frozen = HERE / "round34-freeze.json"
    spec = json.loads(frozen.read_bytes())
    assert spec == json.loads(subprocess.check_output(["git", "show", f"HEAD:{frozen.relative_to(ROOT).as_posix()}"], cwd=ROOT))
    for file, sha in spec["source"].items():
        assert hashlib.sha256((ROOT / file).read_text(encoding="utf-8").encode()).hexdigest() == sha
    snapshot = options_cost_snapshot("NFO")
    assert snapshot == spec["option_cost_snapshot"]
    panels = {}
    for year, folder in DATASETS.items():
        receipt, native = trades(year, "N11T")
        manifest, database = folder / "manifest.json", folder / "breeze.sqlite"
        assert [digest(receipt), digest(manifest)] == spec["inputs"][year]
        assert digest(database) == json.loads(manifest.read_bytes())["files_sha256"]["breeze.sqlite"]
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            panels[year] = annual(db, native["trades"], snapshot)
    by_year = {y: len(p["eligible"]) for y, p in panels.items()}
    result = {"by_year": by_year, "total_eligible": sum(by_year.values()),
              "advance": sum(by_year.values()) >= 20 and sum(n > 0 for n in by_year.values()) >= 4, "panels": panels}
    with (HERE / "round34-results.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "panels"}, indent=2), flush=True)


if __name__ == "__main__":
    main()

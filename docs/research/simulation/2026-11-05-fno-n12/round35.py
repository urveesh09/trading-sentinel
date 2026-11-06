"""Compare the frozen R34 strikes at fixed deadlines and with a premium backstop."""

from collections import defaultdict
from contextlib import closing
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from anatomy import DATASETS, trades
from round25 import digest, LOT
from round29 import ROOT, bid_ask, calc_fno_costs_from_snapshot, options_cost_snapshot, settlement_tickets
from round34 import EXTRA, TWO, entry_quote


HERE = Path(__file__).resolve().parent
NATIVE, GUARD = "NATIVE_CLOCK", "PREMIUM_GUARD"


def timed_exit(opened, closed, quotes, stop):
    if stop is None:
        bid, vol = quotes.get(closed, (0., 0.))
        return (closed, bid, "native_deadline") if bid > 0 and vol >= TWO else None
    minute = opened + timedelta(minutes=1)
    triggered = False
    while minute <= closed:
        mark = quotes.get(minute)
        if mark is None and not triggered:
            return None
        bid, vol = mark or (0., 0.)
        if (triggered or minute == closed) and bid > 0 and vol >= TWO:
            return minute, bid, "premium_backstop" if triggered else "native_deadline"
        if 0 < bid <= stop and vol > 0:
            triggered = True
        minute += timedelta(minutes=1)
    return None


def annual(db, native, selected, snapshot):
    by_clock = {row["entry_time"]: row for row in native}
    assert len(by_clock) == len(native)
    daily = defaultdict(float)
    for row in native:
        daily[row["exit_time"][:10]] += row["net_pnl"]
    rows = []

    def fees(buy, sell, qty):
        return calc_fno_costs_from_snapshot(buy, sell, qty, snapshot)

    for ticket in selected:
        row = by_clock[ticket["entry"]]
        opened_at, closed_at, old_ask, old_bid, qty, old_extra = next(settlement_tickets(row))
        assert qty == LOT and opened_at[:10] == closed_at[:10]
        opened, closed = (datetime.fromisoformat(at).replace(second=0, microsecond=0, tzinfo=None)
                          for at in (opened_at, closed_at))
        assert opened < closed
        identity = (ticket["expiry"], ticket["strike"], ticket["right"])
        exact_entry = entry_quote(db, *identity, datetime.fromisoformat(opened_at))
        assert exact_entry and exact_entry.entry_usable and exact_entry.ask == ticket["ask"]
        tape = {datetime.fromisoformat(stamp): (bid_ask(price)[0], volume or 0) for stamp, price, volume in db.execute(
            "SELECT datetime,close,volume FROM candles WHERE kind='option' AND expiry=? AND strike=? AND opt=? "
            "AND datetime>? AND datetime<=? AND close>0", (*identity, opened.isoformat(sep=" "), closed.isoformat(sep=" ")))}
        old_net = (old_bid - old_ask) * LOT - fees(old_ask, old_bid, LOT) - old_extra
        details = {"entry": opened_at, "strike": ticket["strike"], "stop": ticket["stop"], "native_parent_net": old_net,
                   "earned_children_held_fixed": row["net_pnl"] - old_net}
        for mode, stop in ((NATIVE, None), (GUARD, ticket["stop"])):
            filled = timed_exit(opened, closed, tape, stop)
            if filled is None:
                details[mode] = None
                continue
            at, bid, reason = filled
            gross = (bid - exact_entry.ask) * TWO
            net = gross - fees(exact_entry.ask, bid, TWO) - EXTRA
            details[mode] = {"at": at.isoformat(sep=" "), "bid": bid, "reason": reason, "net": net,
                             "increment": net - old_net, "increment_double": net - old_net - EXTRA + old_extra}
        rows.append(details)
    return {"native_daily": daily, "tickets": rows}


def summary(panels, mode):
    unresolved = sum(row[mode] is None for panel in panels.values() for row in panel["tickets"])
    priced = sum(len(panel["tickets"]) for panel in panels.values()) - unresolved
    stats = {"priced": priced, "unresolved": unresolved}
    for key in ("increment", "increment_double"):
        deltas = defaultdict(float)
        annual_delta = {}
        for year, panel in panels.items():
            found = [r for r in panel["tickets"] if r[mode] is not None]
            annual_delta[year] = sum(r[mode][key] for r in found)
            for row in found:
                deltas[row["entry"][:10]] += row[mode][key]
        total = sum(deltas.values())
        removed = sum(sorted((v for v in deltas.values() if v > 0), reverse=True)[:5])
        stats[key] = {"total": total, "after_best_five": total - removed, "annual": annual_delta}
        if key == "increment":
            days = {d: p for panel in panels.values() for d, p in panel["native_daily"].items()}
            stats["native_worst_day"] = min([0., *days.values()])
            stats["conditional_worst_day"] = min([0., *(p + deltas[d] for d, p in days.items())])
    base, stress = stats["increment"], stats["increment_double"]
    stats["advance"] = (unresolved == 0 and priced == 53 and base["total"] >= 10000.
                        and all(v >= -2500. for v in base["annual"].values())
                        and stats["conditional_worst_day"] >= stats["native_worst_day"] - 1000.
                        and min(base["after_best_five"], stress["after_best_five"]) > 0.)
    return stats


def main():
    freeze = HERE / "round35-freeze.json"
    spec = json.loads(freeze.read_bytes())
    assert spec == json.loads(subprocess.check_output(["git", "show", f"HEAD:{freeze.relative_to(ROOT).as_posix()}"], cwd=ROOT))
    for file, sha in spec["source"].items():
        assert hashlib.sha256((ROOT / file).read_text(encoding="utf-8").encode()).hexdigest() == sha
    snapshot = options_cost_snapshot("NFO")
    assert snapshot == spec["option_cost_snapshot"]
    entry = json.loads((HERE / "round34-results.json").read_bytes())
    assert entry["advance"] and entry["total_eligible"] == 53
    panels = {}
    for year, folder in DATASETS.items():
        receipt, native = trades(year, "N11T")
        manifest, database = folder / "manifest.json", folder / "breeze.sqlite"
        assert [digest(receipt), digest(manifest)] == spec["inputs"][year]
        assert digest(database) == json.loads(manifest.read_bytes())["files_sha256"]["breeze.sqlite"]
        with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("PRAGMA query_only=ON")
            panels[year] = annual(db, native["trades"], entry["panels"][year]["eligible"], snapshot)
    output = {"summary": {mode: summary(panels, mode) for mode in (NATIVE, GUARD)}, "panels": panels}
    with (HERE / "round35-results.json").open("x", encoding="utf-8") as handle:
        json.dump(output, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print(json.dumps(output["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()

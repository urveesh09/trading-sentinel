"""Price a cash-reserved credit vertical on identical native parent clocks."""

from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess

from anatomy import DATASETS, trades
from round25 import digest, LOT
from round29 import ROOT, bid_ask, calc_fno_costs_from_snapshot, identity, options_cost_snapshot, settlement_tickets


HERE = Path(__file__).resolve().parent
WIDTH = 50
FEE_RESERVE = 250.
EXTRA = 205.


@dataclass(frozen=True)
class Print:
    bid: float
    ask: float
    oi: float

    @property
    def entry_usable(self):
        return self.oi >= 5000 and (self.ask - self.bid) / ((self.ask + self.bid) / 2) <= .015


def vertical(future, direction):
    if direction == "LONG":
        sold = WIDTH * math.floor(future / WIDTH)
        return "PE", sold, sold - WIDTH
    assert direction == "SHORT"
    sold = WIDTH * math.ceil(future / WIDTH)
    return "CE", sold, sold + WIDTH


def mark(db, expiry, strike, right, clock):
    at = datetime.fromisoformat(clock)
    assert at.second == 59 and at.microsecond == 0, clock
    row = db.execute("SELECT close,volume,oi FROM candles WHERE kind='option' AND expiry=? AND strike=? "
                     "AND opt=? AND datetime=?", (expiry, strike, right, at.strftime("%Y-%m-%d %H:%M:00"))).fetchone()
    if row and row[0] and row[0] > 0 and (row[1] or 0) >= LOT:
        bid, ask = bid_ask(row[0])
        return Print(bid, ask, row[2] or 0)
    return None


def charges(buy, sell, snapshot):
    return calc_fno_costs_from_snapshot(buy, sell, LOT, snapshot)


def selection(row, short, hedge, snapshot):
    if not short.entry_usable or not hedge.entry_usable:
        return "entry_quality", None
    credit = (short.bid - hedge.ask) * LOT
    add = FEE_RESERVE + 2 * EXTRA
    if not add < credit < WIDTH * LOT:
        return "credit", None
    original = row["entry_premium"]
    backstop = row["n11_entry"].get("premium_stop", .75 * original)
    planned_native = (original - backstop) * LOT + charges(original, backstop, snapshot) + row["extra_cost"]
    capped = WIDTH * LOT - credit + add
    if capped > planned_native:
        return "risk", None
    context = row["n091_entry"]
    reserve = (WIDTH + hedge.ask) * LOT + add
    if context["open_reserve"] + reserve > .15 * context["pool"]:
        return "cash", None
    return "selected", {"credit": credit, "reserved_cash": reserve, "planned_vertical_loss": capped,
                         "planned_native_loss": planned_native}


def amounts(short, hedge, cover, sale, snapshot):
    gross = (short.bid - hedge.ask - cover.ask + sale.bid) * LOT
    fee = charges(cover.ask, short.bid, snapshot) + charges(hedge.ask, sale.bid, snapshot)
    return gross, fee, gross - fee - 2 * EXTRA


def annual(db, rows, snapshot):
    counts = Counter()
    priced, unresolved = [], []
    for row in rows:
        # R29 already reconciled the whole account. Compute just the parent
        # and verify the arithmetic does not accidentally include an earned lot.
        parent, *children = settlement_tickets(row)
        opened, closed, native_ask, native_bid, qty, extra = parent
        if qty != LOT or row["n091_entry"]["native_gate_context"]["open_positions"]:
            counts["not_flat_one_lot"] += 1
            continue
        day = opened[:10]
        expiry, _, _ = identity(row["tradingsymbol"])
        assert day == closed[:10] and expiry > day
        right, short_strike, hedge_strike = vertical(row["entry_underlying"], row["direction"])
        short, hedge = (mark(db, expiry, strike, right, opened) for strike in (short_strike, hedge_strike))
        if short is None or hedge is None:
            counts["missing_entry_print"] += 1
            continue
        status, admission = selection(row, short, hedge, snapshot)
        counts[status] += 1
        if admission is None:
            continue
        cover, sale = (mark(db, expiry, strike, right, closed) for strike in (short_strike, hedge_strike))
        ticket = {"entry": opened, "exit": closed, "expiry": expiry, "right": right,
                  "short_strike": short_strike, "hedge_strike": hedge_strike, **admission}
        if cover is None or sale is None:
            unresolved.append(ticket)
            continue
        native = (native_bid - native_ask) * LOT - charges(native_ask, native_bid, snapshot) - extra
        child_net = sum((b - a) * n - calc_fno_costs_from_snapshot(a, b, n, snapshot) - s for _, _, a, b, n, s in children)
        assert abs(native + child_net - row["net_pnl"]) < .002
        gross, fee, net = amounts(short, hedge, cover, sale, snapshot)
        priced.append({**ticket, "gross": gross, "charges": fee, "vertical_net": net, "native_parent_net": native,
                       "increment": net - native, "increment_double": net - native - 2 * EXTRA + extra,
                       "native_children_net_held_fixed": child_net})
    assert sum(counts.values()) == len(rows) and counts["selected"] == len(priced) + len(unresolved)
    return {"counts": counts, "priced": priced, "unresolved": unresolved}


def summarized(panels):
    counts = sum((Counter(panel["counts"]) for panel in panels.values()), Counter())
    unresolved = sum(len(panel["unresolved"]) for panel in panels.values())
    output = {"counts": counts, "unresolved": unresolved}
    for key in ("increment", "increment_double"):
        daily = defaultdict(float)
        annual_delta = {year: sum(r[key] for r in p["priced"]) for year, p in panels.items()}
        for panel in panels.values():
            for row in panel["priced"]:
                daily[row["entry"][:10]] += row[key]
        total = sum(annual_delta.values())
        removed = sum(sorted((v for v in daily.values() if v > 0), reverse=True)[:5])
        output[key] = {"total": total, "after_best_five": total - removed, "annual": annual_delta}
    base, stress = output["increment"], output["increment_double"]
    output["advance"] = (counts["selected"] >= 20 and not unresolved and base["total"] >= 10000.
                         and all(p >= -2500. for p in base["annual"].values())
                         and min(base["after_best_five"], stress["after_best_five"]) > 0.)
    return output


def main():
    freeze = HERE / "round32-freeze.json"
    spec = json.loads(freeze.read_bytes())
    assert spec == json.loads(subprocess.check_output(["git", "show", f"HEAD:{freeze.relative_to(ROOT).as_posix()}"], cwd=ROOT))
    for file, expected in spec["source"].items():
        assert hashlib.sha256((ROOT / file).read_text(encoding="utf-8").encode()).hexdigest() == expected
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
    output = {"summary": summarized(panels), "windows": panels}
    with (HERE / "round32-results.json").open("x", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(json.dumps(output["summary"], indent=2), flush=True)


if __name__ == "__main__":
    main()

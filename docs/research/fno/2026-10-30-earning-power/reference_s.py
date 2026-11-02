"""O30s references -> reference.json. Information only: nothing here can be a pick, and no runtime module imports this.

1. THE CEILING. What was there to earn per lot with perfect hindsight, so the book's rupees have a scale:
     PEAK   buy the at-the-money call or put at 09:45 (ask) and sell at its best minute close until 15:10 (bid),
            whichever of the two made more;
     DIRECTION  buy at 09:45 the side the day finally went (15:10 against 09:45) and hold to 15:10.
   Then how much of it the book caught, on the biggest days and on the rest.

2. OPTION SELLING, the owner's rule forbids it; it is priced because the owner asked why others earn so much. The usual
   retail form, one textbook setting each, not searched, expiry days skipped:
     STRADDLE   sell the at-the-money call and put at 09:20 (bid), buy a leg back if its ask reaches 1.30 x the sale,
                buy the rest back at 15:10 (ask);
     HEDGED     the same plus long wings 200 points away, bought at 09:20 and sold at 15:10 (defined risk).
   Stress: Rs 100 per leg per day per lot. A stop tested on minute closes flatters the worst days of a short position.
   Also: the correlation of each with the BEST book's days, and what they would have done together.

Read-only on the sealed datasets; no network, no broker.
"""
from __future__ import annotations

import json
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path[:0] = [str(ROOT / "python-engine"), str(ROOT / "docs/research/fno/2026-10-29-year-genome")]
from fno_costs import calc_fno_costs  # noqa: E402
from yeardata import bid_ask  # noqa: E402

LOT = 65
STEP = 50
WING = 200
STOP = 1.30
LEG_STRESS = 100.0
DATA = {"2025": ROOT / "docs/research/fno/2026-10-30-nifty-2025-test/_local/dataset-nifty-2025/breeze.sqlite",
        "2026": ROOT / "docs/research/fno/2026-10-29-year-genome/_local/dataset-nifty/breeze.sqlite"}


def sessions(year: str) -> list[str]:
    if year == "2026":
        return json.loads((ROOT / "docs/research/fno/2026-10-29-year-genome/freeze.json").read_text(encoding="utf-8"))["bindings"]["year_sessions"]
    return json.loads((ROOT / "docs/research/fno/2026-10-30-nifty-2025-test/freeze.json").read_text(encoding="utf-8"))["bindings"]["sessions"]


class Day:
    def __init__(self, con, day: str, expiry: str):
        self.con, self.day, self.expiry = con, day, expiry

    def leg(self, strike: float, opt: str) -> dict:
        """minute 'HH:MM' -> close of this contract today."""
        rows = self.con.execute(
            "SELECT datetime, close FROM candles WHERE kind='option' AND expiry=? AND strike=? AND opt=? AND datetime>=? AND datetime<=?",
            (self.expiry, strike, opt, f"{self.day} 09:15:00", f"{self.day} 15:30:00")).fetchall()
        return {r[0][11:16]: float(r[1]) for r in rows}


def _at(leg: dict, minute: str, back: int = 3):
    """The close at this minute, or the last trade in the few minutes before it."""
    h, m = int(minute[:2]), int(minute[3:])
    for k in range(back + 1):
        total = h * 60 + m - k
        key = f"{total // 60:02d}:{total % 60:02d}"
        if key in leg:
            return leg[key]
    return None


def _minutes(first: str, last: str):
    a, b = int(first[:2]) * 60 + int(first[3:]), int(last[:2]) * 60 + int(last[3:])
    return [f"{t // 60:02d}:{t % 60:02d}" for t in range(a, b + 1)]


def spot(con, day: str, minute: str):
    r = con.execute("SELECT close FROM candles WHERE kind='index' AND datetime<=? AND datetime>=? ORDER BY datetime DESC LIMIT 1",
                    (f"{day} {minute}:00", f"{day} 09:15:00")).fetchone()
    return float(r[0]) if r else None


def buy_leg(leg: dict, first: str, last: str, mode: str) -> float | None:
    """Per-lot net of buying at `first`: mode PEAK sells at the best minute, HOLD at `last`."""
    c0 = _at(leg, first)
    if c0 is None:
        return None
    ask = bid_ask(c0)[1]
    if mode == "HOLD":
        c1 = _at(leg, last)
        if c1 is None:
            return None
        sell = bid_ask(c1)[0]
    else:
        closes = [leg[m] for m in _minutes(first, last) if m in leg and m > first]
        if not closes:
            return None
        sell = bid_ask(max(closes))[0]
    return (sell - ask) * LOT - calc_fno_costs(ask, sell, LOT)


def short_leg(leg: dict, first: str, last: str, stop: bool = True) -> float | None:
    c0 = _at(leg, first)
    if c0 is None:
        return None
    sold = bid_ask(c0)[0]
    bought = None
    if stop:
        for m in _minutes(first, last):
            if m > first and m in leg and bid_ask(leg[m])[1] >= STOP * sold:
                bought = bid_ask(leg[m])[1]
                break
    if bought is None:
        c1 = _at(leg, last)
        if c1 is None:
            return None
        bought = bid_ask(c1)[1]
    return (sold - bought) * LOT - calc_fno_costs(bought, sold, LOT)


def summary(daily: dict) -> dict:
    run = peak = dd = 0.0
    months, weeks = defaultdict(float), defaultdict(float)
    for d in sorted(daily):
        run += daily[d]
        peak = max(peak, run)
        dd = max(dd, peak - run)
        months[d[:7]] += daily[d]
        iso = date.fromisoformat(d).isocalendar()
        weeks[(iso[0], iso[1])] += daily[d]
    return {"net": round(run), "days": len(daily), "fall_rs": round(dd), "worst_day": round(min([0.0, *daily.values()])),
            "best_day": round(max([0.0, *daily.values()])), "worst_week": round(min([0.0, *weeks.values()])),
            "green_months": sum(v > 0 for v in months.values()), "red_months": sum(v < 0 for v in months.values())}


def book_days(year: str, name: str) -> dict:
    raw = json.loads((HERE / f"_local/results-raw-{year}.json").read_text(encoding="utf-8"))
    daily: dict = defaultdict(float)
    for t in raw["trades"][raw["books"][name]]:
        if t.get("net_pnl") is not None:
            daily[t["entry_time"][:10]] += float(t["net_pnl"])
    return dict(daily)


def main() -> None:
    out = {"schema": "o30s_reference_v1", "lot": LOT, "wing_points": WING, "leg_stop": STOP, "leg_stress": LEG_STRESS,
           "qualification": "INFORMATION_ONLY", "can_place_orders": False}
    for year in ("2025", "2026"):
        con = sqlite3.connect(f"file:{DATA[year]}?mode=ro", uri=True)
        expiries = sorted(r[0] for r in con.execute("SELECT DISTINCT expiry FROM candles WHERE kind='option'"))
        peak, direction, straddle, hedged, skipped = {}, {}, {}, {}, defaultdict(int)
        for day in sessions(year):
            expiry = next((e for e in expiries if e >= day), None)
            if expiry is None:
                skipped["no_expiry"] += 1
                continue
            d = Day(con, day, expiry)
            at945 = spot(con, day, "09:45")
            if at945 is None:
                skipped["no_0945_spot"] += 1
                continue
            k = round(at945 / STEP) * STEP
            ce, pe = d.leg(k, "CE"), d.leg(k, "PE")
            pk = [v for v in (buy_leg(ce, "09:45", "15:10", "PEAK"), buy_leg(pe, "09:45", "15:10", "PEAK")) if v is not None]
            if pk:
                peak[day] = max(0.0, *pk)
            last = spot(con, day, "15:10")
            if last is not None:
                side = ce if last >= at945 else pe
                held = buy_leg(side, "09:45", "15:10", "HOLD")
                if held is not None:
                    direction[day] = held
            if day == expiry:
                skipped["expiry_day_no_selling"] += 1
                continue
            at920 = spot(con, day, "09:20")
            if at920 is None:
                skipped["no_0920_spot"] += 1
                continue
            k2 = round(at920 / STEP) * STEP
            ce2, pe2 = d.leg(k2, "CE"), d.leg(k2, "PE")
            a, b = short_leg(ce2, "09:20", "15:10"), short_leg(pe2, "09:20", "15:10")
            if a is None or b is None:
                skipped["no_short_leg"] += 1
                continue
            straddle[day] = a + b - 2 * LEG_STRESS
            wc, wp = d.leg(k2 + WING, "CE"), d.leg(k2 - WING, "PE")
            w1, w2 = buy_leg(wc, "09:20", "15:10", "HOLD"), buy_leg(wp, "09:20", "15:10", "HOLD")
            if w1 is None or w2 is None:
                skipped["no_wing"] += 1
                continue
            hedged[day] = a + b + w1 + w2 - 4 * LEG_STRESS
        days_sorted = sorted(peak, key=lambda x: -peak[x])
        top = set(days_sorted[:max(1, len(days_sorted) // 10)])
        block = {"sessions": len(sessions(year)), "skipped": dict(skipped),
                 "ceiling_peak_per_lot": round(sum(peak.values())), "ceiling_direction_per_lot": round(sum(direction.values())),
                 "median_peak_day": round(statistics.median(peak.values())), "best_peak_day": round(max(peak.values())),
                 "top10pct_days_share_of_peak": round(sum(peak[x] for x in top) / sum(peak.values()), 3),
                 "catch": {}, "selling": {"STRADDLE": summary(straddle), "HEDGED": summary(hedged)}}
        for name in ("LIVE", "BEST", "TPB"):
            days = book_days(year, name)
            block["catch"][name] = {"book_per_lot": round(sum(days.values())),
                                    "share_of_ceiling": round(sum(days.values()) / sum(peak.values()), 3),
                                    "on_top10pct_days": round(sum(v for x, v in days.items() if x in top)),
                                    "on_other_days": round(sum(v for x, v in days.items() if x not in top)),
                                    "top10pct_days_traded": sum(x in days for x in top), "top10pct_days": len(top)}
        best = book_days(year, "BEST")
        common = sorted(set(straddle) | set(best))
        for label, series in (("STRADDLE", straddle), ("HEDGED", hedged)):
            a = np.array([best.get(x, 0.0) for x in common])
            b = np.array([series.get(x, 0.0) for x in common])
            block["selling"][label]["correlation_with_BEST"] = round(float(np.corrcoef(a, b)[0, 1]), 3)
            block["selling"][label]["with_BEST_1_lot_each"] = summary({x: best.get(x, 0.0) + series.get(x, 0.0) for x in common})
        out[year] = block
        con.close()
        print(year, json.dumps(block)[:1600], flush=True)
    (HERE / "reference.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

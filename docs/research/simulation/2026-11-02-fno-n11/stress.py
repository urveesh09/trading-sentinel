"""All 256 orderings of whole years, on the same causal one-lot proxy as N10's stress test, with N11's stand-aside and the native 15% stop. Writes stress.json.

A proxy: fixed admissions from N08's one-lot paper trades, no earned lots, no regenerated market decisions. Exits settle before entries at the same instant.
Paper evidence reads only exits strictly before the entry being judged, in the order of THIS sequence. A trade keeps the volatility reading of its own real day.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import n11_rules as R  # noqa: E402

SIM = HERE.parent
N09 = SIM / "2026-11-01-fno-n09" / "_local"
YEARS = ("2023", "2024", "2025", "2026")
CAPITAL = 250000.0
FLOOR = CAPITAL * 0.85
RATIO, NEED = 0.9, 20
# N10's published table for the same proxy, same orderings. check 11 compares with WATCH.
N10_TABLE = {"NONE": {"worst_end": 211290, "median_end": 367877, "below_start": 67}, "CUSHION": {"worst_end": 215291, "median_end": 342954, "below_start": 50}, "WATCH": {"worst_end": 190822, "median_end": 362226, "below_start": 13}}


def vol_table() -> dict:
    rows = {}
    for p in (SIM / "2026-11-01-fno-n08/_local/daily-2023.json", SIM / "2026-10-31-fno-complements/_local/daily-2026.json"):
        for r in json.loads(p.read_text(encoding="utf-8"))["rows"]:
            rows[r[0]] = r
    days = sorted(rows)
    out, atr, reads, prev = {}, None, [], None
    for i, d in enumerate(days):
        if reads:
            good = reads[:-1][-250:]
            out[d] = (reads[-1], median(good) if len(good) >= 120 else None)
        _d, _o, h, l, c = rows[d]
        tr = h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev))
        atr = tr if atr is None else atr + (tr - atr) / 14
        if i >= 14:
            reads.append(atr / c * 100)
        prev = c
    return out


def load_streams() -> dict:
    vols = vol_table()
    out = {}
    for y in YEARS:
        key = json.loads((N09 / f"keys-diag-{y}.json").read_text(encoding="utf-8"))["DIAG"]
        rows = json.loads((N09 / f"evals-{y}" / f"{key}.json").read_text(encoding="utf-8"))["trades"]
        for t in rows:
            atr, usual = vols.get(t["entry_time"][:10], (None, None))
            t["_vol"] = {r: bool(atr is not None and usual is not None and atr >= usual * r) for r in (RATIO, 1.0)}
        out[y] = rows
    return out


def walk(sequence, streams, stand: bool = True, ratio: float = RATIO, need: int = NEED) -> dict:
    equity = low = peak = CAPITAL
    fall = 0.0
    stopped = False
    active: set = set()
    paper: list = []
    taken = waited = 0
    for block, year in enumerate(sequence):
        events = []
        for i, trade in enumerate(streams[year]):
            events += [(trade["entry_time"], 1, i, trade), (trade["exit_time"], 0, i, trade)]
        for at, kind, ident, trade in sorted(events, key=lambda e: e[:3]):
            if kind == 0:
                paper.append(float(trade["net_pnl"]))
                if ident in active:
                    active.remove(ident)
                    equity += float(trade["net_pnl"])
                    low, peak = min(low, equity), max(peak, equity)
                    fall = max(fall, (peak - equity) / peak)
                    stopped = stopped or equity < FLOOR
                continue
            if stopped:
                continue
            if stand and R.stand_aside(trade["_vol"][ratio], paper, need):
                waited += 1
                continue
            active.add(ident)
            taken += 1
        assert not active
    return {"end": equity, "low": low, "fall": fall * 100, "taken": taken, "waited": waited, "stopped": stopped}


def main() -> None:
    streams = load_streams()
    rows = {seq: walk(seq, streams) for seq in itertools.product(YEARS, repeat=4)}
    plain = {seq: walk(seq, streams, stand=False) for seq in rows}
    ends = sorted(r["end"] for r in rows.values())
    plain_ends = sorted(r["end"] for r in plain.values())
    assert round(plain_ends[0]) == N10_TABLE["NONE"]["worst_end"] and round((plain_ends[127] + plain_ends[128]) / 2) == N10_TABLE["NONE"]["median_end"], "the plain stop must reproduce N10's table"
    diff = [rows[s]["end"] - plain[s]["end"] for s in rows]
    n11 = {"worst_end": round(ends[0]), "median_end": round((ends[127] + ends[128]) / 2), "best_end": round(ends[-1]), "below_start": sum(e < CAPITAL for e in ends),
           "stopped_for_good": sum(r["stopped"] for r in rows.values()), "worst_fall_pct": round(max(r["fall"] for r in rows.values()), 2), "lowest_equity": round(min(r["low"] for r in rows.values()))}
    named = {"2023,2024,2025,2026": ("2023", "2024", "2025", "2026"), "2023 twice,2024,2025": ("2023", "2023", "2024", "2025"), "2023 three times,2024": ("2023", "2023", "2023", "2024"), "2023 four times": ("2023",) * 4}
    result = {"note": "Proxy at one lot, no earned lots. The native 15% stop stops for good below Rs 2,12,500. Not a forecast.", "n10_table": N10_TABLE, "N11_stand_aside": n11,
              "plain_15pct_stop": {"worst_end": round(plain_ends[0]), "median_end": round((plain_ends[127] + plain_ends[128]) / 2), "below_start": sum(e < CAPITAL for e in plain_ends), "stopped_for_good": sum(r["stopped"] for r in plain.values())},
              "against_plain_stop": {"helps": sum(d > 0.01 for d in diff), "hurts": sum(d < -0.01 for d in diff), "same": sum(abs(d) <= 0.01 for d in diff), "largest_gain": round(max(diff)), "largest_cost": round(min(diff))},
              "named": {k: {"plain": round(plain[v]["end"]), "N11": round(rows[v]["end"]), "N11_waited": rows[v]["waited"], "N11_taken": rows[v]["taken"], "N11_fall": round(rows[v]["fall"], 2), "stopped": rows[v]["stopped"]} for k, v in named.items()},
              "check_11": {"median_at_or_above_watch": n11["median_end"] >= N10_TABLE["WATCH"]["median_end"], "below_start_no_more_than_watch": n11["below_start"] <= N10_TABLE["WATCH"]["below_start"]}}
    (HERE / "stress.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()

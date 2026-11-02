"""O30s exact replays -> exact.json: the shipped code at real lot sizes, without the simulator's shortcut.

    O30C_YEAR=2025 python exact_s.py --name "TPB|HOUSE" --lots 3 --half
    O30C_YEAR=2026 python exact_s.py --name "LIVE|ADD2" --sizing shipped --half
    O30C_YEAR=2025 python exact_s.py --name TPB --lots 3 --skip

--lots N sizes every entry at N lots after the shipped planner accepts it (the planner's own gates, including the
minimum-pool gate on the real equity, stay on); an add adds as many lots as the entry had; own cash as in the simulator.
--sizing shipped keeps the shipped sizing and brakes. It compares the rupees with analyze_s.sim on the same choice.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyze_s as A  # noqa: E402
import lab_s as S  # noqa: E402
import lab_s2 as T2  # noqa: E402,F401  (the pass-over-stretched rule; books without "skip" are untouched)

C, Y, O27F = S.C, S.Y, S.O27F
from config import settings  # noqa: E402

LOCAL = HERE / "_local"
Y.EVALS = LOCAL / "exact"
RUN: dict = {}
_prev_entry, _prev_add, _prev_house = Y.BookReplay._entry, S.add_if_due, S._prev_house


def entry(self, book, obs, frame, day, now):
    before = book.next_id
    _prev_entry(self, book, obs, frame, day, now)
    if book.next_id == before:
        return
    leg = book.open[before]
    target = RUN["lots"] or leg.lots
    if RUN["half"] and leg.o30s_stretch is not None and leg.o30s_stretch >= A.GRID["stretch_limit"]:
        target = max(1, target // 2)
    per = leg.entry_premium * leg.lot_size * RUN["reserve"]
    room = book.equity - sum(x.entry_premium * x.qty for x in book.open.values() if x.id != leg.id)
    if target * per > room:
        target = int(room // per)
    if target < 1:
        del book.open[before]
        self.notes["exact_no_cash"] += 1
        return
    leg.lots, leg.initial_qty = target, target * leg.lot_size


def scaled_add(leg, fut, quote, plan, notes):
    base = leg.initial_qty // leg.lot_size
    if not _prev_add(leg, fut, quote, plan, notes):
        return False
    for _ in range(base - 1):
        leg.entry_premium = (leg.entry_premium * leg.lots + quote.ask) / (leg.lots + 1)
        leg.lots += 1
    return True


def house(self, leg, quote, obs, now):
    before = settings.FNO_MAX_LOTS
    settings.FNO_MAX_LOTS = 10_000
    try:
        for _ in range(leg.initial_qty // leg.lot_size):
            _prev_house(self, leg, quote, obs, now)
    finally:
        settings.FNO_MAX_LOTS = before


Y.BookReplay._entry, S.add_if_due, Y.BookReplay._house_money_add = entry, scaled_add, house


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("--name", required=True)
    cli.add_argument("--lots", type=int, default=0)
    cli.add_argument("--sizing", choices=["fixed", "shipped"], default="fixed")
    cli.add_argument("--half", action="store_true")
    cli.add_argument("--skip", action="store_true")
    a = cli.parse_args()
    reserve = 3 if "ADD2" in a.name else 2 if ("ADD1" in a.name or "HOUSE" in a.name) else 1
    RUN.update(lots=a.lots if a.sizing == "fixed" else 0, half=a.half, reserve=reserve)
    if a.sizing == "fixed":
        for k, v in {**S.RAW, "FNO_MAX_OPEN_PREMIUM_PCT": 1.0, "FNO_MAX_TRADES_PER_DAY": 3}.items():
            setattr(settings, k, v)
    O27F.deny_network()
    C.table("year")
    Y._worker_init()
    tag = f"exact|{a.sizing}|{a.lots}|{a.half}|{a.skip}"
    book = {**S.books()[a.name], "o30s": tag, **({"skip": T2.LIMIT} if a.skip else {})}
    _key, trades = Y.evaluate((book, "year", C.WINDOW))
    closed = [t for t in trades if t.get("net_pnl") is not None]
    run = peak = fall = fall_rs = 0.0
    equity = peak = A.CAPITAL
    daily: dict = {}
    for t in sorted(closed, key=lambda x: x["exit_time"]):
        equity += float(t["net_pnl"])
        peak = max(peak, equity)
        fall, fall_rs = max(fall, (peak - equity) / peak), max(fall_rs, peak - equity)
        daily[t["entry_time"][:10]] = daily.get(t["entry_time"][:10], 0.0) + float(t["net_pnl"])
    net = sum(float(t["net_pnl"]) for t in closed)
    stress = sum(A.STRESS * int(t.get("lots_at_exit") or 1) for t in closed)
    base, _sha = A.load()
    rule = ("fixed", a.lots) if a.sizing == "fixed" else ("risk", 0.02)
    brakes = "NONE" if a.sizing == "fixed" else "SHIPPED"
    rows_in = base[C.YEAR][a.name]
    if a.skip:
        raw = json.loads((LOCAL / f"results-t2-raw-{C.YEAR}.json").read_text(encoding="utf-8"))
        rows_in = A.prep(raw["trades"][raw["books"][f"{a.name}|skip"]])
    sim0 = A.sim(rows_in, rule, brakes, 0.0, a.half, reserve=reserve)
    sim1 = A.sim(rows_in, rule, brakes, A.STRESS, a.half, reserve=reserve)
    row = {"year": C.YEAR, "name": a.name, "sizing": a.sizing, "lots": a.lots, "half": a.half, "skip": a.skip, "trades": len(closed),
           "net": round(net), "net_plus_200": round(net - stress), "fall_pct": round(fall, 4), "fall_rs": round(fall_rs),
           "worst_day": round(min([0.0, *daily.values()])), "best_day": round(max([0.0, *daily.values()])),
           "best_day_date": max(daily, key=daily.get) if daily else None, "simulated_net": sim0["net"],
           "simulated_net_plus_200": sim1["net"], "simulated_trades": sim1["trades"]}
    target = HERE / "exact.json"
    rows = json.loads(target.read_text(encoding="utf-8")) if target.is_file() else []
    rows = [r for r in rows if not (r["year"] == row["year"] and r["name"] == row["name"] and r["sizing"] == row["sizing"]
                                    and r["lots"] == row["lots"] and r["half"] == row["half"]
                                    and r.get("skip", False) == row["skip"])] + [row]
    target.write_text(json.dumps(rows, indent=1), encoding="utf-8")
    print(json.dumps(row), flush=True)


if __name__ == "__main__":
    main()

"""EDGE overnight on the LIVE universe (Kite daily cache), with improvement arms.

Development evidence. The frozen study `edge-overnight-t1` tested about 95
Yahoo tickers; the live paper book scans every cached ticker in the price
band (~1,500), and 6 of its first 7 picks were never in the tested universe.
This replays the shipped `scan_today` ranking and the shipped overnight book
(`edge_portfolio_replay.run_overnight_book`, close +25 bps -> next open -5 bps,
1% participation cap, own cash, delivery costs) on that broad universe.

Usage: python backtest.py <ohlcv.sqlite> <tested_tickers.json> <start> <end> <out.json> [arm ...]
"""
from __future__ import annotations

import json
import os
import sqlite3
import statistics as st
import sys
import tempfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "python-engine"))

BAND = (4.0, 60.0)
RANK_DEPTH = 10

ARMS = {
    "LIVE_3":        {"max_positions": 3},
    "LIVE_2":        {"max_positions": 2},
    "LIVE_1":        {"max_positions": 1},
    "TESTED95_3":    {"max_positions": 3, "tested_only": True},
    "LIQ25L_3":      {"max_positions": 3, "min_traded_value": 2_500_000},
    "LIQ1CR_3":      {"max_positions": 3, "min_traded_value": 10_000_000},
    "NO_MR_MID_3":   {"max_positions": 3, "drop_kinds": ("MR_mid",)},
    "LIQ1CR_2":      {"max_positions": 2, "min_traded_value": 10_000_000},
    "LIQ25L_1":      {"max_positions": 1, "min_traded_value": 2_500_000},
    # Realistic fills: a close at the day's high after a >=2% rise is usually
    # locked at its upper band (no sellers), so it cannot be bought at the
    # close; a company is held once whatever its series (-BE/-EQ twins); SME
    # series (-SM/-ST) trade in large lots and are excluded.
    "REAL_3":        {"max_positions": 3, "realistic": True},
    "REAL_2":        {"max_positions": 2, "realistic": True},
    "REAL_1":        {"max_positions": 1, "realistic": True},
    "REAL_MO_3":     {"max_positions": 3, "realistic": True, "drop_kinds": ("MR_mid", "MR_strong", "MR_soft", "MO_mid")},
    "REAL_MR_3":     {"max_positions": 3, "realistic": True, "drop_kinds": ("MO_mid", "MO_strong", "MR_mid", "MR_soft")},
    "REAL_LIQ25L_3": {"max_positions": 3, "realistic": True, "min_traded_value": 2_500_000},
    "REAL_LIQ1CR_3": {"max_positions": 3, "realistic": True, "min_traded_value": 10_000_000},
    "REAL_TESTED95_3": {"max_positions": 3, "realistic": True, "tested_only": True},
    "REAL_NO_MR_MID_3": {"max_positions": 3, "realistic": True, "drop_kinds": ("MR_mid",)},
}


def base_symbol(ticker: str) -> str:
    return ticker.split("-")[0]


def is_sme(ticker: str) -> bool:
    return ticker.endswith(("-SM", "-ST"))


def load(path, start, end):
    con = sqlite3.connect(path)
    band = {t for (t,) in con.execute(
        "SELECT DISTINCT ticker FROM ohlcv_cache WHERE date BETWEEN ? AND ? AND close BETWEEN ? AND ?",
        (start, end, *BAND))}
    band.add("NIFTYBEES")
    marks = ",".join("?" * len(band))
    rows = con.execute(f"SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache WHERE ticker IN ({marks}) "
                       "AND date >= date(?, '-120 days') ORDER BY ticker,date", (*sorted(band), start)).fetchall()
    return rows


def traded_value_median(rows):
    """ticker -> {day: median close*volume of the 20 prior sessions}."""
    by = defaultdict(list)
    for t, d, o, h, l, c, v in rows:
        by[t].append((d, (c or 0) * (v or 0)))
    out = {}
    for t, seq in by.items():
        m = {}
        for i, (d, _) in enumerate(seq):
            prior = [x for _, x in seq[max(0, i - 20):i]]
            m[d] = st.median(prior) if len(prior) >= 10 else 0.0
        out[t] = m
    return out


def run_arm(args):
    name, spec, db_rows, tested, start, end, bankroll = args
    from edge_portfolio_replay import EdgeReplayConfig, run_overnight_book
    from daily_portfolio import DailySignal, bars_by_ticker, calendar_from
    from penny_edge_live import scan_today
    from edge_portfolio_replay import penny_cnc_costs

    rows = db_rows
    if spec.get("tested_only"):
        rows = [r for r in rows if r[0] in tested or r[0] == "NIFTYBEES"]
    bars = bars_by_ticker(rows)
    calendar = calendar_from(bars, "NIFTYBEES", start)
    tv = traded_value_median(rows) if spec.get("min_traded_value") else {}
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE ohlcv_cache (ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
    con.executemany("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)", rows)
    con.execute("CREATE INDEX i ON ohlcv_cache(ticker,date)")
    con.commit()
    con.close()
    refused = defaultdict(int)

    def signals(day, equity):
        scan = scan_today(bankroll=equity, max_positions=RANK_DEPTH, min_strength=0.45, db_path=path,
                          as_of_date=day, nifty_ticker="NIFTYBEES")
        out, bases = [], set()
        for cand in scan["positions"]:
            bar = bars[cand.ticker].get(day)
            if bar is None:
                continue
            if spec.get("realistic"):
                if is_sme(cand.ticker):
                    refused["sme"] += 1
                    continue
                if base_symbol(cand.ticker) in bases:
                    refused["duplicate_series"] += 1
                    continue
                prior = [d for d in bars[cand.ticker] if d < day]
                prev_close = bars[cand.ticker][max(prior)]["close"] if prior else None
                if (prev_close and bar["close"] >= bar["high"] * 0.999
                        and bar["close"] / prev_close - 1 >= 0.019):
                    refused["closed_at_high_up_unbuyable"] += 1
                    continue
                bases.add(base_symbol(cand.ticker))
            if cand.signal_subtype in spec.get("drop_kinds", ()):
                refused["kind"] += 1
                continue
            if spec.get("min_traded_value") and tv.get(cand.ticker, {}).get(day, 0.0) < spec["min_traded_value"]:
                refused["liquidity"] += 1
                continue
            out.append(DailySignal(cand.ticker, day, cand.entry_price, cand.stop_loss, cand.target, cand.shares,
                                   cand.signal_subtype, context={"strength": round(cand.adjusted_strength, 4)}))
        return out[: spec["max_positions"]]

    config = EdgeReplayConfig(tickers=tuple(sorted(bars)), bankroll=bankroll, max_positions=spec["max_positions"],
                              policy="EDGE_OVERNIGHT")
    try:
        result = run_overnight_book(bars, calendar, end=end, signals_at_close=signals, config=config,
                                    costs=penny_cnc_costs)
    finally:
        os.remove(path)
    trades = [t for t in result["trades"] if t["status"] == "CLOSED"]
    per = []
    for t in trades:
        notional = t["entry_price"] * t["shares"]
        close, opn = t["entry_price"] / 1.0025, t["exit_price"] / 0.9995
        per.append({"ticker": t["ticker"], "date": t["signal_date"], "kind": t["kind"], "net": t["net_pnl"],
                    "net_pct": t["net_pnl"] / notional, "notional": notional,
                    "placeholder_open": abs(opn / close - 1) < 1e-6, "tested": t["ticker"] in tested})
    return name, {"spec": spec, "summary": result["summary"], "admission": result["admission_outcomes"],
                  "refused": dict(refused), "trades": per}


def describe(name, res):
    s, per = res["summary"], res["trades"]
    if not per:
        return f"{name:13s} no trades"
    pct = [p["net_pct"] for p in per]
    ph = sum(p["placeholder_open"] for p in per)
    small = [p["net_pct"] for p in per if p["notional"] < 10000]
    return (f"{name:13s} n={len(per):4d} net=Rs{s['net_pnl']:>10,.0f} exbest=Rs{s['net_excluding_best_winner']:>10,.0f} "
            f"DDpk={s.get('max_marked_drawdown_pct', 0):6.1f}% win={s['win_rate_pct']:.0f}% "
            f"mean={100 * st.mean(pct):+.2f}% median={100 * st.median(pct):+.2f}% placeholder={100 * ph / len(per):.0f}% "
            f"under10k={len(small)}({100 * st.mean(small) if small else 0:+.2f}%)")


def main():
    db, tested_path, start, end, out = sys.argv[1:6]
    names = sys.argv[6:] or list(ARMS)
    tested = set(json.load(open(tested_path)))
    rows = load(db, start, end)
    with ProcessPoolExecutor(max_workers=min(4, len(names))) as pool:
        results = dict(pool.map(run_arm, [(n, ARMS[n], rows, tested, start, end, 25000.0) for n in names]))
    for n in names:
        print(describe(n, results[n]), flush=True)
    json.dump(results, open(out, "w"), indent=1, default=str)


if __name__ == "__main__":
    main()

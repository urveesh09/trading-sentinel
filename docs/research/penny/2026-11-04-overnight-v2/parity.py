"""Parity: the fast lab must reproduce the shipped replay exactly before any arm is read.

Reference = shipped penny_edge_live.scan_today on a temporary cache copy (as the
Oct 7 live-universe study ran it) feeding edge_portfolio_replay.run_overnight_book
(split_cash=True, refuse=runtime_realism_refusal, penny_cnc_costs, close +25 bp,
open -5 bp). Lab = lab.build_days + lab.run_book(Arm("BASE")).
Usage: python parity.py <start> <end>
"""
from __future__ import annotations
import json, os, sqlite3, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab  # noqa: E402
from daily_portfolio import DailySignal, bars_by_ticker, calendar_from, penny_cnc_costs  # noqa: E402
from edge_portfolio_replay import EdgeReplayConfig, run_overnight_book, runtime_realism_refusal  # noqa: E402
from penny_edge_live import scan_today  # noqa: E402
from penny_risk import calc_penny_costs  # noqa: E402


def main(start, end):
    bars, nifty = lab.load_panel("kite", start, end)
    rows = [(t, b["date"], b["open"], b["high"], b["low"], b["close"], b["volume"]) for t, tb in bars.items() for b in tb]
    rows += [("NIFTYBEES", r["date"], r["close"], r["close"], r["close"], r["close"], 1.0) for r in nifty]
    fd, path = tempfile.mkstemp(suffix=".sqlite"); os.close(fd)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE ohlcv_cache (ticker TEXT,date TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
    con.executemany("INSERT INTO ohlcv_cache VALUES (?,?,?,?,?,?,?)", rows)
    con.execute("CREATE INDEX i ON ohlcv_cache(ticker,date)"); con.commit(); con.close()
    rb = bars_by_ticker(rows)
    cal = calendar_from(rb, "NIFTYBEES", start)

    def signals(day, equity):
        scan = scan_today(bankroll=equity, max_positions=lab.RANK_DEPTH, min_strength=lab.MIN_STRENGTH,
                          db_path=path, as_of_date=day, nifty_ticker="NIFTYBEES")
        return [DailySignal(c.ticker, day, c.entry_price, c.stop_loss, c.target, c.shares, c.signal_subtype,
                            context={}) for c in scan["positions"]]
    cfg = EdgeReplayConfig(tickers=tuple(sorted(rb)), bankroll=25000.0, max_positions=3,
                           policy="EDGE_OVERNIGHT_RUNTIME", slippage_bps=5.0, overnight_entry_slippage_bps=25.0)
    try:
        ref = run_overnight_book(rb, cal, end=end, signals_at_close=signals, config=cfg, costs=penny_cnc_costs,
                                 refuse=runtime_realism_refusal(rb), split_cash=True)
    finally:
        os.remove(path)
    days = lab.build_days(bars, nifty, start, lab_end(nifty, end))
    mine = lab.run_book(days, lab.Arm("BASE"), start=start, end=end)
    rt = sorted((t["ticker"], t["signal_date"], t["shares"], round(t["net_pnl"], 4))
                for t in ref["trades"] if t["status"] == "CLOSED")
    mt = sorted((t["ticker"], t["entry_date"], t["shares"], round(t["net"], 4)) for t in mine["trades"])
    # cost arithmetic identity on 200 random-ish cases
    cost_mismatch = sum(abs(lab.cnc_costs(e, x, q) - calc_penny_costs(e, x, q, is_intraday=False)) > 1e-6
                        for e in (4.1, 7.77, 13.2, 55.0) for x in (3.9, 8.0, 13.0, 60.1) for q in (1, 17, 333, 2500))
    diff = sorted(set(rt) ^ set(mt), key=lambda x: (x[1], x[0]))
    out = {"window": [start, end], "ref_closed": len(rt), "lab_closed": len(mt), "mismatches": len(diff),
           "first_diffs": diff[:10], "ref_net": round(sum(x[3] for x in rt), 4),
           "lab_net": round(sum(x[3] for x in mt), 4), "cost_mismatch": cost_mismatch,
           "ref_outcomes": ref["admission_outcomes"], "lab_outcomes": mine["outcomes"]}
    print(json.dumps(out, indent=1))
    (HERE / f"parity-{start}-{end}.json").write_text(json.dumps(out, indent=1))


def lab_end(nifty, end):
    later = [r["date"] for r in nifty if r["date"] > end]
    return later[2] if len(later) > 2 else end


if __name__ == "__main__":
    main(*sys.argv[1:3])

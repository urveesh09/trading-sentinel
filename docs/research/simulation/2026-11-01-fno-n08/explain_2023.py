"""Why 2023 went as it did, after the frozen verdict: nothing here changes a book or a verdict. Writes explain-2023.json."""
import json
import sqlite3
import statistics
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
YEARS = ("2023", "2024", "2025", "2026")
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
DB = Path.home() / "sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"


def evals(year):
    return HERE / "_local" / ("evals-2023" if year == "2023" else "evals")


def load(year, action):
    keys = json.loads((HERE / "_local" / f"keys-{action}-{year}.json").read_text())
    return {n: json.loads((evals(year) / f"{k}.json").read_text()) for n, k in keys.items()}


def fall(trades, start=250000.0):
    equity = peak = start
    worst = 0.0
    for t in sorted(trades, key=lambda t: t["exit_time"]):
        equity += t["net_pnl"]
        peak = max(peak, equity)
        worst = max(worst, (peak - equity) / peak)
    return round(100 * worst, 2)


def daily_table():
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True, timeout=10)
    rows = con.execute("SELECT substr(datetime,1,10), open, high, low, close FROM candles WHERE kind='daily' AND underlying='NIFTY' ORDER BY 1").fetchall()
    con.close()
    atr, out, prev = None, {}, None
    for day, o, h, l, c in rows:
        tr = h - l if prev is None else max(h - l, abs(h - prev), abs(l - prev))
        atr = tr if atr is None else (atr * 13 + tr) / 14
        if prev is not None:
            out[day] = {"atr_pct_yesterday": out_prev, "range_pct": 100 * (h - l) / prev, "close": c}
        out_prev = 100 * atr / c
        prev = c
    return out


daily = daily_table()
result = {"years": {}}
print(f"{'year':6}{'index':>8}{'ATR%':>7}{'range%':>8} | {'trades':>6}{'win%':>6}{'gross+%':>8}{'net':>9}{'fall%':>7}{'prem':>7}{'stopPts':>8}{'cost/R%':>8}{'avgW':>7}{'avgL':>7} | {'N08 net':>8}{'N08 fall':>9} | {'random median':>13}{'best':>9}{'worst':>9}")
for y in YEARS:
    days = {d: v for d, v in daily.items() if d[:4] == y}
    closes = [v["close"] for d, v in sorted(days.items())]
    idx = 100 * (closes[-1] / closes[0] - 1)
    atr = statistics.median(v["atr_pct_yesterday"] for v in days.values())
    rng = statistics.median(v["range_pct"] for v in days.values())
    nb = load(y, "nobrake")
    n07 = nb["NOBRAKE|N07"]["trades"]
    n08 = nb["NOBRAKE|N08"]["trades"]
    wins = [t["net_pnl"] for t in n07 if t["net_pnl"] > 0]
    losses = [t["net_pnl"] for t in n07 if t["net_pnl"] <= 0]
    gross_pos = sum(t["gross_pnl"] > 0 for t in n07)
    prem = statistics.median(t["entry_premium"] for t in n07)
    stop = statistics.median(abs(t["entry_underlying"] - t["initial_stop_underlying"]) for t in n07)
    cost = statistics.median((t["gross_pnl"] - t["net_pnl"]) / (t["entry_premium"] * 0.25 * t["entry_qty"]) for t in n07)
    rnd = load(y, "random")
    rnet = sorted(sum(t.get("net_pnl", 0) - 200 for t in e["trades"] if t.get("net_pnl") is not None) for e in rnd.values())
    row = {"index_change_pct": round(idx, 1), "median_atr_pct": round(atr, 2), "median_range_pct": round(rng, 2), "n07_nobrake": {"trades": len(n07), "win_pct": round(100 * len(wins) / len(n07)), "gross_positive_pct": round(100 * gross_pos / len(n07)),
           "net": round(sum(t["net_pnl"] for t in n07)), "fall_pct": fall(n07), "median_premium": round(prem, 1), "median_stop_points": round(stop, 1), "median_cost_share_of_R_pct": round(100 * cost),
           "avg_win": round(sum(wins) / max(1, len(wins))), "avg_loss": round(sum(losses) / max(1, len(losses)))},
           "n08_nobrake": {"net": round(sum(t["net_pnl"] for t in n08)), "fall_pct": fall(n08), "trades": len(n08), "win_pct": round(100 * sum(t["net_pnl"] > 0 for t in n08) / len(n08))},
           "all_nobrake": {n.split("|")[1]: round(sum(t["net_pnl"] for t in e["trades"])) for n, e in nb.items()},
           "random_one_lot_after_200": {"median": round(rnet[len(rnet) // 2]), "best": round(rnet[-1]), "worst": round(rnet[0]), "positive": sum(v > 0 for v in rnet), "books": len(rnet)}}
    result["years"][y] = row
    a = row["n07_nobrake"]
    r = row["random_one_lot_after_200"]
    print(f"{y:6}{idx:>7.1f}%{atr:>7.2f}{rng:>8.2f} | {a['trades']:>6}{a['win_pct']:>6}{a['gross_positive_pct']:>8}{a['net']:>9}{a['fall_pct']:>7}{a['median_premium']:>7}{a['median_stop_points']:>8}{a['median_cost_share_of_R_pct']:>8}{a['avg_win']:>7}{a['avg_loss']:>7} | {row['n08_nobrake']['net']:>8}{row['n08_nobrake']['fall_pct']:>9} | {r['median']:>13}{r['best']:>9}{r['worst']:>9}")
print("\nAll books, brakes off:")
for y in YEARS:
    print(" ", y, result["years"][y]["all_nobrake"])

print("\nN07, brakes off, by yesterday's daily ATR as % of the index (known before the session):")
bands = ((0, .7), (.7, .85), (.85, 1.0), (1.0, 1.25), (1.25, 9))
table = {}
all_n07 = {y: load(y, "nobrake")["NOBRAKE|N07"]["trades"] for y in YEARS}
all_n08 = {y: load(y, "nobrake")["NOBRAKE|N08"]["trades"] for y in YEARS}
for lo, hi in bands:
    label = f"{lo}-{hi}%"
    row = {}
    for y in YEARS:
        ts = [t for t in all_n07[y] if lo <= daily.get(t["entry_time"][:10], {}).get("atr_pct_yesterday", 99) < hi]
        sess = sum(lo <= v["atr_pct_yesterday"] < hi for d, v in daily.items() if d[:4] == y)
        row[y] = {"sessions": sess, "trades": len(ts), "wins": sum(t["net_pnl"] > 0 for t in ts), "net": round(sum(t["net_pnl"] for t in ts))}
    table[label] = row
    print(f"  {label:10}", "  ".join(f"{y}: {row[y]['sessions']:>3}d {row[y]['trades']:>3}t {row[y]['net']:>8}" for y in YEARS), f"  total {sum(row[y]['net'] for y in YEARS):>8}")
result["atr_bands_n07"] = table
table8 = {}
for lo, hi in bands:
    label = f"{lo}-{hi}%"
    row = {}
    for y in YEARS:
        ts = [t for t in all_n08[y] if lo <= daily.get(t["entry_time"][:10], {}).get("atr_pct_yesterday", 99) < hi]
        row[y] = {"trades": len(ts), "wins": sum(t["net_pnl"] > 0 for t in ts), "net": round(sum(t["net_pnl"] for t in ts))}
    table8[label] = row
    print(f"  N08 {label:10}", "  ".join(f"{y}: {row[y]['trades']:>3}t {row[y]['net']:>8}" for y in YEARS), f"  total {sum(row[y]['net'] for y in YEARS):>8}")
result["atr_bands_n08"] = table8

print("\nOne account across the years, brakes on, from Rs 2.5 lakh:")
carry = {}
for name in ("N03", "N04", "N05", "N07", "N08"):
    trades, by_year = [], {}
    for y in YEARS:
        keys = json.loads((HERE / "_local" / f"keys-carry-{y}.json").read_text())
        ts = json.loads((HERE / "_local" / "evals-carry" / f"{keys[name]}.json").read_text())["trades"]
        trades += ts
        by_year[y] = {"trades": len(ts), "net": round(sum(t["net_pnl"] for t in ts))}
    last = max((t["exit_time"] for t in trades), default=None)
    carry[name] = {"by_year": by_year, "end": round(250000 + sum(t["net_pnl"] for t in trades)), "last_trade": last[:10] if last else None}
    print(" ", name, carry[name])
result["one_account"] = carry

print("\nA 2023-style start at one lot, on the real-money test's terms (no brake but the Rs 7,000 floor):")
one = json.loads((evals("2023") / f"{json.loads((HERE / '_local' / 'keys-exam-2023-v2.json').read_text())['ONE|WL']}.json").read_text())["trades"]
one07 = json.loads((evals("2023") / f"{json.loads((HERE / '_local' / 'keys-exam-2023-v2.json').read_text())['ONE|N07']}.json").read_text())["trades"]
start = {}
for name, ts in (("N07 at one lot", one07), ("N08's one-lot parts", one)):
    for capital in (12500, 15000):
        cash = capital
        hit = None
        n = 0
        for t in sorted(ts, key=lambda t: t["exit_time"]):
            cash += t["net_pnl"]
            n += 1
            if cash < 7000:
                hit = (t["exit_time"][:10], n)
                break
        start[f"{name} from {capital}"] = {"below_7000_on": hit[0] if hit else None, "after_trades": hit[1] if hit else None, "end_cash": round(cash)}
        print(" ", name, capital, start[f"{name} from {capital}"])
result["one_lot_2023_start"] = start
(HERE / "explain-2023.json").write_text(json.dumps(result, indent=1), encoding="utf-8")

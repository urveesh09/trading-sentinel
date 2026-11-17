"""SN484: a slower, cash-funded NIFTY trend benchmark (PLAN.md SN484, frozen at bf895633; details fixed here before any number).

Data: NIFTYBEES.NS daily (Yahoo chart API, fetched once with a generic client into the scratchpad, sha256 recorded): close
(split-adjusted traded close) for trades, adjclose (dividends folded in) as the total-return proxy for the signal (no NIFTY 50 TRI
series was fetched), dividend events credited as cash on their dates.
TREND: at each month's last session, hold NIFTYBEES for the next month if adjclose / adjclose 12 months earlier - 1 > 0, else cash;
orders at the next session's close. BUY_HOLD: buy at the first session's close. CASH. Cash yields 0% (primary) or 5% a year
(sensitivity, accrued daily by calendar days). Whole shares. Costs (Zerodha delivery, as frozen): brokerage 0, STT 0.1% each side,
stamp 0.015% on buys, exchange 0.00297%, SEBI 0.0001%, GST 18% on exchange + SEBI, DP Rs 15.34 + GST a sell day, spread 0.05% a side.
Funding: (a) Rs 30,000 at the window's first session; (b) the same plus Gold v5's own refills (GOLD_30K 2023-26 @205, each losing
day's loss deposited on that date: Gold's capital ledger) for the 2023 - Oct 2026 window; deposits are invested at the next close
(BUY_HOLD; TREND when holding).
Windows: 2010-01 (first full signal) - 2026-10-28; 2020-01 - 2026-10-28; 2022-01 - 2026-10-28; 2023-01 - 2026-10-28.
Reported: final value, contributions, spendable P&L (final - contributions), CAGR (lump-sum windows), max drawdown (% of value and Rs),
months invested, trades, costs paid. PASS (per window, primary): TREND's CAGR > CASH's and TREND's CAGR / max-drawdown% > BUY_HOLD's.
Gold v5's own net over the matching dates (2022, 2023-26 replays) is printed beside it for scale (different risk, not paired).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
OUT = HERE / "results-sn484.json"
SRC = Path(r"C:\Users\Urveesh\AppData\Local\Temp\claude\f191b6166a36c84a\b7c0aa9b-c954-4f08-9df8-57422081ea0c\scratchpad\dl\etf\NIFTYBEES.NS.json")
END = "2026-10-28"
STT, STAMP, EXCH, SEBI, GST, DP, SPREAD = 0.001, 0.00015, 0.0000297, 0.000001, 0.18, 15.34 * 1.18, 0.0005


def load():
    blob = SRC.read_bytes()
    r = json.loads(blob)["chart"]["result"][0]
    ts = r["timestamp"]
    close = r["indicators"]["quote"][0]["close"]
    adj = r["indicators"]["adjclose"][0]["adjclose"]
    rows = []
    for t, c, a in zip(ts, close, adj):
        if c is None or a is None:
            continue
        d = dt.datetime.fromtimestamp(t, dt.timezone(dt.timedelta(hours=5, minutes=30))).date().isoformat()
        rows.append((d, float(c), float(a)))
    rows = sorted({d: (d, c, a) for d, c, a in rows}.values())
    divs = {}
    for ev in (r.get("events") or {}).get("dividends", {}).values():
        d = dt.datetime.fromtimestamp(ev["date"], dt.timezone(dt.timedelta(hours=5, minutes=30))).date().isoformat()
        divs[d] = divs.get(d, 0.0) + float(ev["amount"])
    return rows, divs, hashlib.sha256(blob).hexdigest()


def buy_cost(v):
    return v * (STT + STAMP + EXCH + SEBI) + v * (EXCH + SEBI) * GST


def sell_cost(v):
    return v * (STT + EXCH + SEBI) + v * (EXCH + SEBI) * GST + DP


def signals(rows):
    """date of month-end -> hold next month (bool), from adjclose 12 months earlier (the last session of that month)."""
    me = {}
    for d, _c, a in rows:
        me[d[:7]] = (d, a)
    keys = sorted(me)
    out = {}
    for k, m in enumerate(keys):
        if k >= 12:
            out[me[m][0]] = me[m][1] / me[keys[k - 12]][1] - 1 > 0
    return out


def sim(rows, divs, kind, start, deposits=None, yield_pa=0.0):
    deposits = dict(deposits or {})
    sig = signals(rows)
    days = [r for r in rows if start <= r[0] <= END]
    cash, shares, contrib, costs, trades = 0.0, 0, 0.0, 0.0, 0
    hold = kind == "BUY_HOLD"
    pending_trade = "BUY" if kind in ("BUY_HOLD",) else None
    if kind == "TREND":
        prior = [d for d in sig if d < days[0][0]]
        hold = bool(prior) and sig[max(prior)]
        pending_trade = "BUY" if hold else None
    peak, mdd_pct, mdd_rs, invested_days, prev = 0.0, 0.0, 0.0, 0, None
    for idx, (d, c, _a) in enumerate(days):
        if prev is not None and yield_pa:
            cash *= (1 + yield_pa) ** ((dt.date.fromisoformat(d) - dt.date.fromisoformat(prev)).days / 365.0)
        if idx == 0:
            cash += 30000.0
            contrib += 30000.0
        for dd in [x for x in list(deposits) if x < d]:          # a loss day's refill arrives for the next session
            cash += deposits.pop(dd)
        if shares and d in divs:
            cash += shares * divs[d]
        if pending_trade == "SELL" and shares:
            v = shares * c * (1 - SPREAD)
            fee = sell_cost(v)
            cash += v - fee
            costs += fee + shares * c * SPREAD
            shares, trades = 0, trades + 1
        if (pending_trade == "BUY" or (kind == "BUY_HOLD") or (kind == "TREND" and hold)) and kind != "CASH":
            px = c * (1 + SPREAD)
            n = int(cash // (px * (1 + STT + STAMP + EXCH * (1 + GST) + SEBI * (1 + GST))))
            while n > 0 and n * px + buy_cost(n * c) > cash:
                n -= 1
            if n > 0:
                fee = buy_cost(n * c)
                cash -= n * px + fee
                costs += fee + n * c * SPREAD
                shares += n
                trades += 1
        pending_trade = None
        if kind == "TREND" and d in sig:
            want = sig[d]
            pending_trade = "BUY" if (want and not hold) else ("SELL" if (hold and not want) else None)
            hold = want
        value = cash + shares * c
        invested_days += shares > 0
        peak = max(peak, value)
        if peak > 0:
            mdd_pct = max(mdd_pct, (peak - value) / peak)
            mdd_rs = max(mdd_rs, peak - value)
        prev = d
    final = cash + shares * days[-1][1] * (1 - SPREAD) - (sell_cost(shares * days[-1][1]) if shares else 0.0)
    return {"final": round(final), "spendable_pnl": round(final - contrib), "contributions": round(contrib), "max_drawdown_pct": round(100 * mdd_pct, 2),
            "max_drawdown_rs": round(mdd_rs), "share_of_sessions_invested": round(invested_days / len(days), 3), "trades": trades, "costs": round(costs),
            "sessions": len(days), "first": days[0][0], "last": days[-1][0]}


def cagr(r):
    yrs = (dt.date.fromisoformat(r["last"]) - dt.date.fromisoformat(r["first"])).days / 365.25
    return round(100 * ((r["final"] / r["contributions"]) ** (1 / yrs) - 1), 2) if r["final"] > 0 else None


def gold_refills():
    import goldx
    goldx.install()
    days, _log, _ = goldx.gold.run(goldx.gold.Y2326, goldx.gold.DEPLOYED, 205.0)
    dep = {}
    for d, _w, n, _t, _l in days:
        if n < 0:
            dep[d] = dep.get(d, 0.0) - n
    return dep


def main():
    if OUT.exists():
        raise SystemExit("SN484 is scored once")
    rows, divs, sha = load()
    res = {"source": {"file": SRC.name, "sha256": sha, "sessions": len(rows), "first": rows[0][0], "last": rows[-1][0], "dividend_events": len(divs)}, "windows": {}}
    for wname, start in (("2010-2026", "2010-01-01"), ("2020-2026", "2020-01-01"), ("2022-2026", "2022-01-01"), ("2023-2026", "2023-01-01")):
        cell = {}
        for y in (0.0, 0.05):
            for kind in ("TREND", "BUY_HOLD", "CASH"):
                r = sim(rows, divs, kind, start, yield_pa=y)
                r["cagr_pct"] = cagr(r)
                cell[f"{kind} cash@{int(y * 100)}%"] = r
        t, b, c = cell["TREND cash@0%"], cell["BUY_HOLD cash@0%"], cell["CASH cash@0%"]
        ratio = lambda r: (r["cagr_pct"] or 0) / max(r["max_drawdown_pct"], 1e-9)  # noqa: E731
        cell["verdict_primary"] = "PASS" if ((t["cagr_pct"] or -99) > (c["cagr_pct"] or 0) and ratio(t) > ratio(b)) else "FAIL"
        cell["return_per_drawdown"] = {"TREND": round(ratio(t), 3), "BUY_HOLD": round(ratio(b), 3)}
        res["windows"][wname] = cell
    dep = gold_refills()
    res["gold_refills_2023_26"] = {"days": len(dep), "total": round(sum(dep.values()))}
    funded = {}
    for kind in ("TREND", "BUY_HOLD", "CASH"):
        r = sim(rows, divs, kind, "2023-01-01", deposits=dep)
        r["contributions"] = round(30000.0 + sum(dep.values()))
        r["spendable_pnl"] = r["final"] - r["contributions"]
        funded[kind] = r
    res["funded_like_gold_2023_26"] = funded
    res["gold_for_scale"] = {"2022 @205": -15281, "2023-2026 @205": 850883, "2023-2026 @400": 495597, "2020-21 @205 (SN482)": -64783,
                             "note": "Gold's net = sum of day nets with losses refilled (deposits 5,62,130 over 2023-26 @205); not a paired comparison"}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    for w, cell in res["windows"].items():
        print(w, cell["verdict_primary"], cell["return_per_drawdown"])
        for k, r in cell.items():
            if isinstance(r, dict) and "final" in r:
                print(f"   {k:20s} final {r['final']:>9} pnl {r['spendable_pnl']:>9} cagr {r['cagr_pct']} mdd {r['max_drawdown_pct']}% ({r['max_drawdown_rs']}) invested {r['share_of_sessions_invested']} trades {r['trades']} costs {r['costs']}")
    print("funded like Gold 2023-26:", {k: (v["final"], v["spendable_pnl"], v["max_drawdown_rs"]) for k, v in funded.items()}, res["gold_refills_2023_26"])


if __name__ == "__main__":
    main()

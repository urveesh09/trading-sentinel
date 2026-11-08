"""DEV only: the shipped entries under different exits (descriptive, before any freeze)."""
import sys
import pandas as pd
import lab, lab_data

EXITS = [lab.Exit("LIVE", live=True), lab.Exit("DEADLINE"), lab.Exit("T1.6", target_r=1.6),
         lab.Exit("BE1", breakeven_r=1.0), lab.Exit("RUNNER", breakeven_r=1.0, trail_bars=True),
         lab.Exit("VWAP", vwap_exit=True)]


def entries(data, shipped, selective):
    rows = shipped[shipped.selective] if selective else shipped
    for (ticker, day), group in rows.groupby(["ticker", "day"]):
        r = group.sort_values("bar").iloc[0]
        bars = data["bars"][(ticker, day)]
        j = int(r.bar) + 1
        if j >= len(bars) or bars.index[j].strftime("%H:%M") >= lab.DEADLINE:
            continue
        fill = float(bars["open"].iloc[j]) * (1 + lab.SLIP)
        if fill <= r.stop or fill >= r.target:
            continue
        qty = int(min(r.shares * (r.entry_ref - r.stop) / (fill - r.stop), lab.POOL / fill))
        if qty >= 1:
            yield ticker, day, bars, j, fill, r, qty


if __name__ == "__main__":
    window = sys.argv[1] if len(sys.argv) > 1 else "DEV"
    data = lab_data.load_dev() if window == "DEV" else lab_data.load_exam()
    shipped = pd.read_pickle(lab_data.LOCAL / f"{window.lower()}_shipped.pkl")
    for selective in (False, True):
        for rule in EXITS:
            trades = []
            for ticker, day, bars, j, fill, r, qty in entries(data, shipped, selective):
                t = lab.run_trade(bars, j, fill, r.stop, qty, rule, target_price=r.target, atr=r.atr, vwap_entry=r.vwap)
                if t:
                    trades.append({"day": day, "ticker": ticker, **t})
            s = lab.summary(trades)
            reasons = pd.Series([t["reason"] for t in trades]).value_counts().to_dict() if trades else {}
            print("SELECTIVE" if selective else "BASE", rule.name, s, reasons)

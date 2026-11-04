"""Build and pickle the per-session candidate tables. Usage: python build.py kite|yahoo"""
import json, sys, time
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab

SPANS = {"kite": ("2025-07-01", "2026-10-01"), "yahoo": ("2019-04-01", "2026-11-03")}

def main(src):
    t0 = time.time()
    start, end = SPANS[src]
    bars, nifty = lab.load_panel(src, start, end)
    if src == "yahoo":
        acq = json.loads((HERE / "_local/yahoo-acquisition.json").read_text())
        splits = {}
        for r in acq["receipts"]:
            ev = (r.get("corporate_actions") or {}).get("splits") or {}
            if ev:
                splits[r["symbol"]] = sorted(int(k) for k in ev)
        # Yahoo back-adjusts OHLC for splits: nominal price bands before a split
        # are not the traded prices. Drop each split ticker's history before its
        # last split (known from the corporate-action calendar, not outcomes).
        from datetime import datetime, timezone, timedelta
        cut = {}
        for s, stamps in splits.items():
            last = datetime.fromtimestamp(stamps[-1], timezone(timedelta(hours=5, minutes=30))).date().isoformat()
            cut[s] = last
        for s, last in cut.items():
            if s in bars:
                bars[s] = [b for b in bars[s] if b["date"] > last]
        bars = {t: tb for t, tb in bars.items() if len(tb) >= 22}
        (HERE / "_local/yahoo-split-cuts.json").write_text(json.dumps(cut, indent=1))
        # zero-volume Yahoo rows are not sessions for that ticker
        bars = {t: [b for b in tb if b["volume"] > 0] for t, tb in bars.items()}
    days = lab.build_days(bars, nifty, start, end)
    lab.save(days, HERE / f"_local/days-{src}.pkl")
    n = sum(len(d.cands) for d in days)
    print(src, len(bars), "tickers", len(days), "sessions", n, "candidates", f"{time.time()-t0:.0f}s", flush=True)

if __name__ == "__main__":
    main(sys.argv[1])

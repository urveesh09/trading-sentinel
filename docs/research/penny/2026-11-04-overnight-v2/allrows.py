"""All band rows (not only EDGE signals): causal features + next-open label, pickled per panel.
Usage: python allrows.py kite|yahoo"""
import sys, statistics as st, pickle, json
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab

def main(src):
    start, end = {"kite": ("2025-07-01", "2026-10-01"), "yahoo": ("2019-04-01", "2026-11-03")}[src]
    bars, nifty = lab.load_panel(src, start, end)
    if src == "yahoo":
        cut = json.loads((HERE / "_local/yahoo-split-cuts.json").read_text())
        bars = {t: [b for b in tb if b["date"] > cut.get(t, "") and b["volume"] > 0] for t, tb in bars.items()}
    cal = {r["date"] for r in nifty if start <= r["date"] <= end}
    rows = []
    for t, tb in bars.items():
        if t.endswith(("-SM", "-ST")):
            continue
        for i in range(21, len(tb) - 1):
            b = tb[i]
            if b["date"] not in cal or not 5 <= b["close"] <= 55:
                continue
            f = lab._causal_features(tb, i)
            n = tb[i + 1]
            rows.append((t, b["date"], f, n["open"] / b["close"] - 1, n["close"] / n["open"] - 1, n["open"] == b["close"]))
    with open(HERE / f"_local/allrows-{src}.pkl", "wb") as fh:
        pickle.dump(rows, fh, protocol=pickle.HIGHEST_PROTOCOL)
    print(src, len(rows))

if __name__ == "__main__":
    main(sys.argv[1])

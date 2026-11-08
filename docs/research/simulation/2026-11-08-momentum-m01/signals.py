"""Shipped Momentum signals (exact evaluator) for one window, cached in _local/<window>_shipped.pkl."""
import sys, time
from pathlib import Path
import pandas as pd
import lab, lab_data

if __name__ == "__main__":
    window = sys.argv[1]
    out = Path(lab_data.LOCAL) / f"{window.lower()}_shipped.pkl"
    data = lab_data.load_dev() if window == "DEV" else lab_data.load_exam()
    t = time.time()
    frame = lab.shipped_signals(data, workers=4)
    frame.to_pickle(out)
    print(window, len(frame), "accepted bars", frame.groupby(["ticker", "day"]).ngroups if len(frame) else 0,
          "ticker-days", int(frame["selective"].sum()) if len(frame) else 0, "selective bars", round(time.time() - t), "s")

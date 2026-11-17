"""SN429: does the trade still deserve its time? Checkpoint exits on Gold's own entries (PLAN.md section 1, frozen at
123301ac; details fixed here before any number). Learning only; no Gold change follows from this slot.

Through the stream only (gold.run's stream_filter cannot change minutes, so a stream transform is installed the same way
SN409 shifted minutes): for each N11 / R0.85 signal with entry minute i and N11 exit j, at checkpoint i + K:
  FIXED-K   exit at i + K whenever i + K < j (exit at one fixed checkpoint)
  CUT-K     exit at i + K only if the index has not moved in the trade's direction since entry (close[i + K] - close[i]
            signed by CE = +1 / PE = -1 is <= 0); otherwise hold to j (and Gold's own extension)
K = 30 / 60 / 90 minutes. Index closes from Gold's own session data (sn01 sessions, 2022 from SN366's dataset).
Paths 2023-26 (development) and 2022 (Gold's unseen year), Rs 205 / 400. Reported: net, worst month, trades cut, and from
the per-trade join with the deployed run (day, entry minute): losses saved, winners cut, the largest winner cut.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-17-sn411"))
import gold  # noqa: E402

OUT = HERE / "results-sn429.json"
P = gold.P
_orig = gold._orig_stream


def closes():
    gold.D.DATASETS["2022"] = gold.P.SN366L / "dataset-nifty-2022"
    gold.D.load_year = gold.G.load_2022
    out = {}
    for y in gold.Y2226:
        for d, s in gold.D.load_year(y)["sessions"].items():
            out[d] = s["index"][3]
    return out


def transform(rule, K, C):
    def stream(year, book="N11"):
        out = []
        for s in _orig(year, book):
            i, j = s["i"], s["j"]
            c = C.get(s["day"])
            if c is not None and i + K < j and i + K < len(c):
                d = 1 if s["opt"] == "CE" else -1
                if rule == "FIXED" or (c[i + K] - c[i]) * d <= 0:
                    s = {**s, "j": i + K, "cut": True}
            out.append(s)
        return out
    return stream


def main():
    if OUT.exists():
        raise SystemExit("SN429 is run once")
    C = closes()
    res = {}
    base = {}
    for p, years in (("2023-2026", gold.Y2326), ("2022", gold.Y22)):
        for st in (205.0, 400.0):
            days, log, _ = gold.run(years, gold.DEPLOYED, st)
            base[(p, st)] = {(x["day"], x["i"]): x["net"] for x in log}
            res[f"BASE | {p} @{int(st)}"] = gold.summary(days, log)
    assert res["BASE | 2023-2026 @205"]["net"] in (850882, 850883)
    for rule in ("FIXED", "CUT"):
        for K in (30, 60, 90):
            for p, years in (("2023-2026", gold.Y2326), ("2022", gold.Y22)):
                for st in (205.0, 400.0):
                    gold._orig_stream = transform(rule, K, C)
                    try:
                        days, log, _ = gold.run(years, gold.DEPLOYED, st)
                    finally:
                        gold._orig_stream = _orig
                    s = gold.summary(days, log)
                    b = base[(p, st)]
                    pairs = [(b[(x["day"], x["i"])], x["net"]) for x in log if (x["day"], x["i"]) in b]
                    changed = [(o, n) for o, n in pairs if abs(o - n) > 1]
                    s.update(changed_trades=len(changed), losses_saved=round(sum(n - o for o, n in changed if o < 0)),
                             winners_cut=sum(1 for o, n in changed if o > 0 and n < o), winner_give_up=round(sum(o - n for o, n in changed if o > 0 and n < o)),
                             largest_winner_cut=round(max([o for o, n in changed if o > 0 and n < o], default=0)))
                    res[f"{rule}-{K} | {p} @{int(st)}"] = s
                    print(rule, K, p, int(st), s["net"], s["worst_month"], s["changed_trades"], s["losses_saved"], s["winner_give_up"], flush=True)
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()

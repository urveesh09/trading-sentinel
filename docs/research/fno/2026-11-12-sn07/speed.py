"""SN07b speed test: N11 entries taken 1 minute earlier = at the closing minute of the 5-minute bar (zero delay). The 2-minute
shift buys BEFORE the bar is complete (look-ahead) and is kept only as an invalid row. Originally: entries 1 or 2 minutes earlier (the 5-minute bar is complete at its last minute's
close; the replay buys about two minutes after). Exits unchanged. Wallet as the benchmark (descriptive)."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "2026-11-12-sn03")]
import sn03 as B
out = {}
for y in B.YEARS:
    Y = B.Year(y)
    base = Y.sigs("N11")
    gaps = []
    for sigs in base.values():
        for s in sigs:
            bar_close = None
    for shift in (0, 1, 2):
        by = {d: [{**s, "i": s["i"] - shift, "sig_key": (s["sig_key"], shift)} for s in v] for d, v in base.items()}
        Y.streams[f"shift{shift}"] = by
        out.setdefault(f"enter {shift} min earlier", {})[y] = B.year_result(Y, {}, books=(f"shift{shift}",))
for k, per in out.items():
    print(f"{k:22s}", {y: per[y]["net"] for y in B.YEARS}, "total", sum(per[y]["net"] for y in B.YEARS),
          "won/lost/none", sum(per[y]["green"] for y in B.YEARS), sum(per[y]["red"] for y in B.YEARS), sum(per[y]["none"] for y in B.YEARS))
(HERE / "results-speed.json").write_text(json.dumps(out, indent=1), encoding="utf-8")

"""SN09b (after the verdict): OI writer flow as a confirmation filter on N11's own trades; leave one year out.
A trade is skipped when the flow at its entry minute opposes its direction by more than thr (mode 'oppose'), or kept
only when the flow agrees by at least thr (mode 'agree'). Wallet as the benchmark."""
import itertools, json, sys
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn09 as Z
B = Z.B
sys.path.insert(0, str(HERE.parent / "2026-11-12-sn03")); from sn03_run import loyo
GRID = [None] + [(k, w, mode, thr) for k, w, mode, thr in itertools.product((6, 15, 30), (150, 300), ("oppose", "agree"), (0.0, 0.005, 0.01, 0.02))]
table = {}
for y in Z.YEARS:
    Y = B.Year(y); n11 = Y.sigs("N11"); oi = Z.O.load(y)
    for S in Y.ordered():
        S.oi = oi.get(S.day, {})
    for cfg in GRID:
        name = "benchmark" if cfg is None else f"k{cfg[0]} w{cfg[1]} {cfg[2]} {cfg[3]}"
        nets = []
        for S in Y.ordered():
            sigs = n11.get(S.day, [])
            if cfg is not None and sigs:
                k, w, mode, thr = cfg
                K, CE, PE, mask = Z.oi_mats(S, w)
                keep = []
                for s in sigs:
                    i = s["i"]
                    if i < k:
                        continue
                    m = mask[:, i]
                    d_pe = (PE[m, i] - PE[m, i - k]).sum(); d_ce = (CE[m, i] - CE[m, i - k]).sum()
                    tot = (PE[m, i - k] + CE[m, i - k]).sum()
                    flow = (d_pe - d_ce) / tot if tot > 0 else 0.0
                    agree = flow * (1 if s["opt"] == "CE" else -1)
                    ok = agree >= -thr if mode == "oppose" else agree >= thr
                    if ok:
                        keep.append(s)
                sigs = keep
            nets.append(B.play_day(S, sigs, {}, 15000.0, 3000.0)["net"])
        table.setdefault(name, {})[y] = {"net": round(sum(nets)), "green": sum(x > 0 for x in nets), "red": sum(x < 0 for x in nets),
                                         "none": sum(x == 0 for x in nets), "refilled": round(sum(-x for x in nets if x < 0))}
L = loyo(table, "profit")
top = sorted(table.items(), key=lambda kv: -sum(v["net"] for v in kv[1].values()))[:6]
for n, per in top:
    print(f"{n:24s}", [per[y]["net"] for y in Z.YEARS], sum(per[y]["net"] for y in Z.YEARS), "won/lost", sum(per[y]["green"] for y in Z.YEARS), sum(per[y]["red"] for y in Z.YEARS))
print("LOYO", {y: (L[y]["pick"], L[y]["net"]) for y in Z.YEARS}, "sum", L["sum"])
(HERE / "results-confirm.json").write_text(json.dumps({"table": table, "loyo": L}, indent=1), encoding="utf-8")

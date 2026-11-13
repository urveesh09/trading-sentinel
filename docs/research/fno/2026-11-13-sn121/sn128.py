"""SN128 - the morning implied-volatility crush without overnight risk (PLAN.md): sell at 09:16 or 09:20 the iron fly or
condor (as SN124), buy back at 09:45 or 10:15; all days (primary) and Gold-free; control 12:00 -> 12:30 same structure."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pg  # noqa: E402
import sn124  # noqa: E402

C = pg.C
ENTRIES = {"09:16": 1, "09:20": 5}
EXITS = {"09:45": 30, "10:15": 60}


if __name__ == "__main__":
    out_path = HERE / "results-sn128.json"
    if out_path.exists():
        raise SystemExit("SN128 is scored once")
    sessions = pg.all_sessions()
    res = {}
    for dname, ok in (("all days", lambda d: True), ("gold-free", C.gold_free)):
        out = {}
        for sname, st in (("strict", 205.0), ("house", 100.0)):
            raw = {(k, en, ex): {S.day: sn124.short_trade(S, i, S, j, k, st) for S in sessions if ok(S.day)}
                   for k, (en, i), (ex, j) in itertools.product(sn124.STRUCTS, ENTRIES.items(), EXITS.items())}
            ctl = {k: {S.day: sn124.short_trade(S, 165, S, 195, k, st) for S in sessions if ok(S.day)} for k in sn124.STRUCTS}
            tab = {f"{k} {en}->{ex}": sn124.table(v, 15000.0) for (k, en, ex), v in raw.items()}
            Lr = C.loyo(tab, "profit")
            summ = {f"{k} {en}->{ex}": sn124.summarize(v) for (k, en, ex), v in raw.items()}
            out[sname] = {"tables": tab, "loyo": Lr, "summaries": summ, "midday_control": {k: sn124.summarize(v) for k, v in ctl.items()},
                          "_raw": raw}
            print(f"=== SN128 {dname} [{sname}]")
            for k, s in summ.items():
                print(f"   {k:20s}", [tab[k][y]["net"] for y in C.YEARS], s, flush=True)
            print("   midday control", out[sname]["midday_control"], "| LOYO", {y: (Lr[y]["pick"], Lr[y]["net"]) for y in C.YEARS}, "sum", Lr["sum"]["net"], flush=True)
        L_ = out["strict"]["loyo"]
        held_days = {}
        for y in C.YEARS:
            k, rest = L_[y]["pick"].split(" ", 1)
            en, ex = rest.split("->")
            for d, r in out["strict"]["_raw"][(k, en, ex)].items():
                if d[:4] == y and r is not None and r[1] <= 15000.0:
                    held_days[d] = r[0]
        xs = sorted(held_days.values(), reverse=True)
        ctl_best = max(v["total"] for v in out["strict"]["midday_control"].values())
        held = [L_[y]["net"] for y in C.YEARS]
        verdict = {"held_out_strict": L_["sum"]["net"], "held_out_house": out["house"]["loyo"]["sum"]["net"], "years": held,
                   "without_best_5": round(sum(xs[5:])), "worst": round(min(xs)) if xs else 0, "midday_control_best": ctl_best}
        verdict["PASS"] = bool(verdict["held_out_strict"] > 0 and verdict["held_out_house"] > 0 and sum(x > 0 for x in held) >= 3
                               and verdict["without_best_5"] > 0 and verdict["held_out_strict"] > ctl_best)
        for s in out.values():
            s.pop("_raw")
        res[dname] = {**out, "verdict": verdict, "heldout_day_nets": held_days}
        print("VERDICT", dname, verdict, flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")

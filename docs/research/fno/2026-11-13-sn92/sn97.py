"""SN97 parts 2-3 (part 1, Gold sizing by futures volume, runs inside sn99.py; PLAN.md).
2. SN93's and SN94's rules confirmed by futures relative volume >= x at the entry minute (x 1.2 / 1.5): LOYO of the
   confirmed grid against the unconfirmed grid and a random side.
3. Events, description only: Gold v5 on RBI decision days (N012 round 31's dated list) and Union Budget days."""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
import sn93  # noqa: E402
import sn94  # noqa: E402

RBI = [r["date"] for r in json.loads((C.M.ROOT / "docs/research/simulation/2026-11-05-fno-n12/round31-calendar.json").read_text(encoding="utf-8"))]
BUDGET = ["2023-02-01", "2024-02-01", "2024-07-23", "2025-02-01", "2026-02-01"]


def confirmed(f, x):
    def g(S):
        got = f(S)
        if got is None:
            return None
        s, ext = got
        s = s.copy()
        for i in np.flatnonzero(s):
            r = C.rel_vol(S.day, int(i))
            if r is None or r < x:
                s[i] = 0
        return s, ext
    return g


def null(f):
    def g(S):
        got = f(S)
        if got is None:
            return None
        s, x = got
        return (s * (1 if random.Random(f"97|{S.day}").random() < 0.5 else -1)).astype(np.int8), x
    return g


def events():
    C.RECORD[0] = True
    C.TRADES.clear()
    C.run(C.V5, wallets=(C.STD_WALLETS[0],))
    C.RECORD[0] = False
    out = {}
    for name, days in (("RBI decision days", RBI), ("Union Budget days", BUDGET)):
        sess = [d for d in days if any(d in C.years()[y].sessions for y in C.YEARS)]
        tr = [t for t in C.TRADES if t["day"] in set(days)]
        out[name] = {"sessions_in_data": len(sess), "gold_trades": len(tr), "gold_net": round(sum(t["net"] for t in tr)),
                     "days": sorted({t["day"] for t in tr})}
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn97.json"
    if out_path.exists():
        raise SystemExit("SN97 is scored once")
    C.years()
    res = {}
    for name, real0, last in (("SN93 drift", sn93.grid(), sn93.LAST), ("SN94 failed break", None, sn94.LAST)):
        if real0 is None:
            import itertools
            real0 = {}
            for buf, W, retest, target in itertools.product((0.0, 0.5), (15, 30), (True, False), ("mid", "far")):
                real0[f"buf{buf} W{W} {'retest' if retest else 'direct'} {target}"] = (sn94.rule(buf, W, retest, target), sn94.EX)
        real = {f"{k} rv{x}": (confirmed(f, x), ex) for k, (f, ex) in real0.items() for x in (1.2, 1.5)}
        controls = {"unconfirmed": real0, "NULL random side": {k: (null(f), ex) for k, (f, ex) in real.items()}}
        r = C.contest(real, controls, max_trades=1, last_entry=last)
        C.show_contest(f"SN97 {name} + futures volume", r)
        res[name] = {k: v for k, v in r.items() if k != "by_year_cfg"}
    res["events"] = events()
    print("EVENTS", res["events"], flush=True)
    out_path.write_text(json.dumps(C.jsonable(res), indent=1), encoding="utf-8")

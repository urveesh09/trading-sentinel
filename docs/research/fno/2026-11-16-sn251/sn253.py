"""SN253 - seal the samples (PLAN.md): build SN01-format session caches for DEV / TEST (NIFTY Apr 2022 - Oct 2026) and
the two buyer exams, EXAM-N (NIFTY Oct 2020 - Mar 2022) and EXAM-S (SENSEX Oct 2024 - Apr 2026), from the sealed
read-only mirrors. Records counts, source hashes, ATM coverage and the ATM straddle's model spread only. No strategy
price is read into any result. Also checks gl.adx_table against SN06's daily.json (the same algorithm on the same bars)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gl  # noqa: E402


def coverage(smp):
    clocks = {"09:20": 5, "10:00": 45, "14:00": 285, "15:15": 360, "15:20": 365}
    have = {c: 0 for c in clocks}
    strikes, spreads = [], []
    for d in smp.days:
        s = smp.s[d]
        strikes.append(len({k for k, _o in s["options"]}))
        for c, i in clocks.items():
            K = gl.atm(smp, s, i)
            if gl.opx(s, K, "CE", i) is not None and gl.opx(s, K, "PE", i) is not None:
                have[c] += 1
        K = gl.atm(smp, s, 45)
        ce, pe = gl.opx(s, K, "CE", 45), gl.opx(s, K, "PE", 45)
        if ce and pe:
            spreads.append((gl.wk.ask(smp.mk, ce) - gl.wk.bid(smp.mk, ce) + gl.wk.ask(smp.mk, pe) - gl.wk.bid(smp.mk, pe)) * smp.mk["lot"])
    n = len(smp.days)
    return {"sessions": n, "first": smp.days[0], "last": smp.days[-1],
            "atm_both_legs_share": {c: round(v / n, 3) for c, v in have.items()},
            "strikes_median": int(np.median(strikes)), "atm_straddle_round_trip_spread_rs_median": round(float(np.median(spreads))),
            "years": {y: sum(d[:4] == y for d in smp.days) for y in sorted({d[:4] for d in smp.days})},
            "calendar_days": len(smp.cal), "daily_bars": len(smp.daily)}


if __name__ == "__main__":
    out_path = HERE / "results-sn253.json"
    if out_path.exists():
        raise SystemExit("SN253 is run once")
    res = {"sources": {}, "samples": {}}
    for name, cfg in gl.SRC.items():
        res["sources"][name] = {k: {Path(p).name: gl.sha(p)} for k in ("option", "index", "future") for p in cfg[k]}
    for p in list(gl.wk.DEV_SOURCES.values()):
        res["sources"].setdefault("DEV", {})[str(Path(p).relative_to(gl.ROOT))] = gl.sha(p)
    for name in ("DEV", "TEST"):
        res["samples"][name] = coverage(gl.sample(name))
        print("SN253", name, json.dumps(res["samples"][name]), flush=True)
    for name in ("EXAMN", "EXAMS"):
        gl.SEALED[name] = True                  # built and counted only; no strategy reads it here
        res["samples"][name] = coverage(gl.sample(name))
        gl.SEALED[name] = False
        print("SN253", name, json.dumps(res["samples"][name]), flush=True)
    # ADX parity: the algorithm on 2023+ bars only (SN06's YEARS) against daily.json
    dev = gl.sample("DEV")
    sub = gl.Sample("DEV", {"inst": "NIFTY", "sessions": {}, "daily": {d: b for d, b in dev.daily.items() if d >= "2023-01-01"},
                            "cal": [d for d in dev.cal if d >= "2023-01-01"]})
    sub.name = "ADXCHECK"
    mine = gl.adx_table(sub)
    off = json.loads(gl.ADX_FILE.read_text(encoding="utf-8"))
    common = sorted(set(mine) & set(off))
    diff = max(abs(mine[d]["adx"] - off[d]["adx"]) for d in common)
    res["adx_parity"] = {"days": len(common), "max_abs_diff": round(diff, 4), "dir_mismatch": sum(mine[d]["dir"] != off[d]["dir"] for d in common)}
    print("SN253 ADX parity", res["adx_parity"], flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")

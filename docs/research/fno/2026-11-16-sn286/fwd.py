"""SN289-SN300 forward runner and verdict (PLAN.md; frozen before the window starts on Nov 17, 2026).

  python fwd.py collect            copy every recorded day folder from the Production engine container (read-only
                                   there) into _local/ticks/<day>, for days >= 2026-11-17 not yet copied; run each once
                                   (fw.run) and save _local/forward/<day>.json. Run at least every 30 days (the recorder
                                   keeps 35); it never prints P&L.
  python fwd.py verdict            once 20 qualified sessions exist: SN300's verdict on the first 20, with Gold gap days
                                   read from Production's sn_gold_positions (read-only); writes results-sn300.json once.

The window: the first 20 sessions dated >= 2026-11-17 whose SN289 qualification passes (NIFTY option expiry days are
skipped by rule). Pass (each of SN291's candidate and SN293's candidate): net > 0 at Rs 205 and Rs 400; beats its
control at Rs 205; positive without its best session; >= 30 trades on >= 10 sessions; the gap-session subset > 0.
Otherwise FAIL, or INSUFFICIENT when trades / sessions miss the counts. No reruns, no threshold change."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fw  # noqa: E402

TICKS = HERE / "_local" / "ticks"
FWD = HERE / "_local" / "forward"
START = "2026-11-17"
N_SESSIONS = 20
CONTAINER = "python-engine"


def recorded_days():
    r = subprocess.run(["docker", "exec", "-u", "quantuser", CONTAINER, "sh", "-c", "ls /data/research/ticks"],
                       capture_output=True, text=True, check=True)
    return sorted(x for x in r.stdout.split() if len(x) == 10 and x >= START)


def collect():
    FWD.mkdir(parents=True, exist_ok=True)
    TICKS.mkdir(parents=True, exist_ok=True)
    for d in recorded_days():
        if (FWD / f"{d}.json").exists():
            continue
        dst = TICKS / d
        if not dst.exists():
            subprocess.run(["docker", "cp", f"{CONTAINER}:/data/research/ticks/{d}", str(dst)], check=True)
        res = fw.run(dst)
        (FWD / f"{d}.json").write_text(json.dumps(res, default=float), encoding="utf-8")
        print("collected", d, "qualified", res["qualify"]["ok"], flush=True)


def gold_days():
    code = ("import sqlite3; c=sqlite3.connect('file:/data/cache.db?mode=ro', uri=True); "
            "print('\\n'.join(sorted({r[0] for r in c.execute('SELECT session_date FROM sn_gold_positions')})))")
    r = subprocess.run(["docker", "exec", "-u", "quantuser", CONTAINER, "python", "-c", code], capture_output=True, text=True)
    return set(r.stdout.split()) if r.returncode == 0 else None


def arm_stats(rows_by_day, arm, key="net205"):
    per = {d: [x[key] for x in rs.get(arm, []) if x.get(key) is not None] for d, rs in rows_by_day.items()}
    nets = {d: float(sum(v)) for d, v in per.items()}
    n = sum(len(v) for v in per.values())
    return nets, n, sum(1 for v in per.values() if v)


def verdict():
    out = HERE / "results-sn300.json"
    if out.exists():
        raise SystemExit("SN300 is scored once")
    days = sorted(p.stem for p in FWD.glob("*.json"))
    res_all = {d: json.loads((FWD / f"{d}.json").read_text(encoding="utf-8")) for d in days}
    q = [d for d in days if res_all[d]["qualify"]["ok"]][:N_SESSIONS]
    if len(q) < N_SESSIONS:
        raise SystemExit(f"only {len(q)} qualified sessions: SN300 waits for {N_SESSIONS}")
    gd = gold_days()
    gap = None if gd is None else [d for d in q if d not in gd]
    res = {"sessions": q, "gold_days_known": gd is not None, "gap_sessions": gap, "candidates": {}}
    for slot in ("SN291", "SN293"):
        rows = {d: res_all[d][slot] for d in q}
        cn, ct, cs = arm_stats(rows, "candidate")
        c4, _, _ = arm_stats(rows, "candidate", "net400")
        kn, _, _ = arm_stats(rows, "control")
        tot = sum(cn.values())
        best = max(cn.values()) if cn else 0.0
        gap_net = None if gap is None else sum(cn[d] for d in gap)
        r = {"trades": ct, "sessions_with_trades": cs, "net205": round(tot), "net400": round(sum(c4.values())),
             "control205": round(sum(kn.values())), "without_best_session": round(tot - best),
             "gap_sessions_net": None if gap_net is None else round(gap_net),
             "per_gap_session": None if not gap else round(gap_net / len(gap))}
        if ct < 30 or cs < 10:
            r["verdict"] = "INSUFFICIENT"
        else:
            ok = tot > 0 and r["net400"] > 0 and tot > r["control205"] and r["without_best_session"] > 0 and (gap_net is None or gap_net > 0)
            r["verdict"] = "PASS" if ok else "FAIL"
        res["candidates"][slot] = r
    ch = [x for d in q for x in res_all[d]["SN291"].get("challenger", []) if x["fixed205"] is not None and x["challenger205"] is not None]
    res["SN296_exit_challenger"] = {"n": len(ch), "fixed205": round(sum(x["fixed205"] for x in ch)),
                                   "challenger205": round(sum(x["challenger205"] for x in ch))}
    nx = [x for d in q for x in res_all[d]["SN291"].get("next_expiry", []) if x["front205"] is not None and x["next205"] is not None]
    res["SN294_next_expiry"] = {"n": len(nx), "front205": round(sum(x["front205"] for x in nx)), "next205": round(sum(x["next205"] for x in nx))}
    sc = [x for d in q for x in res_all[d]["SN291"].get("sensex_confirmed", []) if x["net205"] is not None]
    res["SN295_sensex"] = {c: {"n": sum(x["confirmed"] == c for x in sc), "net205": round(sum(x["net205"] for x in sc if x["confirmed"] == c))}
                           for c in (True, False)}
    print(json.dumps(res, indent=1), flush=True)
    out.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    {"collect": collect, "verdict": verdict}[sys.argv[1]]()

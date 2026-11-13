"""SN117 - Gold under the measured costs (calibration; PLAN.md). Per Production paper entry inside the quote archive:
equivalent stress per lot = (fill - decision mid) + (exit mid - exit fill) - the model's half spreads at both prices.
300 bootstrap means; Gold v5 rerun at each value; plus the point estimate with entries 1 minute late."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn111"))
import pc  # noqa: E402
import sn115  # noqa: E402

C, M, L = pc.C, pc.M, pc.L
qa = sn115.qa
WALLETS = (("A 15k 1 lot", 15000.0, "one", None), ("C 30k sized", 30000.0, "sized", None),
           ("30k fixed", 30000.0, "grow", 0), ("30k grow stop 3", 30000.0, "grow", 3))


def equivalent_stress():
    assert hashlib.sha256(sn115.DB.read_bytes()).hexdigest() == qa.manifest()["files_sha256"]["fno-replay.sqlite"]
    con = sqlite3.connect(f"file:{sn115.DB.as_posix()}?mode=ro", uri=True)
    cols = [r[1] for r in con.execute("PRAGMA table_info(fno_positions)")]
    pos = [dict(zip(cols, r)) for r in con.execute("SELECT * FROM fno_positions WHERE source='FNO_PAPER' AND underlying='NIFTY'")]
    qdays = set(qa.days())
    out = []
    for p in pos:
        if p["entry_date"] not in qdays or not p.get("exit_time") or p.get("exit_premium") is None:
            continue
        q = qa.load(p["entry_date"])
        r = q["opt"].get(("NIFTY", p["expiry"], int(round(p["strike"])), p["opt_type"]))
        if r is None:
            continue
        close = dt.datetime.fromisoformat(p["bar_ts"]) + dt.timedelta(minutes=5)
        xt = dt.datetime.fromisoformat(p["exit_time"]).replace(tzinfo=None)
        md, mx = sn115.mid(r, sn115.minute_of(close) - 1), sn115.mid(r, sn115.minute_of(xt))
        if md is None or mx is None:
            continue
        lot = p["lot_size"]
        model_half = (M.spread_for(p["entry_premium"]) + M.spread_for(p["exit_premium"])) / 2 * lot
        out.append({"day": p["entry_date"], "measured_round_trip_vs_mid": (p["entry_premium"] - md) * lot + (mx - p["exit_premium"]) * lot,
                    "model_half_spreads": model_half,
                    "equivalent_stress": (p["entry_premium"] - md) * lot + (mx - p["exit_premium"]) * lot - model_half})
    return out


def run_at(stress, extra=None):
    old = L.STRESS
    L.STRESS = float(stress)
    try:
        return C.totals(C.run({**C.V5, **(extra or {})}, WALLETS))
    finally:
        L.STRESS = old


if __name__ == "__main__":
    out_path = HERE / "results-sn117.json"
    if out_path.exists():
        raise SystemExit("SN117 is scored once")
    C.years()
    rows = equivalent_stress()
    e = np.array([r["equivalent_stress"] for r in rows])
    point = float(e.mean())
    rng = np.random.default_rng(117)
    boots = [float(rng.choice(e, len(e)).mean()) for _ in range(300)]
    print(f"positions {len(e)}  equivalent stress per lot: mean {point:.1f} median {np.median(e):.1f} "
          f"bootstrap 5-95% {np.percentile(boots, 5):.1f} .. {np.percentile(boots, 95):.1f}", flush=True)
    ref = {"205 (house)": run_at(205.0), "0": run_at(0.0), f"point {point:.0f}": run_at(point),
           f"point {point:.0f} + 1 minute late": run_at(point, {"late": 1}), "400": run_at(400.0)}
    for k, t in ref.items():
        print(f"   stress {k:28s}", t, flush=True)
    dist = {w[0]: [] for w in WALLETS}
    for s in boots:
        t = run_at(s)
        for w in dist:
            dist[w].append(t[w])
    pct = {w: {p: round(float(np.percentile(v, p))) for p in (5, 50, 95)} for w, v in dist.items()}
    print("Gold v5 net under the measured-cost bootstrap (5th / 50th / 95th):", pct, flush=True)
    out_path.write_text(json.dumps({"positions": rows, "point": point, "bootstrap_means": boots, "reference": ref,
                                    "percentiles": pct}, indent=1, default=float), encoding="utf-8")

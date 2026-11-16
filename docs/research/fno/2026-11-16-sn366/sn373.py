"""SN373: what waiting at a limit really saves (PLAN.md section 1, frozen at 3740b461; details fixed here before any SN373
number). The plan's rule picks the arm with the highest positive pre-stress room among SN353 (b) CONT, SN371 and SN376:
SN376's AUCTION direction, 1-2 strikes in the money at 09:16, 60-minute hold (+Rs 244 a trade at zero stress, 171
sessions, Dec 2025 - Oct 2026, gl's model).
  CROSS   buy at the model ask at 09:16 (SN376's own entry), sell at the model bid 60 minutes later, Rs 3,000 stop
  REST    a one-lot buy limit at the 09:16 mid (gl's minute close), live for the 09:17 and 09:18 minutes, no chase;
          conservative fill = a later minute's traded low BELOW the limit (a trade-through: a resting bid at the limit
          had price priority); permissive fill = low AT OR below the limit; no fill = no trade (0)
          a filled REST trade enters at the limit and exits exactly as CROSS (same exit minute rule and stop)
Reported at stress 0 / 205 / 400: fill rates, saving per filled trade (CROSS entry - limit) x lot, REST's mean per
decision and per filled trade under each bound, CROSS's mean, missed winners (CROSS > 0 where REST did not fill), and
adverse selection = CROSS's mean on filled vs missed sessions. Retire if REST beats CROSS only on the permissive bound.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn371 as S  # noqa: E402
import sn376 as I  # noqa: E402

gl, sn353b = S.gl, S.sn353b
OUT = HERE / "results-sn373.json"
LOT = 65


def run_one(smp, s, side):
    pos0, depth = I.leg(smp, s, side, 0.0)
    if pos0 is None:
        return None
    k = pos0.legs[0][0]
    mid = gl.opx(s, k, side, 1, look=1)
    a = s["options"].get((k, side))
    if mid is None or a is None:
        return None
    lows = [float(a[2][j]) for j in (2, 3) if not np.isnan(a[2][j])]
    out = {"strike": k, "depth": depth, "ask": pos0.fills[0], "limit": mid,
           "fill_conservative": any(x < mid - 1e-9 for x in lows), "fill_permissive": any(x <= mid + 1e-9 for x in lows)}
    for st in (0.0, 205.0, 400.0):
        pos = gl.Pos(smp, s, [(k, side, +1)], 1, lots=1, stress=st)
        net, j, _w = gl.walk(pos, s, 1, 61, room=S.STOP)
        out[f"cross@{int(st)}"] = None if net is None else round(net, 2)
        if net is not None:
            out[f"rest@{int(st)}"] = round(net + (pos0.fills[0] - mid) * LOT, 2)      # same exit, entry at the limit
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN373 is run once")
    raw = gl._cache("devall", gl.build_dev)
    smp = gl.Sample("ALL", raw, gl.DEV_LO, gl.TEST_HI)
    days = [d for d in smp.days if smp.s[d]["day"] != smp.s[d]["expiry"]]
    au = sn353b.auctions([d for d in days if sn353b.LO <= d < sn353b.HI])
    rows = []
    for d, a in sorted(au.items()):
        if a["g"] == 0 or d not in smp.s:
            continue
        r = run_one(smp, smp.s[d], "CE" if a["g"] > 0 else "PE")
        if r is not None and r.get("cross@205") is not None:
            r["day"] = d
            rows.append(r)
    res = {"decisions": len(rows), "itm_depth2_share": round(float(np.mean([r["depth"] == 2 for r in rows])), 3)}
    for bound in ("conservative", "permissive"):
        f = [r for r in rows if r[f"fill_{bound}"]]
        m = [r for r in rows if not r[f"fill_{bound}"]]
        b = {"fill_rate": round(len(f) / max(1, len(rows)), 3), "saving_per_filled_trade": round(float(np.mean([(r["ask"] - r["limit"]) * LOT for r in f])), 1) if f else None}
        for st in (0, 205, 400):
            b[f"rest_per_decision@{st}"] = round(float(np.sum([r[f"rest@{st}"] for r in f]) / max(1, len(rows))), 1)
            b[f"rest_per_filled@{st}"] = round(float(np.mean([r[f"rest@{st}"] for r in f])), 1) if f else None
            b[f"cross_on_filled@{st}"] = round(float(np.mean([r[f"cross@{st}"] for r in f])), 1) if f else None
            b[f"cross_on_missed@{st}"] = round(float(np.mean([r[f"cross@{st}"] for r in m])), 1) if m else None
        b["missed_winners@205"] = sum(1 for r in m if r["cross@205"] > 0)
        res[bound] = b
    for st in (0, 205, 400):
        res[f"cross_per_decision@{st}"] = round(float(np.mean([r[f"cross@{st}"] for r in rows])), 1)
    c, p = res["conservative"], res["permissive"]
    res["retire"] = bool(not (c["rest_per_decision@205"] > res["cross_per_decision@205"]) and p["rest_per_decision@205"] > res["cross_per_decision@205"])
    res["rows"] = rows
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))


if __name__ == "__main__":
    main()

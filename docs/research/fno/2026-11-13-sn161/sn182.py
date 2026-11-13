"""SN182 - the wage trade on real quotes (PLAN.md). Days where the sealed real-quote archive (Sep 10 - Nov 11, one
5-level snapshot a minute) overlaps the lab: Sep 10 ... Oct 28 (all inside TEST). The coin-flip wage trader (20 seeds:
random minute 09:30-14:30 and side, the session's ATM option of its nearest weekly expiry, as many lots as Rs 15k
buys) and the 15-minute range break are replayed twice on the same entries:
  model - the lab (P75 half-spread, charges, Rs 205 per lot, intrabar target / stop);
  real  - the archive: buy by walking the real ask depth, value each minute by walking the real bid depth, charges,
          no extra stress; exit at the first minute snapshot at or beyond +Rs 1,500 / -Rs 1,500 net, else at 15:10.
Measures: net per trade and per lot, the share of targets, and the real cost of a round trip against the model's."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn101"))
import pw  # noqa: E402
import qa  # noqa: E402

M = pw.M


def real_trade(q, S, i, opt, strike, wallet=15000.0):
    rec = q["opt"].get(("NIFTY", S.s["expiry"], int(strike), opt))
    if rec is None or not rec["usable"][i] or np.isnan(rec["ask"][i]):
        return None
    lots = int(wallet // (rec["ask"][i] * pw.LOT))
    if lots < 1:
        return None
    qty = lots * pw.LOT
    ask = qa.walk_cost(rec["askp"][:, i], rec["askq"][:, i], qty)
    if ask is None:
        return None
    mid0 = (rec["bid"][i] + rec["ask"][i]) / 2
    last = None
    for j in range(i + 1, pw.FLAT + 1):
        if not rec["usable"][j]:
            continue
        bid = qa.walk_cost(rec["bidp"][:, j], rec["bidq"][:, j], qty)
        if bid is None:
            continue
        v = (bid - ask) * qty - M.charges(ask, bid, qty)
        last = (v, j)
        if v >= 1500.0:
            return {"net": v, "reason": "target", "lots": lots, "half_spread_in": ask - mid0}
        if v <= -1500.0:
            return {"net": v, "reason": "stop", "lots": lots, "half_spread_in": ask - mid0}
    if last is None:
        return None
    return {"net": last[0], "reason": "time", "lots": lots, "half_spread_in": ask - mid0}


if __name__ == "__main__":
    out_path = HERE / "results-sn182.json"
    if out_path.exists():
        raise SystemExit("SN182 is scored once")
    lab = {S.day: S for S in pw.sessions()}
    qdays = [d for d in qa.days() if d in lab]
    pairs = {"coin-flip": [], "range break": []}
    for d in qdays:
        q, S = qa.load(d), lab[d]
        ents = []
        for k in range(20):
            rng = np.random.default_rng(pw.seed_of(d, k, 182))
            i = int(rng.integers(pw.I_MIN, pw.I_MAX + 1))
            dd = 1 if rng.random() < 0.5 else -1
            ents.append(("coin-flip", i, "CE" if dd > 0 else "PE", pw.atm(S, i)))
        got = pw.range_break_picker(15, 0)(S, pw.I_MIN, 0.0)
        if got:
            ents.append(("range break", *got))
        for kind, i, opt, strike in ents:
            m = pw.trade(S, i, opt, strike, 15000.0, target=1500.0, stop=-1500.0)
            r = real_trade(q, S, i, opt, strike)
            if m is not None and r is not None:
                pairs[kind].append((d, m, r))
    res = {"days": len(qdays), "from": qdays[0] if qdays else None, "to": qdays[-1] if qdays else None}
    for kind, xs in pairs.items():
        if not xs:
            continue
        mn = np.array([m["net"] for _d, m, _r in xs])
        rn = np.array([r["net"] for _d, _m, r in xs])
        lots_m = np.array([m["lots"] for _d, m, _r in xs])
        res[kind] = {"trades": len(xs), "model_net": round(float(mn.sum())), "real_net": round(float(rn.sum())),
                     "model_per_trade": round(float(mn.mean()), 1), "real_per_trade": round(float(rn.mean()), 1),
                     "model_targets": round(float(np.mean([m["reason"] == "target" for _d, m, _r in xs])), 3),
                     "real_targets": round(float(np.mean([r["reason"] == "target" for _d, _m, r in xs])), 3),
                     "real_minus_model_per_lot": round(float(((rn - mn) / lots_m).mean()), 1),
                     "real_half_spread_in_mean": round(float(np.mean([r["half_spread_in"] for _d, _m, r in xs])), 3)}
        print(f"SN182 {kind}: {json.dumps(res[kind])}", flush=True)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")

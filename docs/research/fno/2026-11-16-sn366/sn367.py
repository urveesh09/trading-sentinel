"""SN367: from a visible peak to a paycheck (PLAN.md section 1, frozen at 3740b461; details fixed here before any SN367
number). One bracket on SN351's positions (5 clocks x CE / PE, front-weekly ATM, one lot, non-expiry): gl DEV (modelled,
Apr 2022 - Aug 19, 2026) and the real-quote archive (walked one-lot bids).
At stress s (205 primary, 400): mark(j) = v(j) - s, v = net if sold at minute j (charges, no stress).
  TARGET   trigger when mark(m) >= +750 at a minute m; PRIMARY fill = the next eligible quote, mark(m + 1) (it can be
           below 750 or worse); diagnostic fill = mark(m)
  STOP     trigger when mark(m) <= -3,000; primary fill = mark(m + 1), diagnostic mark(m)
  TIMEOUT  no trigger within 60 minutes: mark(60) (the last price in the exit minute or the one before)
  UNRESOLVED  the fill quote is missing (no price at m + 1 / the deadline)
Reported: the share of each outcome, its mean realized net, the bracket's mean per position, against cash (0), a coin-flip
side (one side per decision) and SN351's fixed 60-minute hold on the same positions. Diagnostics: the best mark before the
trigger, the best mark in the 15 minutes after a target fill, the worst mark after a stop fill.
Never a new candidate.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
for p in ("2026-11-16-sn251", "2026-11-13-sn101", "2026-11-16-sn351"):
    sys.path.insert(0, str(FNO / p))
import gl  # noqa: E402
import qa  # noqa: E402
import sn351 as P  # noqa: E402

qa.EXPORT = P.qa.EXPORT
OUT = HERE / "results-sn367.json"
TGT, STOP, H = 750.0, 3000.0, 60


def bracket(v, s):
    """v: dict minute -> net at stress 0 (1..H+1). Returns (outcome, primary net, diagnostic net, best before, after)."""
    best = -1e18
    for m in range(1, H + 1):
        if m not in v:
            continue
        mk = v[m] - s
        if mk >= TGT or mk <= -STOP:
            out = "TARGET" if mk >= TGT else "STOP"
            nxt = v.get(m + 1)
            after = [v[x] - s for x in range(m + 1, m + 16) if x in v]
            if nxt is None:
                return "UNRESOLVED", None, mk, best, None
            return out, nxt - s, mk, best, (max(after) if out == "TARGET" else min(after)) if after else None
        best = max(best, mk)
    last = v.get(H) if H in v else v.get(H - 1)
    if last is None:
        return "UNRESOLVED", None, None, best, None
    return "TIMEOUT", last - s, last - s, best, None


def dev_paths():
    raw = gl._cache("devall", gl.build_dev)
    smp = gl.Sample("DEV", raw, gl.DEV_LO, gl.TEST_LO)
    out = []
    for d in smp.days:
        s = smp.s[d]
        if s["day"] == s["expiry"]:
            continue
        for c, i in P.CLOCKS.items():
            k = gl.atm(smp, s, i)
            for side in ("CE", "PE"):
                pos = gl.Pos(smp, s, [(k, side, +1)], i, lots=1, stress=0.0)
                if pos.ok:
                    out.append({"day": d, "clock": c, "side": side, "v": {j - i: x for j in range(i + 1, i + H + 2) if (x := pos.value(s, j)) is not None}})
    return out


def arch_paths():
    out = []
    for d in qa.days():
        q = qa.load(d)
        exps = sorted({k[1] for k in q["opt"] if k[0] == "NIFTY" and k[1] >= d})
        fut = qa.front_fut(q, "NIFTY")
        if not exps or exps[0] == d or fut is None:
            continue
        for c, i in P.CLOCKS.items():
            j0 = qa.last_before(fut, i, max(0, i - 2))
            if j0 is None:
                continue
            k = int(round(0.5 * (fut["bid"][j0] + fut["ask"][j0]) / 50.0) * 50)
            for side in ("CE", "PE"):
                rec = q["opt"].get(("NIFTY", exps[0], k, side))
                if rec is None:
                    continue
                i0 = qa.last_before(rec, i, i - 1)
                if i0 is None:
                    continue
                e = qa.walk_cost(rec["askp"][:, i0], rec["askq"][:, i0], P.LOT)
                if e is None:
                    continue
                v = {}
                for j in range(i0 + 1, min(qa.NM, i0 + H + 2)):
                    if rec["usable"][j]:
                        b = qa.walk_cost(rec["bidp"][:, j], rec["bidq"][:, j], P.LOT)
                        if b is not None:
                            v[j - i0] = (b - e) * P.LOT - gl.wk.charges(e, b, P.LOT, "NFO")
                out.append({"day": d, "clock": c, "side": side, "v": v})
    return out


def summarize(paths, s):
    rows = [(p, *bracket(p["v"], s)) for p in paths]
    out = {"positions": len(rows)}
    for o in ("TARGET", "STOP", "TIMEOUT", "UNRESOLVED"):
        rs = [r for r in rows if r[1] == o]
        nets = [r[2] for r in rs if r[2] is not None]
        dg = [r[3] for r in rs if r[3] is not None]
        out[o] = {"share": round(len(rs) / max(1, len(rows)), 3), "mean_net_primary": round(float(np.mean(nets)), 1) if nets else None,
                  "mean_net_same_minute": round(float(np.mean(dg)), 1) if dg else None}
    done = [r[2] for r in rows if r[2] is not None]
    out["bracket_per_position_primary"] = round(float(np.mean(done)), 1) if done else None
    same = [r[3] for r in rows if r[3] is not None]
    out["bracket_per_position_same_minute"] = round(float(np.mean(same)), 1) if same else None
    fixed = [p["v"].get(H, p["v"].get(H - 1)) for p in paths]
    fixed = [x - s for x in fixed if x is not None]
    out["fixed_60m_per_position"] = round(float(np.mean(fixed)), 1) if fixed else None
    coin = []
    for p, o, n, _dg, _b, _a in rows:
        if n is not None and random.Random(f"sn367-{p['day']}-{p['clock']}").choice(("CE", "PE")) == p["side"]:
            coin.append(n)
    out["coin_side_bracket_per_position"] = round(float(np.mean(coin)), 1) if coin else None
    tg = [r for r in rows if r[1] == "TARGET"]
    out["target_fill_slip_mean"] = round(float(np.mean([r[2] - r[3] for r in tg if r[2] is not None])), 1) if tg else None
    out["after_target_best_15m_mean"] = round(float(np.mean([r[5] for r in tg if r[5] is not None])), 1) if tg else None
    st = [r for r in rows if r[1] == "STOP"]
    out["stop_fill_slip_mean"] = round(float(np.mean([r[2] - r[3] for r in st if r[2] is not None])), 1) if st else None
    out["breakeven_target_share_needed"] = None
    if out["TARGET"]["mean_net_primary"] is not None and out["TIMEOUT"]["mean_net_primary"] is not None:
        # with the observed failure mix, the target share that would make the bracket break even
        loss = (out["STOP"]["share"] * (out["STOP"]["mean_net_primary"] or 0) + out["TIMEOUT"]["share"] * out["TIMEOUT"]["mean_net_primary"]) / max(1e-9, out["STOP"]["share"] + out["TIMEOUT"]["share"])
        w = out["TARGET"]["mean_net_primary"]
        out["breakeven_target_share_needed"] = round(-loss / (w - loss), 3) if w > loss else None
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN367 is run once")
    dv, ar = dev_paths(), arch_paths()
    res = {s: {"DEV": summarize(dv, float(s)), "ARCHIVE": summarize(ar, float(s))} for s in (205, 400)}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()

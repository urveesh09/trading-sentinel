"""SN382 (history): SN376's opening arm re-scored honestly on its own sessions (PLAN.md section 1, frozen at c6e99cee;
details fixed here before any SN382 number).

Sessions: gl DEV + TEST NIFTY, non-expiry; AUCTION = sn353b.auctions (Dec 8, 2025 - Oct 28, 2026), labelled by source
(match_row = the pre-open match row; fallback_0915_open = the first continuous minute) and by protocol (before / from Sep
7, 2026); GAP = the index gap 2022 - 2026 (|gap| >= 0.10%) as SN376.
Legs at 09:16 (minute 1), gl's executable model, one lot, held 20 and 60 minutes with the Rs 3,000 stop:
  ITM      the direction's side, depth 2 then 1, admissible only if model ask x lot + entry charges <= Rs 15,000
           (SN381's cash rule; neither -> INADMISSIBLE, scored 0); the model has no queue, so the order cap is not modelled
  ATM      the direction's side at the money, the same admissibility
  COIN_ITM a seeded coin side, the same depth rule and admissibility
Reported per sample and split: per-session net (skips 0) at Rs 205 / 400; fills; inadmissible count; paired difference
vs ATM and COIN_ITM on common fills with a date-level standard error; without the best day; the old SN376 (unchecked) arm
beside it; and how many of SN376's trades were over the room.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn366"))
import sn371 as S  # noqa: E402

gl, sn353b = S.gl, S.sn353b
OUT = HERE / "results-sn382.json"
ROOM, LOT = 15000.0, 65
SPLIT = "2026-09-07"


def cost_of(pos):
    f = pos.fills[0]
    return f * LOT + gl.wk.charges(f, 0.0, LOT, "NFO")


def leg(smp, s, side, i, stress, depths):
    atm = gl.atm(smp, s, i)
    sgn = -1 if side == "CE" else 1
    for dep in depths:
        k = atm + sgn * dep * 50
        pos = gl.Pos(smp, s, [(k, side, +1)], i, lots=1, stress=stress)
        if pos.ok and cost_of(pos) <= ROOM:
            return pos, dep
    return None, None


def old_leg(smp, s, side, i, stress):
    """SN376's selector as it was (depth 1 accepted at any premium)."""
    atm = gl.atm(smp, s, i)
    sgn = -1 if side == "CE" else 1
    for dep in (2, 1):
        pos = gl.Pos(smp, s, [(atm + sgn * dep * 50, side, +1)], i, lots=1, stress=stress)
        if pos.ok and (dep == 1 or pos.premium <= 15000.0):
            return pos, dep
    return None, None


def run(smp, days, dirs, labels):
    rows = []
    for d in days:
        if d not in dirs:
            continue
        s = smp.s[d]
        side = "CE" if dirs[d] > 0 else "PE"
        coin = random.Random(f"sn376-{d}").choice(("CE", "PE"))          # SN376's own coin seeds
        r = {"day": d, "src": labels.get(d), "period": "post" if d >= SPLIT else "pre", "year": d[:4]}
        for arm, sd, depths in (("ITM", side, (2, 1)), ("ATM", side, (0,)), ("COIN_ITM", coin, (2, 1))):
            r[arm] = {"state": "INADMISSIBLE"}
            for st in (0.0, 205.0, 400.0):
                pos, dep = leg(smp, s, sd, 1, st, depths)
                if pos is None:
                    break
                r[arm]["state"], r[arm]["depth"], r[arm]["cost"] = "FILLED", dep, round(cost_of(pos))
                for H in (20, 60):
                    net, _j, _w = gl.walk(pos, s, 1, 1 + H, room=S.STOP)
                    r[arm][f"{H}m@{int(st)}"] = None if net is None else round(net, 2)
        pos, dep = old_leg(smp, s, side, 1, 205.0)
        if pos is not None:
            net, _j, _w = gl.walk(pos, s, 1, 61, room=S.STOP)
            r["OLD"] = {"60m@205": None if net is None else round(net, 2), "over_room": cost_of(pos) > ROOM, "depth": dep}
        rows.append(r)
    return rows


def summarize(rows):
    out = {"sessions": len(rows)}
    for H in (20, 60):
        for st in (205, 400):
            k = f"{H}m@{st}"
            per = [r["ITM"].get(k) or 0.0 if r["ITM"]["state"] == "FILLED" else 0.0 for r in rows]
            out[f"ITM per_session {k}"] = round(float(np.mean(per)), 1) if per else None
            by = {}
            for r, v in zip(rows, per):
                by[r["day"]] = v
            out[f"ITM without_best_day {k}"] = round(float((sum(per) - max(by.values())) / max(1, len(per) - 1)), 1) if per else None
            for c in ("ATM", "COIN_ITM"):
                common = [r for r in rows if r["ITM"]["state"] == "FILLED" and r[c]["state"] == "FILLED" and r["ITM"].get(k) is not None and r[c].get(k) is not None]
                dd = np.array([r["ITM"][k] - r[c][k] for r in common])
                out[f"paired vs {c} {k}"] = {"common": len(common), "mean": round(float(dd.mean()), 1) if len(dd) else None,
                                             "se": round(float(dd.std(ddof=1) / np.sqrt(len(dd))), 1) if len(dd) > 1 else None}
    out["fills"] = sum(r["ITM"]["state"] == "FILLED" for r in rows)
    out["inadmissible"] = sum(r["ITM"]["state"] == "INADMISSIBLE" for r in rows)
    out["depth2_share"] = round(float(np.mean([r["ITM"].get("depth") == 2 for r in rows if r["ITM"]["state"] == "FILLED"])), 3) if out["fills"] else None
    old = [r["OLD"] for r in rows if r.get("OLD") and r["OLD"]["60m@205"] is not None]
    out["old_sn376_60m@205_per_trade"] = round(float(np.mean([o["60m@205"] for o in old])), 1) if old else None
    out["old_trades_over_room"] = sum(o["over_room"] for o in old)
    out["old_over_room_net_60m@205"] = round(float(sum(o["60m@205"] for o in old if o["over_room"])))
    return out


def main():
    if OUT.exists():
        raise SystemExit("SN382 is run once")
    raw = gl._cache("devall", gl.build_dev)
    smp = gl.Sample("ALL", raw, gl.DEV_LO, gl.TEST_HI)
    days = [d for d in smp.days if smp.s[d]["day"] != smp.s[d]["expiry"]]
    au = sn353b.auctions([d for d in days if sn353b.LO <= d < sn353b.HI])
    auc = {d: (1 if a["g"] > 0 else -1) for d, a in au.items() if a["g"] != 0}
    lab = {d: a["how"] for d, a in au.items()}
    gap = {}
    for d in days:
        pb, o = smp.prev_bar(d), smp.s[d]["index"][0][0]
        if pb is not None and not np.isnan(o) and abs(float(o) / float(pb[3]) - 1.0) >= 0.001:
            gap[d] = 1 if float(o) > float(pb[3]) else -1
    ra = run(smp, days, auc, lab)
    rg = run(smp, days, gap, {})
    res = {"AUCTION": summarize(ra), "GAP": summarize(rg)}
    for src in ("match_row", "fallback_0915_open"):
        res[f"AUCTION {src}"] = summarize([r for r in ra if r["src"] == src])
    for per in ("pre", "post"):
        res[f"AUCTION {per}-{SPLIT}"] = summarize([r for r in ra if r["period"] == per])
        res[f"AUCTION match_row {per}"] = summarize([r for r in ra if r["period"] == per and r["src"] == "match_row"])
    by_week = {}
    for r in ra:
        if r["ITM"]["state"] == "FILLED" and r["ITM"].get("60m@205") is not None:
            wk = np.datetime64(r["day"]).astype("datetime64[W]").astype(str)
            by_week.setdefault(wk, []).append(r["ITM"]["60m@205"])
    wk = np.array([np.sum(v) for v in by_week.values()])
    res["AUCTION weekly 60m@205"] = {"weeks": len(wk), "mean_week": round(float(wk.mean()), 1), "se_week": round(float(wk.std(ddof=1) / np.sqrt(len(wk))), 1),
                                     "weeks_positive": int((wk > 0).sum())}
    res["rows_auction"] = ra
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    for k, v in res.items():
        if k != "rows_auction":
            print(k, json.dumps({x: v[x] for x in v if x in ("sessions", "fills", "inadmissible", "ITM per_session 60m@205", "ITM per_session 60m@400", "ITM without_best_day 60m@205",
                                                         "paired vs ATM 60m@205", "paired vs COIN_ITM 60m@205", "ITM per_session 20m@205", "old_sn376_60m@205_per_trade",
                                                         "old_trades_over_room", "old_over_room_net_60m@205", "weeks", "mean_week", "se_week", "weeks_positive")}), flush=True)


if __name__ == "__main__":
    main()

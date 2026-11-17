"""SN287 (where the partner's green days were lost) and SN288 (the first-minute read at executable prices), PLAN.md.
Frozen Nov 4 extract (7 sessions), real minute quotes (SN101's sealed per-minute archive, SN121's symbol maps).
Privacy rule: shapes, shares, ratios and per-lot averages only; no partner rupee totals.

SN288 timing: the archive keeps one snapshot a minute, so "the first snapshot >= fill + 60 s" is taken as the fill
minute + 2 (always >= 60 s, at most ~3 minutes); +1 is shown for reference."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn121"))
import pg  # noqa: E402

qa, M = pg.qa, pg.M
GB_PEAK, GB_SHARE = 0.05 * 25000.0, 0.30
STRESS = 205.0


def orders():
    import json as _j
    b = (pg.PARTNER / "_local" / "production-selected.json").read_bytes()
    return _j.loads(b)["tables"]["partner_orders"]


def path_parts(day, trips):
    """Per minute: day value (realised + open marks at the bid), and per trip its mark series."""
    q = qa.load(day)
    smap = pg.symbol_map(day)
    n = qa.NM
    total = np.zeros(n)
    marks = []
    for t in trips:
        cm = pg.ist_minute(t["closed_at"])
        a, b = max(0, pg.ist_minute(t["first_at"])), (min(n - 1, cm) if cm is not None else 374)
        key = smap.get(t["tradingsymbol"])
        rec = q["opt"].get(key) if key else None
        mk = np.full(n, np.nan)
        last = None
        for m in range(a, b):
            x = pg.qbid(rec, m)
            if x is not None:
                last = x
            if last is not None:
                mk[m] = (last - t["entry"]) * t["bought"]
        if cm is not None and t["realised"] is not None:
            mk[b:] = t["realised"]
        else:
            mk[b:] = mk[b - 1] if b > a and not np.isnan(mk[b - 1]) else 0.0
        mk[:a] = 0.0
        mk = np.where(np.isnan(mk), 0.0, mk)
        marks.append((a, b, mk))
        total += mk
    return total, marks


def sn287(trips):
    by = collections.defaultdict(list)
    for t in trips:
        by[t["session_date"]].append(t)
    rng = np.random.default_rng(287)
    out = {"sessions": len(by), "alert_sessions": 0, "per_session": []}
    agg = {"open_inventory": [], "later_entries": [], "actual": [], "close_all": [], "no_new": [], "rand_close_all": [], "rand_no_new": []}
    for day, ts in sorted(by.items()):
        total, marks = path_parts(day, ts)
        peak, A = -np.inf, None
        for m, v in enumerate(total):
            peak = max(peak, v)
            if peak >= GB_PEAK and v <= peak * (1 - GB_SHARE):
                A = m
                break
        final = total[-1]
        row = {"day": day, "alert": A is not None}
        if A is None:
            out["per_session"].append(row)
            continue
        out["alert_sessions"] += 1
        open_at = [mk for a, b, mk in marks if a <= A < b]
        later = [mk for a, b, mk in marks if a > A]
        d_open = sum(mk[-1] - mk[A] for mk in open_at)
        d_later = sum(mk[-1] for mk in later)
        move = final - total[A]
        scale = abs(total[A]) if total[A] else 1.0
        row.update({"alert_minute": int(A), "change_after_alert_pct_of_value_at_alert": round(100 * move / scale, 1),
                    "share_from_open_inventory": round(d_open / move, 3) if move else None,
                    "share_from_later_entries": round(d_later / move, 3) if move else None,
                    "later_trips": len(later), "open_trips_at_alert": len(open_at)})
        # random alert clocks with similar open exposure
        expo = lambda m: sum(1 for a, b, _mk in marks if a <= m < b)  # noqa: E731
        e0 = max(1, expo(A))
        pool = [m for m in range(15, 346) if m != A and 0.5 * e0 <= expo(m) <= 2.0 * e0]
        rc, rn = [], []
        for m in (rng.choice(pool, min(200, len(pool)), replace=True) if pool else []):
            m = int(m)
            rc.append(total[m] - final)                   # gain of closing everything at m vs actual
            rn.append(-sum(mk[-1] for a, b, mk in marks if a > m))   # gain of no new entries after m vs actual
        row.update({"close_all_vs_actual_sign": int(np.sign(total[A] - final)), "no_new_vs_actual_sign": int(np.sign(-d_later)),
                    "close_all_better_than_random_clock_share": round(float(np.mean([(total[A] - final) > x for x in rc])), 3) if rc else None,
                    "no_new_better_than_random_clock_share": round(float(np.mean([(-d_later) > x for x in rn])), 3) if rn else None})
        out["per_session"].append(row)
        for k, v in (("open_inventory", d_open), ("later_entries", d_later), ("actual", move), ("close_all", total[A] - final), ("no_new", -d_later)):
            agg[k].append(v)
        agg["rand_close_all"].append(float(np.mean(rc)) if rc else 0.0)
        agg["rand_no_new"].append(float(np.mean(rn)) if rn else 0.0)
    if agg["actual"]:
        tot_move = sum(agg["actual"])
        out["pooled_shares_of_after_alert_change"] = {"open_inventory": round(sum(agg["open_inventory"]) / tot_move, 3),
                                                      "later_entries": round(sum(agg["later_entries"]) / tot_move, 3)}
        out["arms_vs_actual_sessions_better"] = {"close_all_at_alert": int(sum(x > 0 for x in agg["close_all"])),
                                                 "no_new_entries_after_alert": int(sum(x > 0 for x in agg["no_new"])),
                                                 "of": len(agg["actual"])}
        out["arms_vs_random_clocks"] = {"close_all: alert better than its random-clock mean in sessions": int(sum(a > b for a, b in zip(agg["close_all"], agg["rand_close_all"]))),
                                        "no_new: alert better than its random-clock mean in sessions": int(sum(a > b for a, b in zip(agg["no_new"], agg["rand_no_new"])))}
    return out


def sn288():
    od = [o for o in orders() if o.get("status") == "COMPLETE" and o.get("transaction_type") == "BUY"
          and (o.get("filled_quantity") or 0) > 0 and (o.get("average_price") or 0) > 0]
    rows, last_seen = [], {}
    for o in sorted(od, key=lambda o: o["placed_at"]):
        day = o["session_date"]
        try:
            q = qa.load(day)
        except Exception:
            continue
        key = pg.symbol_map(day).get(o["tradingsymbol"])
        rec = q["opt"].get(key) if key else None
        if rec is None:
            continue
        m = pg.ist_minute(o["placed_at"])
        if m is None or not (5 <= m <= 340):
            continue
        k2 = (day, o["tradingsymbol"])
        if k2 in last_seen and m - last_seen[k2] <= 2:          # collapse re-entries into the same move
            last_seen[k2] = m
            continue
        last_seen[k2] = m
        lot = q["lot"][key[0]]
        fill = float(o["average_price"])
        b1, b2, a0 = pg.qbid(rec, m + 1), pg.qbid(rec, m + 2), pg.qask(rec, m)
        if b2 is None:
            continue
        bucket = m // 30
        ctl, ctl1, ctl_lot = [], [], []
        for c in range(bucket * 30, bucket * 30 + 30):
            if abs(c - m) <= 2 or c < 5 or c > 340:
                continue
            ca, cb, cb1 = pg.qask(rec, c), pg.qbid(rec, c + 2), pg.qbid(rec, c + 1)
            if ca is None or cb is None:
                continue
            ctl.append((cb - ca) / ca)
            if cb1 is not None:
                ctl1.append((cb1 - ca) / ca)
            ctl_lot.append((cb - ca) * lot - M.charges(ca, cb, lot) - STRESS)
        if not ctl:
            continue
        rows.append({"day": day, "lift2": (b2 - fill) / fill, "lift1": None if b1 is None else (b1 - fill) / fill,
                     "ctl2": float(np.mean(ctl)), "ctl1": float(np.mean(ctl1)) if ctl1 else None,
                     "per_lot2": (b2 - fill) * lot - M.charges(fill, b2, lot) - STRESS, "ctl_per_lot2": float(np.mean(ctl_lot)),
                     "fill_vs_ask_pct": None if a0 is None else (fill - a0) / a0})
    by = collections.defaultdict(list)
    for r in rows:
        by[r["day"]].append(r)
    sess = {d: float(np.mean([r["lift2"] - r["ctl2"] for r in rs])) for d, rs in by.items()}
    out = {"buy_events": len(rows), "sessions": len(by),
           "partner_exec_lift_2min_pct": round(100 * float(np.mean([r["lift2"] for r in rows])), 2),
           "control_exec_lift_2min_pct": round(100 * float(np.mean([r["ctl2"] for r in rows])), 2),
           "partner_exec_lift_1min_pct": round(100 * float(np.mean([r["lift1"] for r in rows if r["lift1"] is not None])), 2),
           "control_exec_lift_1min_pct": round(100 * float(np.mean([r["ctl1"] for r in rows if r["ctl1"] is not None])), 2),
           "partner_per_lot_2min_after_costs": round(float(np.mean([r["per_lot2"] for r in rows]))),
           "control_per_lot_2min_after_costs": round(float(np.mean([r["ctl_per_lot2"] for r in rows]))),
           "fill_vs_snapshot_ask_pct_median": round(100 * float(np.median([r["fill_vs_ask_pct"] for r in rows if r["fill_vs_ask_pct"] is not None])), 2),
           "sessions_partner_beats_control": int(sum(v > 0 for v in sess.values())),
           "sign_test_p_one_sided": float(sum(1 for _ in [0])) if False else None}
    k = out["sessions_partner_beats_control"]
    n = len(sess)
    from math import comb
    out["sign_test_p_one_sided"] = round(sum(comb(n, j) for j in range(k, n + 1)) / 2 ** n, 4) if n else None
    return out


if __name__ == "__main__":
    outp = HERE / "results-sn287-288.json"
    if outp.exists():
        raise SystemExit("SN287-SN288 run once")
    res = {"SN287": sn287(pg.partner_trips()), "SN288": sn288()}
    print(json.dumps(res, indent=1), flush=True)
    outp.write_text(json.dumps(res, indent=1), encoding="utf-8")

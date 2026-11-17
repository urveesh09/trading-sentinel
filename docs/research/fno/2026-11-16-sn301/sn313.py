"""SN313: the give-back alert, order by order (PLAN.md, frozen at 94c772cd). Frozen Nov 4 partner extract (hash-checked by
pg.partner_trips), real minute quotes (SN101's sealed archive). Privacy rule: shares, counts and signs only; no rupee totals.

The alert minute A is SN287's reconstruction (the day path from the trips: a day that reached 5% of Rs 25,000 gives back
30% of its best). Every COMPLETE order of the session is replayed first-in first-out per contract:
  - a BUY at or before A is "inventory"; a BUY after A is "new" when no position in the same underlying and side (CE / PE)
    is open at that moment, else "add";
  - each bought piece is valued to its FIFO sale (or, if still open, to the last executable bid of the session) with
    Zerodha charges for new / add pieces;
  - an inventory piece counts only its change after A: from the bid at A (or its entry if bought later... never) to its sale
    or the last bid.
Reported per alert session: the shares of the post-alert change from inventory, new and add pieces; the counts; and the
sign of "no new episodes" / "no new episodes and no adds" against the actual session."""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn286"))
import sn287_288 as P  # noqa: E402

pg, qa, M = P.pg, P.qa, P.M


def alert_minute(day, trips):
    total, _marks = P.path_parts(day, trips)
    peak = -np.inf
    for m, v in enumerate(total):
        peak = max(peak, v)
        if peak >= P.GB_PEAK and v <= peak * (1 - P.GB_SHARE):
            return m, total
    return None, total


def last_bid(rec, upto=374):
    for m in range(min(upto, qa.NM - 1), -1, -1):
        b = pg.qbid(rec, m)
        if b is not None:
            return b
    return None


def bid_at(rec, m):
    for k in range(m, max(-1, m - 6), -1):
        b = pg.qbid(rec, k)
        if b is not None:
            return b
    return None


def session(day, ords, A):
    q = qa.load(day)
    smap = pg.symbol_map(day)
    book = collections.defaultdict(collections.deque)       # symbol -> [qty_left, price, minute, class]
    val = collections.Counter()
    cnt = collections.Counter()
    unmatched_sells = 0
    for o in sorted(ords, key=lambda o: o["placed_at"]):
        m = pg.ist_minute(o["placed_at"])
        sym = o["tradingsymbol"]
        qty, px = int(o["filled_quantity"]), float(o["average_price"])
        key = smap.get(sym)
        side = (key[0], key[3]) if key else (sym[:6], sym[-2:])
        rec = q["opt"].get(key) if key else None
        if o["transaction_type"] == "BUY":
            if m is None or m <= A:
                cls = "inventory"
            else:
                open_same = any(sum(p[0] for p in dq) > 0 for s, dq in book.items()
                                if ((smap.get(s)[0], smap.get(s)[3]) if smap.get(s) else (s[:6], s[-2:])) == side)
                cls = "add" if open_same else "new"
            cnt[cls] += 1
            book[sym].append([qty, px, m, cls, rec])
            continue
        left = qty
        while left > 0 and book[sym]:
            p = book[sym][0]
            take = min(left, p[0])
            val[p[3]] += piece_value(p, px, take, A, sold_at=m)
            p[0] -= take
            left -= take
            if p[0] == 0:
                book[sym].popleft()
        unmatched_sells += left > 0
    for sym, dq in book.items():
        for p in dq:
            if p[0] > 0:
                b = last_bid(p[4]) if p[4] is not None else None
                val[p[3]] += piece_value(p, b if b is not None else 0.0, p[0], A, sold_at=None)
    return val, cnt, unmatched_sells


def piece_value(p, sell_px, qty, A, sold_at):
    _left, buy_px, m, cls, rec = p
    if cls == "inventory":
        if sold_at is not None and sold_at <= A:
            return 0.0                                     # sold before the alert: no post-alert change
        ref = bid_at(rec, A) if rec is not None else None
        ref = buy_px if ref is None else ref
        return (sell_px - ref) * qty
    return (sell_px - buy_px) * qty - M.charges(buy_px, sell_px, qty)


if __name__ == "__main__":
    out_path = HERE / "results-sn313.json"
    if out_path.exists():
        raise SystemExit("SN313 is run once")
    trips = pg.partner_trips()
    by_trip = collections.defaultdict(list)
    for t in trips:
        by_trip[t["session_date"]].append(t)
    ords = [o for o in P.orders() if o.get("status") == "COMPLETE" and (o.get("filled_quantity") or 0) > 0 and (o.get("average_price") or 0) > 0]
    by_ord = collections.defaultdict(list)
    for o in ords:
        by_ord[o["session_date"]].append(o)
    res = {"sessions_with_orders": len(by_ord), "alert_sessions": [], "pooled": {}}
    pooled = collections.Counter()
    for day in sorted(by_trip):
        A, total = alert_minute(day, by_trip[day])
        if A is None or day not in by_ord:
            continue
        val, cnt, unmatched = session(day, by_ord[day], A)
        post = val["inventory"] + val["new"] + val["add"]
        row = {"day": day, "alert_minute": int(A), "orders_after_alert": {"new": cnt["new"], "add": cnt["add"]},
               "orders_before_or_at_alert": cnt["inventory"], "unmatched_sells": unmatched,
               "shares_of_post_alert_change": {k: round(val[k] / post, 3) if post else None for k in ("inventory", "new", "add")},
               "post_alert_change_sign": int(np.sign(post)),
               "signs": {k: int(np.sign(val[k])) for k in ("inventory", "new", "add")},
               "no_new_better_than_actual": bool(-val["new"] > 0), "no_new_no_add_better_than_actual": bool(-(val["new"] + val["add"]) > 0)}
        res["alert_sessions"].append(row)
        pooled.update({k: val[k] for k in ("inventory", "new", "add")})
        print("SN313", json.dumps(row), flush=True)
    tp = sum(pooled.values())
    res["pooled"] = {"shares": {k: round(pooled[k] / tp, 3) if tp else None for k in ("inventory", "new", "add")},
                     "sessions_no_new_better": sum(r["no_new_better_than_actual"] for r in res["alert_sessions"]),
                     "sessions_no_new_no_add_better": sum(r["no_new_no_add_better_than_actual"] for r in res["alert_sessions"]),
                     "of": len(res["alert_sessions"])}
    print("SN313 pooled", json.dumps(res["pooled"]), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")

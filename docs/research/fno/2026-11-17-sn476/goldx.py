"""SN476-SN490: an instrumented copy of gw.walk (Gold v5's position walk, cash rule "mtm" = Gold v5 line for line) with the
round's switches. With every switch off it must reproduce Gold v5 (checked: DEPLOYED 2023-26 @205 = Rs 8,50,882 / 883).
Gold's frozen files, the SN51 lab and gw.py are not edited; install() points the lab at this walk, after gold.install().

Switches (v keys; all default off):
  stop_rule   "low" (Gold: the bar's bid low touches the stop, fill min(stop, open bid)) | "close" (SN476 D: the minute's close
              bid, or the mark on an untraded minute, at or below the stop; the fill is that bid)
  fail_theta  None | theta (SN480 / SN486): after an add, the future's close through c[i] + d*theta*atr[i] against the trade
              sells only the added lots; theta = 0 is the original entry level
  fail_exec   "next" (SN480: at minute j+1's executable bid = close bid if traded, else the mark) | "same" (minute j's bid)
  fail_fee    Rs added to each failed-add sale (default 23.60 when fail_theta is set: one more order's brokerage + GST)
  no_add      frozenset of experts whose trades never add (SN489)
  skip_add    callable(day, sg) -> bool: the add is not taken (SN483's reduction)
Every trade is logged into gw.LOG (the runner reads it) with the failed-add events.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-17-sn411"))
import gold  # noqa: E402

gw = gold.Q.gw
L, M = gw.L, gw.M
CUR = gw.CUR
LOG = gw.LOG


def _bid(bc, bm, tr, j):
    return float(bc[j]) if tr[j] else float(bm[j])


def walk(S, rec, ask, lots, i, j_n11, d, v, room, wallet):
    a, bo, bh, bl, bc, bm, tr = rec
    c, atr = S.F["c"], S.F["atr"]
    sg = CUR.get("sg") or {}
    qty = lots * M.LOT
    stop = M._ceil_tick(ask - (room - L.cost(ask, ask, qty, lots)) / qty)
    stop0 = stop
    out_px = ask * (1 + v["out_x"]) if v.get("out_x") and lots >= 2 else None
    in_px = ask * (1 + v["in_x"]) if v.get("in_x") else None
    in_u = (c[i] + d * v["in_atr"] * atr[i]) if v.get("in_atr") else None
    if in_u is not None:
        in_px = None
    if in_u is not None and (sg.get("expert") in v.get("no_add", ()) or (v.get("skip_add") and v["skip_add"](S.day, sg))):
        in_u = None
    ext_end = v.get("ext_end", 355)
    theta = v.get("fail_theta")
    fail_exec = v.get("fail_exec", "next")
    fail_fee = v.get("fail_fee", 23.6 if theta is not None else 0.0)
    fail_level = None if theta is None else c[i] + d * theta * atr[i]
    stop_rule = v.get("stop_rule", "low")
    peak_b = ask
    held = [[ask, lots]]
    realized = 0.0
    ext, best_u, px, j = False, c[i], None, i
    j_add, pending, failed = None, None, False
    log = {"day": S.day, "i": i, "j_n11": j_n11, "d": d, "lots0": lots, "ask0": ask, "wallet": wallet, "room": room,
           "stop0": stop, "adds": [], "reason": None, "ext": False, "fail": None}
    reason = None
    for j in range(i + 1, max(M.EXIT_MIN, v.get("ext_end", 355)) + 1):
        open_lots = sum(p[1] for p in held)
        if stop_rule == "low":
            if tr[j] and bl[j] <= stop:
                px = min(stop, bo[j])
                reason = "stop"
                break
        else:
            b_now = _bid(bc, bm, tr, j)
            if not np.isnan(b_now) and b_now <= stop:
                px = b_now
                reason = "stop"
                break
        bid = bc[j] if tr[j] else bm[j]
        if out_px is not None and tr[j] and bh[j] >= out_px and open_lots >= 2:
            e = held[0][0]
            realized += (out_px - e) * M.LOT - L.cost(e, out_px, M.LOT, 1)
            held[0][1] -= 1
            out_px = None
        trig = (in_px is not None and tr[j] and bc[j] >= in_px) or (in_u is not None and tr[j] and (c[j] - in_u) * d >= 0)
        if trig and in_u is not None:
            in_u = None
        if trig:
            add_ask = M.ask_of(float(a[3][j]))
            n_new = max(1, int(wallet // (add_ask * M.LOT)) - open_lots) if v.get("in_full") else 1
            fits = (open_lots + n_new) * add_ask * M.LOT <= wallet
            info = {"j": j, "ask": add_ask, "open": open_lots, "n_mtm": n_new, "fits_mtm": fits, "added": 0}
            if fits:
                pieces = held + [[add_ask, n_new]]
                q = sum(n for _e, n in pieces) * M.LOT
                avg = sum(e * n for e, n in pieces) * M.LOT / q
                fees = sum(L.cost(e, e, n * M.LOT, n) for e, n in pieces) + realized * 0
                new_stop = M._ceil_tick(avg - (room - realized - fees) / q)
                if new_stop < bc[j]:
                    held.append([add_ask, n_new])
                    stop = max(stop, new_stop)
                    info["added"] = n_new
                    info["stop_after"] = stop
                    j_add = j
                else:
                    info["stop_blocked"] = True
            log["adds"].append(info)
            n_add = len(held) - 1
            in_px = ask * (1 + v["in_x"] * (n_add + 1)) if n_add < v.get("in_max", 1) and n_add >= 1 else None
            if n_add == 0 and v.get("in_max", 1) > 1:
                in_px = ask * (1 + v["in_x"])
        best_u = max(best_u, c[j]) if d > 0 else min(best_u, c[j])
        if ext:
            peak_b = max(peak_b, bid)
            if v.get("ext_give") and bid <= peak_b - v["ext_give"] * (peak_b - ask):
                px = bid
                reason = "ext_give"
                break
            if (c[j] - (best_u - d * v["ext_k"] * atr[j])) * d <= 0 or j >= ext_end:
                px = bid
                reason = "ext_trail" if j < ext_end else "ext_end"
                break
        elif j >= j_n11:
            if v.get("extend") and bid >= ask * (1 + v["ext_x"]) and j < ext_end:
                ext = True
                log["ext"] = True
                log["n11_bid"] = float(bid)
                log["held_at_n11"] = [list(p) for p in held]
            else:
                px = bid
                reason = "n11"
                break
        # ---- the failed add (SN480 / SN486): only when the whole position did not exit this minute ----
        if pending is not None and len(held) > 1:
            px_a = float(bid)
            if np.isnan(px_a):
                px_a = float(bm[j]) if not np.isnan(bm[j]) else None
            if px_a is not None:
                sold = held[1:]
                net_a = sum((px_a - e) * n * M.LOT - L.cost(e, px_a, n * M.LOT, n) for e, n in sold) - fail_fee
                realized += net_a
                q_sold = sum(n for _e, n in sold)
                assert q_sold <= sum(n for _e, n in held) and all(n > 0 for _e, n in sold)
                held = held[:1]
                e0, n0 = held[0]
                q0 = n0 * M.LOT
                stop = max(stop0, M._ceil_tick(e0 - (room + realized - L.cost(e0, e0, q0, n0)) / q0))
                log["fail"] = {"j_sig": pending, "j_exec": j, "px": px_a, "lots": q_sold, "net": net_a, "stop_after": stop,
                               "add_ask": sold[0][0]}
                pending, failed = None, True
        if (fail_level is not None and j_add is not None and j > j_add and not failed and pending is None and len(held) > 1
                and (c[j] - fail_level) * d < 0):
            if fail_exec == "same":
                pending = j
                px_a = float(bid) if not np.isnan(bid) else (float(bm[j]) if not np.isnan(bm[j]) else None)
                if px_a is not None:
                    sold = held[1:]
                    net_a = sum((px_a - e) * n * M.LOT - L.cost(e, px_a, n * M.LOT, n) for e, n in sold) - fail_fee
                    realized += net_a
                    q_sold = sum(n for _e, n in sold)
                    held = held[:1]
                    e0, n0 = held[0]
                    q0 = n0 * M.LOT
                    stop = max(stop0, M._ceil_tick(e0 - (room + realized - L.cost(e0, e0, q0, n0)) / q0))
                    log["fail"] = {"j_sig": j, "j_exec": j, "px": px_a, "lots": q_sold, "net": net_a, "stop_after": stop,
                                   "add_ask": sold[0][0]}
                    pending, failed = None, True
            else:
                pending = j
    marked = False
    if px is None or np.isnan(px):
        px = float(bm[j]) if not np.isnan(bm[j]) else ask
        reason = reason or "end"
        marked = True
    px = float(px)
    pieces_net = []
    for e, n in held:
        if n > 0:
            pn = (px - e) * n * M.LOT - L.cost(e, px, n * M.LOT, n)
            realized += pn
            pieces_net.append([e, n, pn])
    log.update(j=j, px=px, reason=reason, traded_exit=bool(tr[j]) and not marked, net=realized, pieces=pieces_net, stop=stop,
               fees=sum(L.cost(e, px, n * M.LOT, n) for e, n in held if n > 0))
    if log["ext"]:
        cf = sum((log["n11_bid"] - e) * n * M.LOT - L.cost(e, log["n11_bid"], n * M.LOT, n) for e, n in log["held_at_n11"] if n > 0)
        log["ext_contrib"] = realized - cf
    log.update(expert=sg.get("expert"), opt=sg.get("opt"), n11_strike=sg.get("strike"), sig_j=sg.get("j"))
    LOG.append(log)
    return realized, j, px


def install():
    gold.install()
    L.walk = walk


SELF_30K = ("30k self-funded", 30000.0, "float", None)
ONE_15K = ("A 15k 1 lot", 15000.0, "one", None)
GOLD_30K = gold.GOLD_30K

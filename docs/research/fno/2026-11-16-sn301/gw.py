"""SN310 / SN311: an instrumented copy of the SN51 lab's `walk` (Gold v5's position walk; lab.py and the frozen sn-gold
files are not edited). With v["cash"] absent or "mtm" it is the lab's rule line for line, and every trade is logged for
the loss waterfall. Two other scale-in cash rules (PLAN.md, SN311):
  "both"  : Gold v5's added lots and test, and also paid debit of the open lots + the new lots' debit + buy-side charges
            <= the wallet (lots reduced to what fits, >= 1, else no add);
  "debit" : added lots = floor((wallet - paid - buy-side charges) / (ask x lot)) >= 1, replacing the mark-to-market test.
install() points the lab at this walk and wraps the harness's gold_one so each log row knows its signal."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn251"))
import ow  # noqa: E402

C = ow.C
L = C.L
M = L.M
LOG: list = []
CUR = {"sg": None, "day": None}
_ORIG = {"walk": L.walk, "gold_one": C.gold_one}


def buy_fees(e, qty):
    return M.charges(e, 0.0, qty)


def walk(S, rec, ask, lots, i, j_n11, d, v, room, wallet):
    cash = v.get("cash", "mtm")
    a, bo, bh, bl, bc, bm, tr = rec
    c, atr = S.F["c"], S.F["atr"]
    qty = lots * M.LOT
    stop = M._ceil_tick(ask - (room - L.cost(ask, ask, qty, lots)) / qty)
    out_px = ask * (1 + v["out_x"]) if v.get("out_x") and lots >= 2 else None
    in_px = ask * (1 + v["in_x"]) if v.get("in_x") else None
    in_u = (c[i] + d * v["in_atr"] * atr[i]) if v.get("in_atr") else None
    if in_u is not None:
        in_px = None
    ext_end = v.get("ext_end", 355)
    peak_b = ask
    held = [[ask, lots]]
    realized = 0.0
    ext, best_u, px, j = False, c[i], None, i
    log = {"day": S.day, "i": i, "j_n11": j_n11, "d": d, "lots0": lots, "ask0": ask, "wallet": wallet, "room": room,
           "stop0": stop, "adds": [], "reason": None, "ext": False, "add_minutes": []}
    reason = None
    for j in range(i + 1, max(M.EXIT_MIN, v.get("ext_end", 355)) + 1):
        open_lots = sum(p[1] for p in held)
        if tr[j] and bl[j] <= stop:
            px = min(stop, bo[j])
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
            n_mtm = max(1, int(wallet // (add_ask * M.LOT)) - open_lots) if v.get("in_full") else 1
            fits_mtm = (open_lots + n_mtm) * add_ask * M.LOT <= wallet
            paid = sum(e * n * M.LOT for e, n in held if n > 0)
            fee_open = sum(buy_fees(e, n * M.LOT) for e, n in held if n > 0)
            n_cash = 0
            for n in range(int((wallet - paid - fee_open) // (add_ask * M.LOT)) + 1, 0, -1):
                if paid + fee_open + n * add_ask * M.LOT + buy_fees(add_ask, n * M.LOT) <= wallet:
                    n_cash = n
                    break
            if cash == "mtm":
                n_new, fits = n_mtm, fits_mtm
            elif cash == "both":
                n_new = min(n_mtm, n_cash)
                fits = fits_mtm and n_new >= 1
            elif cash == "debit":
                n_new, fits = n_cash, n_cash >= 1
            else:
                raise ValueError(cash)
            info = {"j": j, "ask": add_ask, "open": open_lots, "paid": paid, "n_mtm": n_mtm, "fits_mtm": fits_mtm, "n_cash": n_cash,
                    "over_wallet_if_mtm": bool(fits_mtm and paid + n_mtm * add_ask * M.LOT > wallet),
                    "excess_if_mtm": round(paid + n_mtm * add_ask * M.LOT - wallet, 2) if fits_mtm else None, "added": 0}
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
                n11_bid = bid
                log["n11_bid"] = float(bid)
                log["held_at_n11"] = [list(p) for p in held]
            else:
                px = bid
                reason = "n11"
                break
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
    if reason == "stop":
        log["overshoot"] = (stop - px) * sum(n for _e, n in held if n > 0) * M.LOT
    if log["ext"]:
        cf = sum((log["n11_bid"] - e) * n * M.LOT - L.cost(e, log["n11_bid"], n * M.LOT, n) for e, n in log["held_at_n11"] if n > 0)
        log["ext_contrib"] = realized - cf
    sg = CUR["sg"]
    if sg is not None:
        log.update(expert=sg.get("expert"), opt=sg.get("opt"))
    LOG.append(log)
    return realized, j, px


def gold_one(S, sg, *args, **kw):
    CUR["sg"] = sg
    try:
        return _ORIG["gold_one"](S, sg, *args, **kw)
    finally:
        CUR["sg"] = None


def install():
    L.walk = walk
    C.gold_one = gold_one


def uninstall():
    L.walk = _ORIG["walk"]
    C.gold_one = _ORIG["gold_one"]

"""SN51-SN75 LAB (a copy of the frozen sn-gold/gold_v4.py; v4 itself is never edited).
SN31-SN50 LAB (a copy of the frozen sn-gold/gold_v3.py with extra knobs; v3 itself is never edited).
SN Gold harness (research only): N11's entries + every SN idea from SN19 on, scored at every wallet.

SN GOLD (owner, Nov 12: "the current best ... will be called SN Gold"), from SN02 / SN13 / SN16:
  N11's entries and exits; a winner up >= 25% at N11's exit is kept with a 3-ATR index trail until 15:10 (SN16);
  lots = floor(W / 15,000), halved (min 1) on a low-volatility day (SN13); the wallet starts at Rs 15,000 and grows 50%
  after net profit equal to the wallet, stopped after the 3rd step; 20% day loss limit; the strike one step out of the
  money when a lot costs more than the wallet; current Zerodha charges + Rs 205 per lot per trade; losing days refilled.

A variant `v` switches ideas on. Every variant is reported at: A Rs 15k 1 lot, B Rs 20k 1 lot, C Rs 30k sized, and
growth from Rs 15k stopped after 0, 2, 3 (Gold), 5 steps. Per year: net, refilled, days won / lost / no trade, worst day.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
for _p in ("2026-11-12-sn02", "2026-11-12-sn03", "2026-11-12-sn13"):
    sys.path.insert(0, str(HERE.parent / _p))
import sn02_ext as X  # noqa: E402
import sn03 as B  # noqa: E402
import sn13 as V  # noqa: E402
from sn03_run import loyo  # noqa: E402

M = B.M
YEARS = B.YEARS
STRESS = 205.0
GOLD = {"extend": True, "ext_x": 0.25, "ext_k": 3.0}
WALLETS = (("A 15k 1 lot", 15000.0, "one", None), ("B 20k 1 lot", 20000.0, "one", None), ("C 30k sized", 30000.0, "sized", None),
           ("G0", 15000.0, "grow", 0), ("G2", 15000.0, "grow", 2), ("G3 (Gold)", 15000.0, "grow", 3), ("G5", 15000.0, "grow", 5))


STRESS_PCT = 0.0      # SN65: slippage as a share of premium per side (on top of STRESS per lot)


def cost(entry, exit_, qty, lots):
    return M.charges(entry, exit_, qty) + STRESS * lots + STRESS_PCT * (entry + exit_) * qty


def _rng(day, i):
    import hashlib
    return int(hashlib.sha256(f"{day}|{i}".encode()).hexdigest()[:8], 16) / 2 ** 32


def quote(S, strike, opt, i):
    rec = S.option(strike, opt)
    if rec is None or not rec[6][i]:
        return None
    return rec


def affordable(S, i, strike, opt, budget, step_out=True):
    for attempt in range(2):
        rec = quote(S, strike, opt, i)
        if rec is None:
            return None
        ask = M.ask_of(float(rec[0][3][i]))
        if ask * M.LOT <= budget:
            return rec, ask, strike
        if attempt or not step_out:
            return None
        strike += M.STEP if opt == "CE" else -M.STEP


OI = {}
ADX = {}


def oi_agree(S, sg, v):
    oi = OI.get(S.day)
    if not oi:
        return False
    k, w, thr = v.get("oi_k", 15), v.get("oi_w", 150), v.get("oi_thr", 0.0)
    i = sg["i"]
    if i < k:
        return False
    p = S.F["c"][i]
    near = sorted({s for s, _ in oi if abs(s - p) <= w})

    def tot(opt, at):
        return sum(float(oi[(s, opt)][at]) for s in near if (s, opt) in oi)
    d_pe, d_ce = tot("PE", i) - tot("PE", i - k), tot("CE", i) - tot("CE", i - k)
    base = tot("PE", i - k) + tot("CE", i - k)
    flow = (d_pe - d_ce) / base if base > 0 else 0.0
    return flow * (1 if sg["opt"] == "CE" else -1) >= thr


class Ctx:
    """Causal per-run state shared across days (for adaptive sizing)."""

    def __init__(self):
        self.day_nets = []
        self.closed = []      # (day, minute, expert, net per lot) of earlier trades, in time order


def walk(S, rec, ask, lots, i, j_n11, d, v, room, wallet):
    """One N11 position with optional scale-out (SN27), scale-in (SN28), hedge (SN24), short leg (SN25)."""
    a, bo, bh, bl, bc, bm, tr = rec
    c, atr = S.F["c"], S.F["atr"]
    qty = lots * M.LOT
    stop = M._ceil_tick(ask - (room - cost(ask, ask, qty, lots)) / qty)
    out_px = ask * (1 + v["out_x"]) if v.get("out_x") and lots >= 2 else None
    in_px = ask * (1 + v["in_x"]) if v.get("in_x") else None
    in_u = (c[i] + d * v["in_atr"] * atr[i]) if v.get("in_atr") else None
    if in_u is not None:
        in_px = None
    ext_end = v.get("ext_end", 355)
    peak_b = ask
    held = [[ask, lots]]          # [entry, lots] pieces still open
    realized = 0.0
    ext, best_u, px, j = False, c[i], None, i
    for j in range(i + 1, max(M.EXIT_MIN, v.get("ext_end", 355)) + 1):
        open_lots = sum(p[1] for p in held)
        if tr[j] and bl[j] <= stop:
            px = min(stop, bo[j])
            break
        bid = bc[j] if tr[j] else bm[j]
        if out_px is not None and tr[j] and bh[j] >= out_px and open_lots >= 2:
            # sell one lot at the limit, the rest stays with the trade
            e = held[0][0]
            realized += (out_px - e) * M.LOT - cost(e, out_px, M.LOT, 1)
            held[0][1] -= 1
            out_px = None
        trig = (in_px is not None and tr[j] and bc[j] >= in_px) or (in_u is not None and tr[j] and (c[j] - in_u) * d >= 0)
        if trig and in_u is not None:
            in_u = None
        if trig:
            add_ask = M.ask_of(float(a[3][j]))
            n_new = max(1, int(wallet // (add_ask * M.LOT)) - open_lots) if v.get("in_full") else 1
            if (open_lots + n_new) * add_ask * M.LOT <= wallet:
                # the whole position must still fit the day's loss room at one stop price
                pieces = held + [[add_ask, n_new]]
                q = sum(n for _e, n in pieces) * M.LOT
                avg = sum(e * n for e, n in pieces) * M.LOT / q
                fees = sum(cost(e, e, n * M.LOT, n) for e, n in pieces) + realized * 0
                new_stop = M._ceil_tick(avg - (room - realized - fees) / q)
                if new_stop < bc[j]:
                    held.append([add_ask, n_new])
                    stop = max(stop, new_stop)
            n_add = len(held) - 1
            in_px = ask * (1 + v["in_x"] * (n_add + 1)) if n_add < v.get("in_max", 1) and n_add >= 1 else None
            if n_add == 0 and v.get("in_max", 1) > 1:
                in_px = ask * (1 + v["in_x"])
        best_u = max(best_u, c[j]) if d > 0 else min(best_u, c[j])
        if ext:
            peak_b = max(peak_b, bid)
            if v.get("ext_give") and bid <= peak_b - v["ext_give"] * (peak_b - ask):
                px = bid
                break
            if (c[j] - (best_u - d * v["ext_k"] * atr[j])) * d <= 0 or j >= ext_end:
                px = bid
                break
        elif j >= j_n11:
            if v.get("extend") and bid >= ask * (1 + v["ext_x"]) and j < ext_end:
                ext = True
            else:
                px = bid
                break
    if px is None or np.isnan(px):
        px = float(bm[j]) if not np.isnan(bm[j]) else ask
    px = float(px)
    for e, n in held:
        if n > 0:
            realized += (px - e) * n * M.LOT - cost(e, px, n * M.LOT, n)
    return realized, j, px


def side_legs(S, i, j, d, strike, v):
    """SN24 hedge (buy the opposite option) and SN25 short leg (sell a further out-of-the-money option, same side)."""
    net = 0.0
    if v.get("hedge_k") is not None:
        opt = "PE" if d > 0 else "CE"
        k = int(round(S.F["c"][i] / M.STEP) * M.STEP) - d * v["hedge_k"] * M.STEP
        rec = quote(S, k, opt, i)
        if rec is not None:
            e = M.ask_of(float(rec[0][3][i]))
            x = float(rec[4][j]) if rec[6][j] else float(rec[5][j])
            net += (x - e) * M.LOT - cost(e, x, M.LOT, 1)
    if v.get("short_k") is not None:
        opt = "CE" if d > 0 else "PE"
        k = strike + d * v["short_k"] * M.STEP
        rec = quote(S, k, opt, i)
        if rec is not None:
            sell = float(rec[4][i])                     # sold at the bid
            buy = M.ask_of(float(rec[5][j])) if not np.isnan(rec[5][j]) else sell
            net += (sell - buy) * M.LOT - M.charges(buy, sell, M.LOT) - STRESS
    return net


def play_day(S, sigs, v, wallet, full_lots, ctx: Ctx, vol_day: bool):
    loss = v.get("loss_share", 0.2) * wallet
    realized, free, ntr = 0.0, 0, 0
    c, atr = S.F["c"], S.F["atr"]
    for sg in sorted(sigs, key=lambda x: x["i"]):
        i = sg["i"]
        if ntr >= v.get("max_trades", 99):
            break
        if v.get("day_lock") and realized >= v["day_lock"] * wallet:      # SN58: protect a big day (no new trades)
            break
        if i < free or i >= M.EXIT_MIN or sg["expiry"] != S.s["expiry"]:
            continue
        lots = size(S, sg, v, full_lots, ctx, vol_day)
        if v.get("partial") and lots >= 2 and _rng(S.day, i) < v["partial"]:   # SN66: only one lot gets filled
            lots = 1
        strike = sg["strike"] + v.get("offset", {}).get(sg["expert"], 0) * (M.STEP if sg["opt"] == "CE" else -M.STEP)
        if v.get("itm_if_fits"):    # SN19b: one strike in the money when the wallet can pay for every lot there
            casc = v.get("itm_cascade")
            if v.get("itm_auto"):   # SN43: depth by the money behind each lot
                per_lot = wallet / max(1, lots)
                casc = 1 if per_lot < v["itm_auto"][0] else (2 if per_lot < v["itm_auto"][1] else 3)
            if v.get("itm_max"):    # SN60: the deepest in-the-money strike (up to itm_max) whose lots fit a budget share
                casc = v["itm_max"]
            depths = range(casc, 0, -1) if casc else [v.get("itm_depth", 1)]
            for dep in depths:      # SN38: the deepest in-the-money strike (up to itm_cascade) that every lot fits
                k_itm = sg["strike"] - dep * (M.STEP if sg["opt"] == "CE" else -M.STEP)
                r_itm = quote(S, k_itm, sg["opt"], i)
                if r_itm is not None and M.ask_of(float(r_itm[0][3][i])) * M.LOT * lots <= wallet * v.get("itm_share", 1.0):
                    strike = k_itm
                    break
        got = affordable(S, i, strike, sg["opt"], wallet)     # one lot must fit, else one strike further out
        if got is None:
            continue
        rec, ask, strike = got
        lots = min(lots, max(1, int(wallet // (ask * M.LOT))))
        d = 1 if sg["opt"] == "CE" else -1
        vt = v
        if v.get("in_x") and ((v.get("in_vol_only") and not vol_day) or i >= v.get("in_before", 999) or (v.get("in_puts_only") and d > 0)):
            vt = {**v, "in_x": None}
        net, j, px = walk(S, rec, ask, lots, i, min(max(sg["j"], i + 1), M.EXIT_MIN), d, vt, loss + realized, wallet)
        ntr += 1
        net += side_legs(S, i, j, d, strike, v)
        realized += net
        ctx.closed.append((S.day, j, sg["expert"], net / lots))
        free = j + 1
        if loss + realized < loss * 0.05:
            break
        if v.get("second_chance") and net < 0:
            # SN20: the index comes back through the failed entry level in the trade's direction
            level = c[i]
            for k in range(j + 1, min(M.EXIT_MIN - 30, j + 1 + v["sc_win"])):
                if (c[k] - (level + d * v["sc_b"] * atr[k])) * d > 0:
                    got = affordable(S, k, int(round(c[k] / M.STEP) * M.STEP), sg["opt"], wallet)
                    if got is None:
                        break
                    rec2, ask2, _ = got
                    n2, j2, _ = walk(S, rec2, ask2, 1, k, min(k + 45, M.EXIT_MIN), d, v, loss + realized, wallet)
                    realized += n2
                    free = j2 + 1
                    break
            if loss + realized < loss * 0.05:
                break
    return realized


def size(S, sg, v, full, ctx: Ctx, vol_day: bool) -> int:
    if full <= 1:
        return 1
    rule = v.get("size", "vol")
    small = max(1, full // 2)
    if rule == "vol":
        return full if vol_day else small
    if rule == "all":
        return full
    if rule == "oi":        # SN53: option writers' flow at entry agrees with the trade (SN09 OI cache)
        return full if (vol_day and oi_agree(S, sg, v)) else small
    if rule == "oi_or_vol":
        return full if (vol_day or oi_agree(S, sg, v)) else small
    if rule == "puts_full":
        return full if (sg["opt"] == "PE" or vol_day) else small
    if rule in ("adx_hi", "adx_lo"):
        rd = ADX.get(S.day)
        hi = rd is not None and rd["adx"] >= v.get("adx", 30)
        return full if (vol_day and (hi if rule == "adx_hi" else not hi)) else small
    if rule == "equity":    # SN59: the book's own last N trading days net positive
        recent = ctx.day_nets[-v.get("eq_n", 20):]
        return full if (vol_day and sum(recent) > 0) else small
    if rule == "vol_puts":
        return full if (vol_day and sg["opt"] == "PE") else small
    if rule == "iv":   # today's range so far against yesterday's daily ATR scaled to the time of day
        i = sg["i"]
        hi, lo = float(S.F["h"][: i + 1].max()), float(S.F["l"][: i + 1].min())
        a = VOLT.get(S.day, (None, None))[0]
        if not a:
            return small
        iv = (hi - lo) / S.F["c"][i] / (a * ((i + 1) / 375) ** 0.5)
        return full if iv >= v.get("iv_thr", 1.0) else small
    if rule == "iv&vol":
        return full if (vol_day and size(S, sg, {**v, "size": "iv"}, full, ctx, vol_day) == full) else small
    if rule == "am":
        return full if (vol_day and sg["i"] < 165) else small
    if rule == "pm":
        return full if (vol_day and sg["i"] >= 165) else small
    if rule == "hot":       # SN22: the strategy's last N closed trades (per lot) net positive
        past = [n for (_d, _j, e, n) in ctx.closed if e == sg["expert"]][-v.get("hot_n", 10):]
        return full if (vol_day and len(past) >= 3 and sum(past) > 0) else small
    if rule == "gap_with":  # SN23: a big opening gap in the trade's direction
        gap = S.F["gap"]
        d = 1 if sg["opt"] == "CE" else -1
        return full if (vol_day and gap * d >= v.get("gap", 0.004)) else small
    if rule == "gap_against":
        gap = S.F["gap"]
        d = 1 if sg["opt"] == "CE" else -1
        return full if (vol_day and gap * d <= -v.get("gap", 0.004)) else small
    raise ValueError(rule)


VOLT = {}


def vol_table():
    """day -> (yesterday's daily ATR%, median of the prior sessions' ATR% (up to 250)), as sn13.vol_days reads it."""
    import sqlite3
    seen = {}
    for y in YEARS:
        con = sqlite3.connect(f"file:{(B.D.DATASETS[y] / 'breeze.sqlite').as_posix()}?mode=ro", uri=True)
        for st, o, h, l, c in con.execute("SELECT datetime, open, high, low, close FROM candles WHERE kind='index' ORDER BY datetime"):
            b = seen.setdefault(st[:10], [h, l, c])
            b[0], b[1], b[2] = max(b[0], h), min(b[1], l), c
        con.close()
    days = sorted(seen)
    atr, hist, out = None, [], {}
    for k in range(1, len(days)):
        h, l, c = seen[days[k]]
        pc = seen[days[k - 1]][2]
        tr = max(h - l, abs(h - pc), abs(l - pc)) / pc
        atr = tr if atr is None else atr + (tr - atr) / 14
        if k + 1 < len(days):
            if len(hist) >= 60:
                out[days[k + 1]] = (atr, float(np.median(hist[-250:])))
            hist.append(atr)
    return out


def vday_of(day, v):
    a, med = VOLT.get(day, (None, None))
    return a is not None and a >= v.get("vol_ratio", 1.0) * med


def sig_of(Y, day, v):
    books = v.get("books", ("N11",))
    if tuple(books) == ("N11",):
        return Y.sigs("N11").get(day, [])
    seen, out = set(), []
    for b in books:
        for s in Y.sigs(b).get(day, []):
            if s["sig_key"] not in seen:
                seen.add(s["sig_key"])
                out.append(s)
    return out


def run(years, vol, v) -> dict:
    out = {}
    for name, W0, kind, cap in WALLETS:
        ctx = Ctx()
        W, steps, prog = W0, 0, 0.0
        W_end = [W0]
        per = {y: {"net": 0.0, "refilled": 0.0, "won": 0, "lost": 0, "none": 0, "worst": 0.0} for y in YEARS}
        for y in YEARS:
            Y = years[y]
            for S in Y.ordered():
                if kind == "one":
                    full, vday = 1, False
                elif kind == "float":
                    full, vday = 1, vday_of(S.day, v)
                elif kind == "sized":
                    full, vday = 2, vday_of(S.day, v)
                else:
                    full, vday = max(1, int(W // 15000)), vday_of(S.day, v)
                if v.get("from_day") and S.day < v["from_day"]:
                    continue
                if kind == "float":
                    size_w = min(W, v.get("float_cap", 1e18))
                    full = max(1, int(size_w // 15000)) if W >= v.get("float_floor", 7500) else 0
                    if full == 0:
                        ctx.day_nets.append(0.0)
                        per[y]["none"] += 1
                        continue
                x = play_day(S, sig_of(Y, S.day, v), v, min(W, v.get("float_cap", 1e18)) if kind == "float" else W, full, ctx, vday)
                ctx.day_nets.append(x)
                p = per[y]
                p["net"] += x
                p["refilled"] += max(0.0, -x)
                p["won" if x > 0 else "lost" if x < 0 else "none"] += 1
                p["worst"] = min(p["worst"], x)
                if kind == "float":
                    W += x
                    W_end[0] = W
                if kind == "grow":
                    prog += x
                    while prog >= v.get("g_trig", 1.0) * W and steps < cap:
                        prog -= v.get("g_trig", 1.0) * W
                        W *= v.get("g_mult", 1.5)
                        steps += 1
        out[name] = {y: {k: round(val) for k, val in per[y].items()} for y in YEARS}
        if kind == "float":
            out[name]["final_equity"] = {"net": round(W_end[0])}
    return out


def line(name, r) -> str:
    def net(w):
        return sum(r[w][y]["net"] for y in YEARS)
    return f"{name:46s} " + " ".join(f"{w.split()[0]} {net(w):>8}" for w in ("A 15k 1 lot", "B 20k 1 lot", "C 30k sized", "G3 (Gold)", "G5"))


def _old_line(name, r) -> str:
    tot = lambda w: sum(r[w][y]["net"] for y in YEARS)  # noqa: E731
    return (f"{name:44s} " + " ".join(f"{w.split()[0]} {tot(w):>8}" for w in ("A 15k 1 lot", "B 20k 1 lot", "C 30k sized", "G3 (Gold)", "G5")))


def study(tag: str, variants: dict, out_dir: Path) -> dict:
    VOLT.update(vol_table())
    vol = None
    years = {y: B.Year(y) for y in YEARS}
    res = {k: run(years, vol, v) for k, v in variants.items()}
    for k, r in res.items():
        print(line(k, r), flush=True)
    picks = {}
    for w in ("A 15k 1 lot", "B 20k 1 lot", "C 30k sized", "G3 (Gold)"):
        L = loyo({k: {y: {**r[w][y], "green": r[w][y]["won"], "red": r[w][y]["lost"]} for y in YEARS} for k, r in res.items()}, "profit")
        picks[w] = L
        print(f"  held out {w:12s} sum {L['sum']['net']:>8}  (v4: {sum(res['SN Gold v4'][w][y]['net'] for y in YEARS)})  picks",
              [L[y]["pick"][:26] for y in YEARS], flush=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"results-{tag}.json").write_text(json.dumps({"variants": res, "loyo": picks}, indent=1), encoding="utf-8")
    return res

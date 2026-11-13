"""SN92-SN100 shared harness (research only). Built on the SN51 lab (a copy of the frozen v4 harness that reproduces
SN Gold v5 exactly with the V5 variant); the frozen sn-gold/*.py files are never edited or imported for changes.

What this adds to the lab, without changing any of its rules:
  * play_day replacement (`combo_play_day`) that runs Gold alone (parity with the lab), a companion alone, or both in
    one chronological ledger (Gold first; an open companion position is sold at the bid the minute a Gold signal
    arrives; one position at a time; the 20% day room is shared);
  * a single-leg companion trade with index exits (stop / trail / target / VWAP / clock), premium backstop and the
    day stop, sized by lots that fit the wallet;
  * causal day features: yesterday's ADX (Gold-free = ADX < 30), India VIX, futures relative volume, option-implied
    per-minute volatility from the ATM straddle;
  * extra sizing rules for Gold (SN97 futures volume, SN99 setup / cheapness / VIX), routed through the lab's size().
"""
from __future__ import annotations

import bisect
import json
import math
import sqlite3
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
for _p in ("2026-11-13-sn51", "2026-11-12-sn03", "2026-11-12-sn01"):
    sys.path.insert(0, str(FNO / _p))
import lab as L  # noqa: E402
from sn03_run import loyo  # noqa: E402

M = L.M
B = L.B
YEARS = L.YEARS
FLAT = 355                      # 15:10
V5 = {"extend": True, "ext_x": 0.25, "ext_k": 3.0, "itm_if_fits": True, "in_x": None, "in_atr": 1.0, "in_full": True,
      "itm_auto": (17500, 20000), "books": ("N11", "R0.85")}
V5_TOTALS = {"A 15k 1 lot": 151155, "B 20k 1 lot": 176846, "C 30k sized": 280508, "G3 (Gold)": 399906, "G5": 741675}
EXPERTS = ("EFF", "OR20", "SHIPPED", "TPB")
STD_WALLETS = L.WALLETS
BIG_WALLETS = (("A 15k 1 lot", 15000.0, "one", None), ("B 20k 1 lot", 20000.0, "one", None),
               ("C 30k sized", 30000.0, "sized", None), ("G0", 15000.0, "grow", 0), ("G2", 15000.0, "grow", 2),
               ("G3 (Gold)", 15000.0, "grow", 3), ("G5", 15000.0, "grow", 5),
               ("30k fixed", 30000.0, "grow", 0), ("30k grow stop 3", 30000.0, "grow", 3),
               ("30k grow stop 5", 30000.0, "grow", 5), ("20k grow stop 3", 20000.0, "grow", 3),
               ("50k grow stop 3", 50000.0, "grow", 3))

# ---------------------------------------------------------------------------------------------------------------
# loading


_YEARS = None


def years():
    global _YEARS
    if _YEARS is None:
        L.VOLT.update(L.vol_table())
        _YEARS = {y: B.Year(y) for y in YEARS}
        _build_calendar()
        _build_relvol(_YEARS)
    return _YEARS


ADX = json.loads((FNO / "2026-11-12-sn06" / "_local" / "daily.json").read_text(encoding="utf-8"))


def adx(day):
    r = ADX.get(day)
    return None if r is None else r["adx"]


def gold_free(day) -> bool:
    """Causal: yesterday's daily ADX below 30 (Gold's call side and three of four setups are shut)."""
    a = adx(day)
    return a is not None and a < 30


_VIX = json.loads((M.ROOT / "docs/research/simulation/2026-11-05-fno-n12/_local/india-vix/india-vol-closes.json")
                  .read_text(encoding="utf-8"))["closes"]
_VIX_DAYS = sorted(d for d, r in _VIX.items() if r.get("vix"))


def vix_prev(day):
    """(yesterday's India VIX close, median of the 60 closes before it) - known before the open."""
    k = bisect.bisect_left(_VIX_DAYS, day)
    if k < 61:
        return None, None
    last = _VIX[_VIX_DAYS[k - 1]]["vix"]
    med = float(np.median([_VIX[d]["vix"] for d in _VIX_DAYS[k - 61:k - 1]]))
    return last, med


_CAL: list = []


def _build_calendar():
    seen = set()
    for y in YEARS:
        con = sqlite3.connect(f"file:{(B.D.DATASETS[y] / 'breeze.sqlite').as_posix()}?mode=ro", uri=True)
        seen |= {r[0] for r in con.execute("SELECT DISTINCT substr(datetime,1,10) FROM candles WHERE kind='index'")}
        con.close()
    _CAL[:] = sorted(seen)


def sessions_until(day, expiry) -> int:
    """Trading sessions after `day` up to and including `expiry`."""
    a = bisect.bisect_right(_CAL, day)
    b = bisect.bisect_right(_CAL, expiry)
    return max(0, b - a)


REL: dict = {}


def _build_relvol(Ys):
    """rel_vol[day][i] = futures volume of minutes i-14..i / the median of the same window over the prior 20 sessions."""
    hist = []
    for y in YEARS:
        for S in Ys[y].ordered():
            fv = np.nan_to_num(S.F["fv"])
            cs = np.concatenate([[0.0], np.cumsum(fv)])
            wv = np.array([cs[i + 1] - cs[max(0, i - 14)] for i in range(len(fv))])
            if len(hist) >= 20:
                med = np.median(np.vstack(hist[-20:]), axis=0)
                REL[S.day] = np.where(med > 0, wv / np.maximum(med, 1.0), np.nan)
            hist.append(wv)


def rel_vol(day, i):
    r = REL.get(day)
    return None if r is None or np.isnan(r[i]) else float(r[i])


# ---------------------------------------------------------------------------------------------------------------
# option-implied volatility from the ATM straddle (SN95 / SN99)

OVERNIGHT_MIN = 125.0


def leg_mark(S, strike, opt, i):
    rec = S.option(strike, opt)
    if rec is None:
        return None
    a = rec[0]
    col = a[3][: i + 1]
    ok = np.flatnonzero(~np.isnan(col))
    if len(ok) == 0 or i - ok[-1] > 5:      # a stale mark (no print in 5 minutes) is no price
        return None
    return float(col[ok[-1]])


def sigma_imp(S, i):
    c = S.F["c"][i]
    K = int(round(c / M.STEP) * M.STEP)
    ce, pe = leg_mark(S, K, "CE", i), leg_mark(S, K, "PE", i)
    if ce is None or pe is None:
        return None
    F = float(S.s["future"][3][i])
    n = sessions_until(S.day, S.s["expiry"])
    tau = (375 - (i + 1)) + 375.0 * n + OVERNIGHT_MIN * n
    if tau <= 0:
        return None
    return (ce + pe) / (0.7979 * F * math.sqrt(tau))


def r_today(S, i):
    si = sigma_imp(S, i)
    if si is None or i < 20:
        return None
    c = S.F["c"][5: i + 1]
    r = np.diff(np.log(c))
    return float(np.std(r)) / si if len(r) > 5 else None


def r_atr(S, i):
    si = sigma_imp(S, i)
    a = L.VOLT.get(S.day, (None, None))[0]
    if si is None or not a:
        return None
    return a / (1.6 * math.sqrt(375.0)) / si


# ---------------------------------------------------------------------------------------------------------------
# Gold: one signal, exactly the lab's per-signal body (parity proven by combo_play_day == lab.play_day)

def gold_one(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss):
    i = sg["i"]
    lots = L.size(S, sg, v, full_lots, ctx, vol_day)
    if v.get("partial") and lots >= 2 and L._rng(S.day, i) < v["partial"]:
        lots = 1
    if v.get("drop") and sg["expert"] in v["drop"]:
        return None
    strike = sg["strike"] + v.get("offset", {}).get(sg["expert"], 0) * (M.STEP if sg["opt"] == "CE" else -M.STEP)
    if v.get("itm_if_fits"):
        casc = v.get("itm_cascade")
        if v.get("itm_auto"):
            per_lot = wallet / max(1, lots)
            casc = 1 if per_lot < v["itm_auto"][0] else (2 if per_lot < v["itm_auto"][1] else 3)
        if v.get("itm_max"):
            casc = v["itm_max"]
        depths = range(casc, 0, -1) if casc else [v.get("itm_depth", 1)]
        for dep in depths:
            k_itm = sg["strike"] - dep * (M.STEP if sg["opt"] == "CE" else -M.STEP)
            r_itm = L.quote(S, k_itm, sg["opt"], i)
            if r_itm is not None and M.ask_of(float(r_itm[0][3][i])) * M.LOT * lots <= wallet * v.get("itm_share", 1.0):
                strike = k_itm
                break
    got = L.affordable(S, i, strike, sg["opt"], wallet)
    if got is None:
        return None
    rec, ask, strike = got
    lots = min(lots, max(1, int(wallet // (ask * M.LOT))))
    d = 1 if sg["opt"] == "CE" else -1
    vt = v
    if v.get("in_x") and ((v.get("in_vol_only") and not vol_day) or i >= v.get("in_before", 999) or (v.get("in_puts_only") and d > 0)):
        vt = {**v, "in_x": None}
    if v.get("late"):                       # robustness: the entry 1 minute late (signal unchanged)
        i2 = i + v["late"]
        rec2 = L.quote(S, strike, sg["opt"], i2) if i2 < M.EXIT_MIN else None
        if rec2 is None:
            return None
        ask = M.ask_of(float(rec2[0][3][i2]))
        if ask * M.LOT > wallet:
            return None
        lots = min(lots, max(1, int(wallet // (ask * M.LOT))))
        i = i2
    net, j, px = L.walk(S, rec, ask, lots, i, min(max(sg["j"], i + 1), M.EXIT_MIN), d, vt, loss + realized, wallet)
    net += L.side_legs(S, i, j, d, strike, v)
    return net, j, lots, ask, px, strike


# ---------------------------------------------------------------------------------------------------------------
# companion: one single-leg trade with index exits

def comp_one(S, i, d, ex, wallet, lots, room, stop_at=None, stress=None, extra=None):
    """Buy the ATM option at minute i (+ex['delay']) in direction d; exit by the rules in `ex`. Returns
    (net, j, forced) or None when nothing could be bought or the stop does not fit the room."""
    stress = L.STRESS if stress is None else stress
    e = i + ex.get("delay", 0)
    if e >= FLAT or (stop_at is not None and e >= stop_at):
        return None
    c, atr, vwap = S.F["c"], S.F["atr"], S.F["vwap"]
    opt = "CE" if d > 0 else "PE"
    strike = int(round(c[e] / M.STEP) * M.STEP) + d * ex.get("offset", 0) * M.STEP
    rec = None
    for attempt in range(2):
        rec = S.option(strike, opt)
        if rec is None or not rec[6][e]:
            return None
        ask = M.ask_of(float(rec[0][3][e]))
        if ask * M.LOT <= wallet:
            break
        if attempt:
            return None
        strike += M.STEP * d
    lots = max(1, min(lots, int(wallet // (ask * M.LOT))))
    a, b_open, b_high, b_low, b_close, b_mark, traded = rec
    while lots >= 1:
        qty = lots * M.LOT
        est = M.charges(ask, ask, qty) + stress * lots
        prem_stop = max(M._ceil_tick(ask * (1 - ex.get("backstop", 0.25))), M._ceil_tick(ask - (room - est) / qty))
        if (ask - prem_stop) * qty + est <= room + 1e-6 and prem_stop < ask:
            break
        lots -= 1
    if lots < 1:
        return None
    qty = lots * M.LOT
    u0 = c[e]
    xs = extra or {}
    u_stop = xs.get("stop", u0 - d * ex.get("stop_k", 4.0) * atr[e])
    u_tgt = xs.get("target")
    best = u0
    px, j, forced = None, e, False
    for j in range(e + 1, FLAT + 1):
        if stop_at is not None and j >= stop_at:
            px, forced = (b_close[j] if traded[j] else b_mark[j]), True
            break
        if traded[j] and b_low[j] <= prem_stop:
            px = min(prem_stop, b_open[j])
            break
        u = c[j]
        best = max(best, u) if d > 0 else min(best, u)
        level = u_stop
        if ex.get("trail_k"):
            t = best - d * ex["trail_k"] * atr[j]
            level = max(level, t) if d > 0 else min(level, t)
        bid = b_close[j] if traded[j] else b_mark[j]
        if (u - level) * d <= 0:
            px = bid
            break
        if u_tgt is not None and (u - u_tgt) * d >= 0:
            px = bid
            break
        if ex.get("vwap_exit") and j % 15 == 14 and (u - vwap[j]) * d < 0:
            px = bid
            break
        if j - e >= ex.get("time", 400) or j >= FLAT:
            px = bid
            break
    if px is None or np.isnan(px):
        px = float(b_mark[j]) if not np.isnan(b_mark[j]) else ask
    px = float(px)
    net = (px - ask) * qty - M.charges(ask, px, qty) - stress * lots
    return net, j, forced


# ---------------------------------------------------------------------------------------------------------------
# the day player (replaces lab.play_day through `install()`)

TRADES: list = []          # filled when RECORD[0] is True: one dict per trade (SN92)
RECORD = [False]


def _comp_cfg(v, day):
    cfg = v.get("comp")
    by = v.get("comp_by_year")
    if by is not None:
        cfg = by.get(day[:4])
    return cfg


def combo_play_day(S, sigs, v, wallet, full_lots, ctx, vol_day):
    mode = v.get("mode", "gold")
    loss = v.get("loss_share", 0.2) * wallet
    realized, free, ntr = 0.0, 0, 0
    gold = sorted(sigs, key=lambda x: x["i"]) if mode != "comp" else []
    cfg = _comp_cfg(v, S.day) if mode != "gold" else None
    csig, cext = (None, {})
    if cfg is not None:
        got = cfg["sig"](S)
        if got is not None:
            csig, cext = got
    cidx = np.flatnonzero(csig) if csig is not None else np.array([], int)
    ctr, gk = 0, 0
    while True:
        while gk < len(gold) and (gold[gk]["i"] < free or gold[gk]["i"] >= M.EXIT_MIN or gold[gk]["expiry"] != S.s["expiry"]):
            gk += 1
        g_i = gold[gk]["i"] if gk < len(gold) else None
        c_i = None
        if cfg is not None and ctr < cfg.get("max_trades", 1):
            k = np.searchsorted(cidx, free)
            if k < len(cidx) and cidx[k] <= cfg.get("last_entry", 300):
                c_i = int(cidx[k])
        if g_i is None and c_i is None:
            break
        if g_i is not None and (c_i is None or g_i <= c_i):
            sg = gold[gk]
            gk += 1
            if ntr >= v.get("max_trades", 99):
                break
            if v.get("day_lock") and realized >= v["day_lock"] * wallet:
                break
            res = gold_one(S, sg, v, wallet, full_lots, ctx, vol_day, realized, loss)
            if res is None:
                continue
            net, j, lots, ask, px, strike = res
            ntr += 1
            realized += net
            ctx.closed.append((S.day, j, sg["expert"], net / lots))
            if RECORD[0]:
                TRADES.append({"day": S.day, "who": "gold", "expert": sg["expert"], "book": sg["book"], "opt": sg["opt"],
                               "i": sg["i"], "j": j, "j_n11": sg["j"], "lots": lots, "ask": ask, "px": px,
                               "strike": strike, "net": net, "wallet": wallet})
            free = j + 1
            if loss + realized < loss * 0.05:
                break
        else:
            lots = 1 if cfg.get("size", "one") == "one" else (full_lots if vol_day else max(1, full_lots // 2))
            res = comp_one(S, c_i, int(csig[c_i]), cfg["ex"], wallet, lots, loss + realized, stop_at=g_i,
                           stress=cfg.get("stress"), extra=cext.get(c_i))
            if res is None:
                free = c_i + 1
                continue
            net, j, forced = res
            ctr += 1
            realized += net
            if RECORD[0]:
                TRADES.append({"day": S.day, "who": "comp", "i": c_i, "j": j, "dir": int(csig[c_i]), "net": net,
                               "forced": forced, "wallet": wallet})
            free = j if forced else j + 1
            if loss + realized < loss * 0.05:
                break
    return realized


_orig_size = L.size


def size_ext(S, sg, v, full, ctx, vol_day):
    rule = v.get("size", "vol")
    if full <= 1 or rule in ("vol", "all", "oi", "oi_or_vol", "puts_full", "adx_hi", "adx_lo", "equity", "vol_puts",
                             "iv", "iv&vol", "am", "pm", "hot", "gap_with", "gap_against"):
        return _orig_size(S, sg, v, full, ctx, vol_day)
    small = max(1, full // 2)
    if rule == "single":                            # SN99: one (deep) lot every day
        return 1
    if rule.startswith("rv"):                       # SN97: futures volume before the entry
        r = rel_vol(S.day, sg["i"])
        hot = r is not None and r >= v["rv_x"]
        ok = {"rv": hot, "rv_and_vol": hot and vol_day, "rv_or_vol": hot or vol_day}[rule]
        return full if ok else small
    if rule == "setup":                             # SN99: full lots only for chosen setups (volatility days)
        return full if (vol_day and sg["expert"] in v["full_for"]) else small
    if rule in ("cheap_hi", "cheap_lo", "cheap_hi&vol", "cheap_lo&vol"):
        r = r_today(S, sg["i"])
        med = v["cheap_med"]
        ok = r is not None and ((r >= med) if "hi" in rule else (r <= med))
        if rule.endswith("&vol"):
            ok = ok and vol_day
        return full if ok else small
    if rule in ("vix_hi&vol", "vix_lo&vol"):
        last, med = vix_prev(S.day)
        ok = last is not None and ((last >= med) if "hi" in rule else (last <= med))
        return full if (ok and vol_day) else small
    raise ValueError(rule)


def install():
    L.play_day = combo_play_day
    L.size = size_ext


def run(v, wallets=STD_WALLETS):
    install()
    old = L.WALLETS
    L.WALLETS = wallets
    try:
        return L.run(years(), None, v)
    finally:
        L.WALLETS = old


def totals(r):
    return {w: sum(r[w][y]["net"] for y in YEARS) for w in r if isinstance(r[w], dict) and "2023" in r[w]}


def panel(r):
    """Per wallet: by-year net, won, refilled, net at the end, days won/lost/none, worst day."""
    out = {}
    for w, per in r.items():
        if "2023" not in per:
            continue
        won = sum(per[y]["net"] + per[y]["refilled"] for y in YEARS)
        ref = sum(per[y]["refilled"] for y in YEARS)
        out[w] = {"by_year": [per[y]["net"] for y in YEARS], "won": won, "refilled": ref, "net": won - ref,
                  "w/l/none": [sum(per[y][k] for y in YEARS) for k in ("won", "lost", "none")],
                  "worst": min(per[y]["worst"] for y in YEARS), "losing_years": sum(per[y]["net"] < 0 for y in YEARS)}
    return out


def loyo_wallet(res: dict, w: str) -> dict:
    tab = {k: {y: {**r[w][y], "green": r[w][y]["won"], "red": r[w][y]["lost"]} for y in YEARS} for k, r in res.items()}
    return loyo(tab, "profit")


# ---------------------------------------------------------------------------------------------------------------
# standalone companion tables (1 lot at Rs 15k, Rs 3k room - the SN80 convention) for the LOYO contests

def comp_table(sig_fn, ex, day_ok=gold_free, wallet=15000.0, room=3000.0, stress=None, max_trades=1, last_entry=300,
               delay=0):
    Ys = years()
    per = {}
    exd = {**ex, "delay": delay}
    for y in YEARS:
        nets, trades = [], 0
        for S in Ys[y].ordered():
            if not day_ok(S.day):
                continue
            got = sig_fn(S)
            realized, n, free = 0.0, 0, 0
            if got is not None:
                sig, ext = got
                idx = np.flatnonzero(sig)
                for i in idx:
                    if n >= max_trades or i > last_entry:
                        break
                    if i < free:
                        continue
                    res = comp_one(S, int(i), int(sig[i]), exd, wallet, 1, room + realized, stress=stress, extra=ext.get(int(i)))
                    if res is None:
                        continue
                    net, j, _ = res
                    realized += net
                    n += 1
                    free = j + 1
                    if room + realized < room * 0.05:
                        break
            trades += n
            nets.append(realized)
        per[y] = {"net": round(sum(nets)), "green": sum(x > 0 for x in nets), "red": sum(x < 0 for x in nets),
                  "none": sum(x == 0 for x in nets), "refilled": round(sum(-x for x in nets if x < 0)), "days": len(nets),
                  "trades": trades}
    return per


def tot(per):
    return sum(per[y]["net"] for y in YEARS)


# ---------------------------------------------------------------------------------------------------------------
# a companion contest: the fixed grid, its controls, leave one year out, robustness and every wallet

def contest(real: dict, controls: dict, day_ok=gold_free, max_trades=1, last_entry=300, wallets=STD_WALLETS):
    """real / controls[group]: {name: (sig_fn, ex)}. Returns tables, LOYO per group, the picks' robustness, the
    held-out picks run as a companion alone at every wallet, and the verdict of PLAN.md's companion pass rule."""
    def tab(group):
        return {k: comp_table(f, ex, day_ok, max_trades=max_trades, last_entry=last_entry) for k, (f, ex) in group.items()}
    out = {"real": tab(real), "controls": {g: tab(grp) for g, grp in controls.items()}}
    Lr = loyo(out["real"], "profit")
    out["loyo_real"] = Lr
    out["loyo_controls"] = {g: loyo(t, "profit") for g, t in out["controls"].items()}
    rob = {}
    for label, kw in (("stress 400", {"stress": 400.0}), ("1 minute late", {"delay": 1})):
        s = 0
        for y in YEARS:
            f, ex = real[Lr[y]["pick"]]
            s += comp_table(f, ex, day_ok, max_trades=max_trades, last_entry=last_entry, **kw)[y]["net"]
        rob[label] = s
    out["robust"] = rob
    def gated(f):
        return lambda S: f(S) if day_ok(S.day) else None
    by_year = {y: {"sig": gated(real[Lr[y]["pick"]][0]), "ex": real[Lr[y]["pick"]][1], "max_trades": max_trades,
                   "last_entry": last_entry, "size": "gold"} for y in YEARS}
    out["by_year_cfg"] = by_year
    w = run({**V5, "mode": "comp", "comp_by_year": {y: {**c} for y, c in by_year.items()}}, wallets)
    out["wallets_heldout_picks"] = panel(w)
    held = [Lr[y]["net"] for y in YEARS]
    beats = {g: Lr["sum"]["net"] > L_["sum"]["net"] for g, L_ in out["loyo_controls"].items()}
    ok = Lr["sum"]["net"] > 0 and sum(x > 0 for x in held) >= 3 and all(beats.values()) and all(v > 0 for v in rob.values())
    out["verdict"] = {"held_out_sum": Lr["sum"]["net"], "held_out_years": held, "beats_controls": beats,
                      "robust": rob, "PASS": ok}
    return out


def show_contest(name, res):
    print(f"=== {name}")
    for k, per in sorted(res["real"].items(), key=lambda kv: -tot(kv[1]))[:8]:
        print(f"  {k:40s} {[per[y]['net'] for y in YEARS]} sum {tot(per):>8} won/lost {sum(per[y]['green'] for y in YEARS)}/"
              f"{sum(per[y]['red'] for y in YEARS)} trades {sum(per[y]['trades'] for y in YEARS)}", flush=True)
    Lr = res["loyo_real"]
    print("  LOYO real picks", {y: (Lr[y]["pick"], Lr[y]["net"]) for y in YEARS}, "sum", Lr["sum"]["net"])
    for g, L_ in res["loyo_controls"].items():
        print(f"  LOYO {g:22s} sum {L_['sum']['net']:>8}", {y: L_[y]["net"] for y in YEARS})
    print("  robustness of the held-out picks", res["robust"])
    for w, p in res["wallets_heldout_picks"].items():
        print(f"  wallet {w:16s} net {p['net']:>8} by year {p['by_year']} refilled {p['refilled']} w/l/none {p['w/l/none']} worst {p['worst']}")
    print("  VERDICT", res["verdict"], flush=True)


def jsonable(x):
    if callable(x):
        return getattr(x, "__name__", "fn")
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return float(x)
    return x

"""SN161-SN185 shared helpers: the daily wage (PLAN.md). Imports the SN lab through SN151's ph (fill model, charges,
stops and Gold v5 parity proven upstream); edits nothing.

  * the split: TEST = the latest 5% of the 742 sessions (2026-08-20 ... 2026-10-28), DEVELOPMENT = the rest;
  * trade(): one long option position (max lots for the wallet unless fixed) with a net target (limit on the bid high),
    a net stop (stop on the bid low, ties go to the stop, gap-through fills at the open) and a clock exit;
  * spread_trade(): a 1:1 debit spread with the same exits on its executable value;
  * play(): a day of up to `attempts` positions from a picker, with the wage lock (stop at +wage) and the day limit;
  * pickers: random (the null), 15-minute range break;
  * wage_stats(): wage / red / flat days, monthly sums, per year."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn151"))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn116"))
import ph  # noqa: E402

pa, pb = ph.pa, ph.pb
C, M = ph.C, ph.M
L = C.L
TEST_FROM = "2026-08-20"
FLAT = C.FLAT                    # 15:10
I_MIN, I_MAX = 15, 315           # 09:30 ... 14:30: entry window
LOT = M.LOT
STEP = M.STEP
STRESS = 205.0
TICK = 0.05
DEV_YEARS = ("2023", "2024", "2025", "2026")

_SESS = None


def sessions():
    global _SESS
    if _SESS is None:
        _SESS = ph.sessions()
    return _SESS


def is_test(day: str) -> bool:
    return day >= TEST_FROM


def dev_sessions():
    return [S for S in sessions() if not is_test(S.day)]


def test_sessions():
    return [S for S in sessions() if is_test(S.day)]


def atm(S, i) -> int:
    return int(round(S.F["c"][i] / STEP) * STEP)


def _floor_tick(x):
    return round(math.floor(x / TICK + 1e-9) * TICK, 2)


def _ceil_tick(x):
    return round(math.ceil(x / TICK - 1e-9) * TICK, 2)


def price_for_net(ask, qty, lots, net, stress, up=True):
    """The bid at which selling ``qty`` bought at ``ask`` nets ``net`` after charges and stress."""
    p = ask + (net + stress * lots) / qty
    for _ in range(3):
        p = ask + (net + stress * lots + M.charges(ask, max(p, TICK), qty)) / qty
    return _ceil_tick(p) if up else _floor_tick(p)


def net_at(ask, px, qty, lots, stress):
    return (px - ask) * qty - M.charges(ask, px, qty) - stress * lots


def lots_for(ask, wallet, max_lots=None):
    n = int(wallet // (ask * LOT))
    return min(n, max_lots) if max_lots else n


def trade(S, i, opt, strike, wallet, target=None, stop=None, end=FLAT, stress=STRESS, max_lots=None, late=0,
          lots=None, record_path=False):
    """One long option bought at minute i (+late) at the ask. Returns dict(net, j, reason, lots, ask[, peak]) or None."""
    e = i + late
    if e >= end:
        return None
    rec = S.option(strike, opt)
    if rec is None or not rec[6][e]:
        return None
    ask = M.ask_of(float(rec[0][3][e]))
    n = lots if lots is not None else lots_for(ask, wallet, max_lots)
    if n < 1 or ask * LOT * n > wallet + 1e-6:
        return None
    qty = n * LOT
    tp = price_for_net(ask, qty, n, target, stress, up=True) if target is not None else None
    sp = price_for_net(ask, qty, n, stop, stress, up=False) if stop is not None else None
    if sp is not None and sp < TICK:
        sp = None
    _a, bo, bh, bl, bc, bm, tr = rec
    px, reason, j, peak = None, "time", e, -math.inf
    for j in range(e + 1, end + 1):
        if tr[j]:
            if sp is not None and bl[j] <= sp:
                px, reason = min(sp, float(bo[j])), "stop"
                break
            if tp is not None and bh[j] >= tp:
                px, reason = tp, "target"
                break
            if record_path:
                peak = max(peak, float(bh[j]))
        if j == end:
            px = float(bc[j]) if tr[j] else float(bm[j])
    if px is None or px != px:
        px = float(bm[j]) if bm[j] == bm[j] else ask
    out = {"net": net_at(ask, px, qty, n, stress), "j": j, "reason": reason, "lots": n, "ask": ask}
    if record_path:
        out["peak"] = net_at(ask, max(peak, px), qty, n, stress) if peak > -math.inf else out["net"]
    return out


def spread_trade(S, i, d, wallet, width=2, target=None, stop=None, end=FLAT, stress_leg=100.0, max_lots=None, late=0):
    """Debit spread: buy ATM, sell ATM + width steps (CE up / PE down). Value = long bid - short ask."""
    e = i + late
    if e >= end:
        return None
    opt = "CE" if d > 0 else "PE"
    k1 = atm(S, e)
    k2 = k1 + d * width * STEP
    r1, r2 = S.option(k1, opt), S.option(k2, opt)
    if r1 is None or r2 is None or not r1[6][e] or not r2[6][e]:
        return None
    a1 = M.ask_of(float(r1[0][3][e]))
    b2 = M.bid_of(float(r2[0][3][e]))
    debit = a1 - b2
    if debit <= TICK:
        return None
    n = int(wallet // (debit * LOT))
    if max_lots:
        n = min(n, max_lots)
    if n < 1:
        return None
    qty = n * LOT
    stress = 2 * stress_leg * n

    def value_net(v1, v2):
        return (v1 - a1) * qty + (b2 - v2) * qty - M.charges(a1, v1, qty) - M.charges(v2, b2, qty) - stress
    last, raw2 = None, float(r2[0][3][e])
    for j in range(e + 1, end + 1):
        p1 = float(r1[4][j]) if r1[6][j] else float(r1[5][j])                  # long leg bid (mark carried)
        if r2[6][j]:
            raw2 = float(r2[0][3][j])                                          # short leg: last printed close
        p2 = M.ask_of(raw2)                                                    # bought back at the ask
        if p1 != p1:
            continue
        v = value_net(p1, p2)
        if stop is not None and v <= stop:
            return {"net": v, "j": j, "reason": "stop", "lots": n, "ask": debit}
        if target is not None and v >= target:
            return {"net": v, "j": j, "reason": "target", "lots": n, "ask": debit}
        last = (v, j)
    if last is None:                       # unreachable when both legs printed at entry (marks carry forward)
        return None
    return {"net": last[0], "j": last[1], "reason": "time", "lots": n, "ask": debit}


def play(S, picker, wallet, wage, stop, attempts=1, day_limit=None, stress=STRESS, end=FLAT, max_lots=None,
         late=0, shape=None):
    """A day of up to ``attempts`` positions. ``picker(S, from_minute, realized)`` -> (i, opt, strike) or None.
    Each position's target is the rest of the wage (wage - realized); its stop is min(|stop|, the day's room).
    ``shape`` (optional) replaces trade(): shape(S, i, opt, strike, wallet, target, stop) -> dict or None."""
    day_limit = 2.0 * wage if day_limit is None else day_limit
    realized, k, i0, trades = 0.0, 0, I_MIN, []
    while k < attempts and realized < wage - 1e-6 and realized > -day_limit + 1e-6 and i0 <= I_MAX:
        got = picker(S, i0, realized)
        if got is None:
            break
        i, opt, strike = got
        room = day_limit + realized
        st = -min(abs(stop), room)
        tgt = wage - realized
        if shape is None:
            r = trade(S, i, opt, strike, wallet, target=tgt, stop=st, end=end, stress=stress, max_lots=max_lots, late=late)
        else:
            r = shape(S, i, opt, strike, wallet, tgt, st)
        k += 1
        if r is None:
            i0 = i + 1
            continue
        realized += r["net"]
        trades.append({**r, "i": i, "opt": opt, "strike": strike})
        i0 = r["j"] + 1
    return realized, trades


# ---------------------------------------------------------------------------------------------------------------
# pickers

def random_picker(seed, offset=0):
    rng = np.random.default_rng(seed)

    def pick(S, i0, realized):
        lo = max(i0, I_MIN)
        if lo > I_MAX:
            return None
        i = int(rng.integers(lo, I_MAX + 1))
        d = 1 if rng.random() < 0.5 else -1
        opt = "CE" if d > 0 else "PE"
        return i, opt, atm(S, i) + d * offset * STEP
    return pick


def range_break_picker(n=15, offset=0, last=I_MAX):
    """First close beyond the first n minutes' range after it forms: CE up, PE down."""
    def pick(S, i0, realized):
        F = S.F
        hi, lo = float(np.max(F["h"][:n])), float(np.min(F["l"][:n]))
        c = F["c"]
        for i in range(max(i0, n), last + 1):
            if c[i] > hi and c[i - 1] <= hi:
                return i, "CE", atm(S, i) + offset * STEP
            if c[i] < lo and c[i - 1] >= lo:
                return i, "PE", atm(S, i) - offset * STEP
        return None
    return pick


def seed_of(day: str, draw: int = 0, salt: int = 0) -> int:
    return int(day.replace("-", "")) * 1000 + draw * 7 + salt


# ---------------------------------------------------------------------------------------------------------------
# metrics

def wage_stats(day_nets: dict, days, wallet, wage=None):
    """day_nets: {day: net} (days absent = no trade). ``days``: the calendar scored."""
    wage = 0.10 * wallet if wage is None else wage
    days = list(days)
    x = np.array([float(day_nets.get(d, 0.0)) for d in days])
    traded = np.array([d in day_nets for d in days])
    months = {}
    for d, v in zip(days, x):
        months.setdefault(d[:7], []).append(v)
    msum = np.array([sum(v) for v in months.values()]) if months else np.array([0.0])
    mwage = np.array([sum(1 for t in v if t >= wage - 1e-6) for v in months.values()]) if months else np.array([0])
    by_year = {}
    for y in DEV_YEARS:
        m = np.array([d[:4] == y for d in days])
        if m.any():
            by_year[y] = {"net": round(float(x[m].sum())), "wage_days": int((x[m] >= wage - 1e-6).sum()),
                          "red_days": int((x[m] < 0).sum()), "sessions": int(m.sum())}
    return {"sessions": len(days), "trade_days": int(traded.sum()), "wage_days": int((x >= wage - 1e-6).sum()),
            "wage_share": round(float((x >= wage - 1e-6).mean()), 4) if len(x) else 0.0,
            "red_days": int((x < 0).sum()), "net": round(float(x.sum())),
            "per_session": round(float(x.mean()), 1) if len(x) else 0.0,
            "month": {"n": len(msum), "mean": round(float(msum.mean())), "median": round(float(np.median(msum))),
                      "worst": round(float(msum.min())), "best": round(float(msum.max())),
                      "wage_days_mean": round(float(mwage.mean()), 1)},
            "worst_day": round(float(x.min())) if len(x) else 0, "by_year": by_year}


def null_stats(run_draw, days, wallet, wage, draws=20):
    """Mean statistics of ``draws`` random replays; run_draw(draw) -> {day: net}."""
    shares, nets, per = [], [], []
    for k in range(draws):
        dn = run_draw(k)
        s = wage_stats(dn, days, wallet, wage)
        shares.append(s["wage_share"])
        nets.append(s["net"])
    return {"draws": draws, "wage_share_mean": round(float(np.mean(shares)), 4), "net_mean": round(float(np.mean(nets))),
            "net_p5": round(float(np.percentile(nets, 5))), "net_p95": round(float(np.percentile(nets, 95)))}

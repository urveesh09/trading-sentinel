"""SN01 simulator - a small fixed wallet that buys NIFTY weekly options for a daily target (research only).

The owner's SN01 idea (Nov 12, 2026), as rules:
  * a fixed wallet W (Rs 15,000 at the start); profits are banked, never traded; a losing day is refilled;
  * the day stops when the day's net profit after charges reaches the target T (10% of the starting wallet),
    or when the day's net loss reaches L = 20% of the current wallet;
  * many small trades are allowed (quick entry, quick exit); one position at a time; options are bought only
    (Rs 15,000 cannot carry futures or short options).

This module runs ONE session for one genome on the minute grid of ``sn01_data``. It is causal: a decision at minute i
reads only minutes <= i of the session and earlier sessions, and its fill is at minute i's close.

Fill model (declared before scoring; conservative where the candle hides the order of events):
  * entry: buy at the ask (close + half the archive's 75th-percentile spread) of the signal minute, only if the
    contract printed a candle that minute;
  * a stop is a stop-market: it triggers when the minute's low reaches it (at the bid) and fills at the stop or at the
    minute's open if the market opened through it;
  * a target is a sell limit: it fills when the minute's high reaches it at the bid, at the target (or at the open if
    the market opened through it);
  * if a stop and a target are both reached in the same minute, the stop is taken;
  * the time stop and the 15:15 exit sell at the minute's close bid;
  * charges: the shipped round-trip model (``fno_costs``, today's NFO rates, STT 0.15%) on every trade, plus an
    optional stress of extra rupees per lot per trade (``stress``), because candles flatter fills.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
sys.path[:0] = [str(ROOT / "python-engine")]

LOT = 65
STEP = 50
TICK = 0.05
EXIT_MIN = 360          # 15:15 - every position is closed at this minute's close
SPREAD_P75 = ((50.0, 0.10), (100.0, 0.20), (150.0, 0.30), (200.0, 0.45), (300.0, 0.60), (450.0, 0.80))
SPREAD_ABOVE_PCT = 0.002

_SNAPSHOT = None


def cost_snapshot() -> dict:
    global _SNAPSHOT
    if _SNAPSHOT is None:
        from cost_schedules import options_cost_snapshot
        _SNAPSHOT = options_cost_snapshot("NFO")
    return _SNAPSHOT


def charges(entry: float, exit_: float, qty: int, _calc=[]) -> float:
    if not _calc:
        from fno_costs import calc_fno_costs_from_snapshot
        _calc.append(calc_fno_costs_from_snapshot)
    return _calc[0](entry, exit_, qty, cost_snapshot())


def spread_for(premium: float) -> float:
    for below, spread in SPREAD_P75:
        if premium < below:
            return spread
    return max(SPREAD_P75[-1][1], round(SPREAD_ABOVE_PCT * premium / TICK) * TICK)


def bid_of(price: float) -> float:
    half = spread_for(price) / 2
    return round(max(TICK, math.floor((price - half) / TICK + 1e-9) * TICK), 2)


def ask_of(price: float) -> float:
    half = spread_for(price) / 2
    bid = max(TICK, math.floor((price - half) / TICK + 1e-9) * TICK)
    return round(max(bid + TICK, math.ceil((price + half) / TICK - 1e-9) * TICK), 2)


def _ceil_tick(x: float) -> float:
    return round(math.ceil(x / TICK - 1e-9) * TICK, 2)


def _bid_vec(a: np.ndarray) -> np.ndarray:
    a = np.asarray(a, dtype=np.float64)
    sp = np.select([a < 50, a < 100, a < 150, a < 200, a < 300, a < 450],
                   [0.10, 0.20, 0.30, 0.45, 0.60, 0.80],
                   np.maximum(0.80, np.round(SPREAD_ABOVE_PCT * np.nan_to_num(a) / TICK) * TICK))
    return np.maximum(TICK, np.floor((a - sp / 2) / TICK + 1e-9) * TICK)


# ---- features --------------------------------------------------------------------------------------------------

def _ema(x: np.ndarray, n: int) -> np.ndarray:
    out = np.empty_like(x)
    k = 2.0 / (n + 1)
    acc = x[0]
    for i in range(len(x)):
        acc = x[i] * k + acc * (1 - k)
        out[i] = acc
    return out


def features(s: dict) -> dict:
    """Causal per-minute features of one session (index prices, the future's volume and VWAP)."""
    o, h, l, c = (np.asarray(s["index"][k], dtype=np.float64) for k in range(4))
    fo, fh, fl, fc, fv = (np.asarray(s["future"][k], dtype=np.float64) for k in range(5))
    n = len(c)
    pdc = s["prev"][3] if s.get("prev") else o[0]
    prev_c = np.concatenate([[pdc], c[:-1]])
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    tr[0] = h[0] - l[0]
    atr = np.empty(n)
    acc = max(tr[: 5].mean(), 1.0)
    for i in range(n):
        acc = acc + (tr[i] - acc) / 14.0
        atr[i] = acc
    tp = (fh + fl + fc) / 3.0
    cv = np.cumsum(fv)
    fvwap = np.where(cv > 0, np.cumsum(tp * fv) / np.maximum(cv, 1.0), fc)
    vwap = fvwap - (fc - c)                       # the future's VWAP in index points
    F = {"o": o, "h": h, "l": l, "c": c, "atr": atr, "vwap": vwap, "fv": fv}
    for k in (5, 9, 13, 21, 34, 50):
        F[f"ema{k}"] = _ema(c, k)
    for N in (5, 10, 15, 30):
        orh = np.full(n, np.nan)
        orl = np.full(n, np.nan)
        orh[N:] = h[:N].max()
        orl[N:] = l[:N].min()
        F[f"orh{N}"], F[f"orl{N}"] = orh, orl
    prev = s.get("prev") or (o[0], o[0], o[0], o[0])
    F["pdh"], F["pdl"], F["pdc"] = prev[1], prev[2], prev[3]
    closes = [d[3] for d in s.get("prev_days") or []]
    if len(closes) >= 10:
        e = closes[0]
        for x in closes:
            e = x * (2 / 21) + e * (1 - 2 / 21)
        F["daily_dir"] = 1 if closes[-1] >= e else -1
    else:
        F["daily_dir"] = 0
    F["gap"] = (o[0] - prev[3]) / prev[3] if prev[3] else 0.0
    return F


def _fresh(cond: np.ndarray) -> np.ndarray:
    out = cond.copy()
    out[1:] &= ~cond[:-1]
    return out


def signals(F: dict, g: dict, day_seed: int) -> np.ndarray:
    """Direction per minute (+1 buy a call, -1 buy a put, 0 nothing); a fresh condition at minute i's close."""
    sig = np.zeros(len(F["c"]), dtype=np.int8)
    for fam in g["families"]:
        part = _family(F, fam, day_seed)
        sig = np.where(sig != 0, sig, part).astype(np.int8)
    bias = g.get("bias", "none")
    if bias == "with_daily" and F["daily_dir"] != 0:
        sig[sig == -F["daily_dir"]] = 0
    elif bias == "against_daily" and F["daily_dir"] != 0:
        sig[sig == F["daily_dir"]] = 0
    elif bias == "puts":
        sig[sig > 0] = 0
    elif bias == "calls":
        sig[sig < 0] = 0
    return sig


def _family(F: dict, fam: dict, day_seed: int) -> np.ndarray:
    c, h, l, o, atr, vwap = F["c"], F["h"], F["l"], F["o"], F["atr"], F["vwap"]
    n = len(c)
    kind = fam["kind"]
    up = np.zeros(n, bool)
    dn = np.zeros(n, bool)
    if kind == "ORB":
        N, buf = fam["n"], fam["buf"]
        with np.errstate(invalid="ignore"):
            up = c > F[f"orh{N}"] + buf * atr
            dn = c < F[f"orl{N}"] - buf * atr
    elif kind == "MOMO":
        k, z = fam["k"], fam["z"]
        mv = np.zeros(n)
        mv[k:] = c[k:] - c[:-k]
        thr = z * atr * math.sqrt(k)
        up = mv >= thr
        dn = mv <= -thr
        if fam.get("vwap"):
            up &= c > vwap
            dn &= c < vwap
    elif kind == "TPB":
        ef, es = F[f"ema{fam['fast']}"], F[f"ema{fam['slow']}"]
        p, touch = fam["look"], fam["touch"]
        es_prev = np.concatenate([np.full(5, es[0]), es[:-5]])
        trend_up = (ef > es) & (es > es_prev) & (c > vwap)
        trend_dn = (ef < es) & (es < es_prev) & (c < vwap)
        lo_p = np.full(n, np.inf)
        hi_p = np.full(n, -np.inf)
        for j in range(1, p + 1):
            lo_p[j:] = np.minimum(lo_p[j:], l[:-j])
            hi_p[j:] = np.maximum(hi_p[j:], h[:-j])
        h_prev = np.concatenate([[np.inf], h[:-1]])
        l_prev = np.concatenate([[-np.inf], l[:-1]])
        up = trend_up & (lo_p <= ef + touch * atr) & (c > h_prev) & (c > ef)
        dn = trend_dn & (hi_p >= ef - touch * atr) & (c < l_prev) & (c < ef)
    elif kind == "VWAPX":
        ef = F[f"ema{fam['fast']}"]
        ef_prev = np.concatenate([[ef[0]], ef[:-1]])
        up = (c > vwap + fam["buf"] * atr) & (ef > ef_prev)
        dn = (c < vwap - fam["buf"] * atr) & (ef < ef_prev)
    elif kind == "EMAX":
        ef, es = F[f"ema{fam['fast']}"], F[f"ema{fam['slow']}"]
        up = ef > es
        dn = ef < es
    elif kind == "FADE":
        dev = (c - vwap) / atr
        c_prev = np.concatenate([[c[0]], c[:-1]])
        dn = (dev >= fam["z"]) & (c < o) & (c < c_prev)
        up = (dev <= -fam["z"]) & (c > o) & (c > c_prev)
    elif kind == "PDX":
        up = c > F["pdh"] + fam["buf"] * atr
        dn = c < F["pdl"] - fam["buf"] * atr
    elif kind == "RANDOM":
        rng = np.random.default_rng((fam["seed"] * 1_000_003 + day_seed) & 0xFFFFFFFF)
        u = rng.random(n)
        side = rng.random(n) < 0.5
        hit = u < fam["p"]
        out = np.zeros(n, dtype=np.int8)
        out[hit & side] = 1
        out[hit & ~side] = -1
        return out
    else:
        raise ValueError(kind)
    out = np.zeros(n, dtype=np.int8)
    out[_fresh(up)] = 1
    out[_fresh(dn) & (out == 0)] = -1
    return out


# ---- one session -----------------------------------------------------------------------------------------------

class Session:
    """One session's arrays plus cached bids, shared by every genome a worker evaluates."""

    def __init__(self, s: dict):
        self.s = s
        self.day = s["day"]
        self.seed = int(self.day.replace("-", ""))
        self.F = features(s)
        self._bids: dict = {}

    def option(self, strike: int, opt: str):
        key = (strike, opt)
        if key not in self._bids:
            a = self.s["options"].get(key)
            if a is None:
                self._bids[key] = None
            else:
                a = a.astype(np.float64)
                # bids of open/high/low/close; marks carry the last close forward
                mark = a[3].copy()
                last = np.nan
                for i in range(len(mark)):
                    if np.isnan(mark[i]):
                        mark[i] = last
                    else:
                        last = mark[i]
                self._bids[key] = (a, _bid_vec(a[0]), _bid_vec(a[1]), _bid_vec(a[2]), _bid_vec(a[3]),
                                   _bid_vec(mark), ~np.isnan(a[3]))
        return self._bids[key]


def run_day(S: Session, g: dict, wallet: float, target: float, loss_limit: float, stress: float = 0.0,
            record: bool = False) -> dict:
    """Play one session for genome ``g``. Returns the day's net (after charges and stress) and how it ended."""
    F = S.F
    sig = signals(F, g, S.seed)
    start, last_entry = g["start"], g["last_entry"]
    idx = np.flatnonzero(sig[: last_entry + 1])
    idx = idx[idx >= start]
    realized = 0.0
    n_trades = 0
    trades = []
    end = "no_signal" if len(idx) == 0 else "window_closed"
    i = start
    lock_on = g.get("lock", 0.0) > 0
    while True:
        k = np.searchsorted(idx, i)
        if k >= len(idx):
            break
        if n_trades >= g["max_trades"]:
            end = "max_trades"
            break
        i = int(idx[k])
        d = int(sig[i])
        c = F["c"][i]
        atm = int(round(c / STEP) * STEP)
        off = g["offset"]
        strike = atm + d * off * STEP
        opt = "CE" if d > 0 else "PE"
        rec = S.option(strike, opt)
        if rec is None or not rec[6][i] or rec[0][4][i] < g.get("min_vol", 0):
            i += 1
            continue
        a, b_open, b_high, b_low, b_close, b_mark, traded = rec
        ask = ask_of(float(a[3][i]))
        room = loss_limit + realized
        lots = int(min(g["max_lots"], math.floor(wallet * g["cash"] / (ask * LOT))))
        while lots >= 1:
            qty = lots * LOT
            est = charges(ask, ask, qty) + stress * lots
            if ask * g["stop"] * qty + est <= room:
                break
            lots -= 1
        if lots < 1:
            # the stop does not fit the day's remaining loss room (or the wallet cannot buy a lot)
            if room < loss_limit * 0.15:
                end = "loss_room"
                break
            i += 1
            continue
        qty = lots * LOT
        est = charges(ask, ask, qty) + stress * lots
        stop_px = ask * (1 - g["stop"])
        day_stop = ask - (room - est) / qty
        day_stop = _ceil_tick(ask - (room - charges(ask, day_stop, qty) - stress * lots) / qty)
        stop_px = max(stop_px, day_stop)
        # the sell limit that brings the day exactly to its target after this trade's own charges
        day_tgt = ask + (target - realized + est) / qty
        for _ in range(2):
            day_tgt = ask + (target - realized + charges(ask, day_tgt, qty) + stress * lots) / qty
        day_tgt = _ceil_tick(day_tgt)
        tgt_px = ask * (1 + g["target"])
        if not lock_on:
            tgt_px = min(tgt_px, day_tgt)
        peak = ask
        locked = False
        floor = -np.inf
        exit_px, reason, j = None, None, i
        for j in range(i + 1, EXIT_MIN + 1):
            if traded[j]:
                bo, bh, bl, bc = b_open[j], b_high[j], b_low[j], b_close[j]
                stop_eff = max(stop_px, floor)
                if g.get("trail_act", 0) > 0 and peak >= ask * (1 + g["trail_act"]):
                    stop_eff = max(stop_eff, peak - g["trail_give"] * (peak - ask))
                if bl <= stop_eff:
                    exit_px = min(stop_eff, bo)
                    reason = "lock_floor" if locked and stop_eff == floor else (
                        "day_loss" if stop_eff == day_stop else "stop")
                    break
                if not locked:
                    if bh >= tgt_px:
                        exit_px = max(tgt_px, bo)
                        reason = "day_target" if tgt_px == day_tgt else "target"
                        break
                    if lock_on and bh >= day_tgt:
                        locked = True
                        floor = day_tgt
                        peak = max(peak, bh)
                        if bc < floor:
                            exit_px, reason = floor, "lock_floor"
                            break
                if locked:
                    give = g["lock"] * target / qty
                    floor = max(floor, max(peak, bc) - give)
                peak = max(peak, bc)
                if not locked and j - i >= g["hold"]:
                    exit_px, reason = bc, "time"
                    break
            if j == EXIT_MIN:
                exit_px = b_close[j] if traded[j] else b_mark[j]
                if np.isnan(exit_px):
                    exit_px = bid_of(float(a[3][i]))
                reason = "eod"
                break
        exit_px = float(exit_px)
        net = (exit_px - ask) * qty - charges(ask, exit_px, qty) - stress * lots
        realized += net
        n_trades += 1
        if record:
            trades.append({"i": i, "j": j, "dir": d, "strike": strike, "lots": lots, "entry": ask, "exit": exit_px,
                           "net": round(net, 2), "reason": reason})
        i = j + 1
        if locked or realized >= target - 1e-6:
            end = "target"
            break
        if realized <= -loss_limit * 0.98 or (loss_limit + realized) < loss_limit * 0.05:
            end = "loss_limit"
            break
    out = {"day": S.day, "net": realized, "trades": n_trades, "end": end}
    if record:
        out["detail"] = trades
    return out

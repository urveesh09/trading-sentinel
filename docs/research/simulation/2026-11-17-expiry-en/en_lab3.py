"""EN11-EN25 lab (PLAN3.md): en_lab2's day loop with every new hook off by default. check() proves the hooks-off
loop reproduces E03.2 day by day on NIFTY 2023, 2024 and 2025 at all three fill levels, and prints signal counts only.
Every decision reads the completed bar and earlier bars; fills are the next bar's (or, for EN11's intrabar stop and
EN25's resting limit, the same bar's observed range with the stated conservative prices).

Hooks (Rule fields):
  fast_exit       EN11 intrabar premium stop / joint index+future structure trigger on non-runner tickets
  cover           EN12 at the 2x trigger sell the fewest lots that pay back the whole ticket (else all)
  runner_struct   EN12 the runner also exits when the index closes back through the decision close
  setup3          new entry setups: RANGE (EN13), WAVE / WAVE_NOW (EN14), PIN (EN19), LASTHALF (EN23), PAIR (EN17)
  retry_gate      EN20 a same-side ticket after a losing STOP/STRUCTURE ticket needs reclaim + new higher low/lower high
  no_retry_after_stop  EN20 diagnostic: no ticket after a losing stop
  scale_in        EN21 half the lots first, the rest once if the bid reaches 1.2x within 3 bars
  no_pstop        EN22 no hard premium stop
  fut_vol         EN24 keep a signal only when the decision bar's futures volume >= its 30-bar median
  passive         EN25 resting buy limit at the decision bar's bid for 2 bars, filled only when traded through
  no_clock        no 8-minute TIME exit (EN19, EN23)
  day_budget      >0: the day's reserve (EN17 pairs)
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, replace
import hashlib, json, math, random, sqlite3
import numpy as np
import en_lab2 as M

N, R, L, X, E = M.N, M.R, M.L, M.X, M.E
LOT, PARTIAL = M.LOT, M.PARTIAL
AVAIL = None          # set by the scorer (and check) to exam2023b.available_at
NULL = None           # seed string: replace setup signals by a random side at the same minutes (matched null)
LOSS_FIRST = ("STOP", "STRUCTURE", "STOP_FAST", "STRUCTURE_FAST")


@dataclass(frozen=True)
class Rule(M.Rule):
    fast_exit: bool = False
    cover: bool = False
    runner_struct: bool = False
    setup3: str = ""
    retry_gate: bool = False
    no_retry_after_stop: bool = False
    scale_in: bool = False
    no_pstop: bool = False
    fut_vol: bool = False
    passive: bool = False
    no_clock: bool = False
    day_budget: float = 0.

    @property
    def key(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


E032 = Rule(**asdict(M.E032))
NEW = dict(put_mult=1.)                     # symmetric Rs 1,250 tickets, Rs 2,500 day, for new setups

ARMS = {   # PLAN3.md, one primary arm per slot (+ named diagnostics)
    "EN11": replace(E032, fast_exit=True),
    "EN12": replace(E032, cover=True, runner_struct=True),
    "EN12_full_sale_diag": replace(E032, split=False),
    "EN13": replace(E032, setup3="RANGE", **NEW),
    "EN14": replace(E032, setup3="WAVE", **NEW),
    "EN14_immediate_diag": replace(E032, setup3="WAVE_NOW", **NEW),
    "EN17": replace(E032, setup3="PAIR", day_budget=5000.),
    "EN19": replace(E032, setup3="PIN", premium_low=2., premium_high=19., max_lots=1, arm=.5, keep=.75, solo_runner=True,
                    runner_keep=.7, no_clock=True, **NEW),
    "EN20": replace(E032, retry_gate=True),
    "EN20_no_retry_diag": replace(E032, no_retry_after_stop=True),
    "EN21": replace(E032, scale_in=True),
    "EN22": replace(E032, no_pstop=True),
    "EN23": replace(E032, setup3="LASTHALF", no_clock=True, flat=928, **NEW),
    "EN24": replace(E032, fut_vol=True),
    "EN25": replace(E032, passive=True),
}
NEW_SETUPS = ("EN13", "EN14", "EN14_immediate_diag", "EN17", "EN19", "EN23")


# ---------------------------------------------------------------- data
_FV = {}


def futvol(t):
    """Futures volume per bar from the sealed export (the tape keeps OHLC only); NaN where missing."""
    if t.day not in _FV:
        import exam2023 as A
        c = sqlite3.connect(A.SEALED.resolve().as_uri() + "?mode=ro", uri=True)
        v = np.full(375, np.nan)
        for stamp, vol in c.execute("SELECT datetime, volume FROM candles WHERE kind='future' AND datetime BETWEEN ? AND ?",
                                    (t.day + " 09:15:00", t.day + " 15:29:00")):
            k = (int(stamp[11:13]) - 9) * 60 + int(stamp[14:16]) - 15
            if 0 <= k < 375 and vol is not None and vol >= 0:
                v[k] = vol
        c.close(); _FV[t.day] = v
    return _FV[t.day]


def _avail(t, i, d):
    return AVAIL is None or AVAIL(t, i, d)


# ---------------------------------------------------------------- setups (signal arrays: dir, structure distance, target distance)
_SIG = {}


def setup_signals(t, rule):
    key = (id(t), rule.setup3, id(AVAIL))
    if key not in _SIG:
        _SIG[key] = {"RANGE": _range, "WAVE": lambda x: _wave(x, False), "WAVE_NOW": lambda x: _wave(x, True),
                     "PIN": _pin, "LASTHALF": _lasthalf}[rule.setup3](t)
    return _SIG[key]


def _blank(t):
    return np.zeros(t.n, dtype=np.int8), np.full(t.n, np.nan), np.full(t.n, np.nan)


def _range(t):
    dirs, sd, td = _blank(t); c, hi, lo, fc = t.close, t.x[:, 1], t.x[:, 2], t.f[:, 3]
    frozen = None
    for i in range(61, t.n):
        if not 780 <= t.minute[i] < 900:
            continue
        if not (np.isfinite(t.x[i]).all() and np.isfinite(t.f[i]).all() and np.isfinite([c[i - 1], fc[i - 1]]).all()):
            continue
        if frozen is None:
            w = slice(i - 60, i)
            if not np.isfinite(t.x[w]).all():
                continue
            H, Lo = float(np.max(hi[w])), float(np.min(lo[w])); mid = (H + Lo) / 2; cw = c[w]
            path = float(np.abs(np.diff(cw)).sum()); er = abs(cw[-1] - cw[0]) / path if path else 1.
            s = np.sign(cw - mid); s = s[s != 0]; cross = int(np.count_nonzero(np.diff(s)))
            if er <= .25 and cross >= 4 and (H - Lo) / 2 >= .0006 * c[i] and Lo <= c[i] <= H:
                frozen = (H, Lo, mid)
            else:
                continue
        H, Lo, mid = frozen; width = H - Lo
        if c[i] > H or c[i] < Lo:
            break                                                   # the range is broken: no more entries today
        low2, high2 = min(lo[i - 1], lo[i]), max(hi[i - 1], hi[i])
        d = 0
        if Lo <= low2 <= Lo + .25 * width and c[i] > c[i - 1] and fc[i] > fc[i - 1] and mid - c[i] >= .4 * (mid - Lo):
            d = 1
        elif H - .25 * width <= high2 <= H and c[i] < c[i - 1] and fc[i] < fc[i - 1] and c[i] - mid >= .4 * (H - mid):
            d = -1
        if d and _avail(t, i, d):
            dirs[i] = d; sd[i] = (c[i] - Lo) if d > 0 else (H - c[i]); td[i] = (mid - c[i]) if d > 0 else (c[i] - mid)
    return dirs, sd, td


def _wave(t, now):
    dirs, sd, td = _blank(t); c, hi, lo, fc, fh, fl = t.close, t.x[:, 1], t.x[:, 2], t.f[:, 3], t.f[:, 1], t.f[:, 2]
    atr = t.features[10][:, 4]; fv = futvol(t)
    k = 40
    while k < t.n - 1:
        if not 780 <= t.minute[k] < 885 or not np.isfinite(c[k - 3:k + 1]).all() or not np.isfinite(fc[k - 3:k + 1]).all() \
                or not np.isfinite(atr[k]) or not np.isfinite(t.x[k - 2:k + 1]).all() or not np.isfinite(t.f[k - 2:k + 1]).all():
            k += 1; continue
        im, fm = c[k] - c[k - 3], fc[k] - fc[k - 3]
        if not (abs(im) >= 2.5 * atr[k] and np.sign(fm) == np.sign(im) and abs(fm) >= .6 * abs(im)):
            k += 1; continue
        d = int(np.sign(im)); S = c[k - 3]
        ext = float(np.max(hi[k - 2:k + 1]) if d > 0 else np.min(lo[k - 2:k + 1])); mid = (S + ext) / 2
        fext = float(np.max(fh[k - 2:k + 1]) if d > 0 else np.min(fl[k - 2:k + 1])); fmid = (fc[k - 3] + fc[k]) / 2
        if now:
            if _avail(t, k, d):
                dirs[k] = d; sd[k] = abs(c[k] - mid)
            k += 6; continue
        base = fv[k - 32:k - 2]; base = float(np.median(base[np.isfinite(base)])) if np.isfinite(base).sum() >= 20 else np.nan
        vols = []; last = k
        for i in range(k + 1, min(k + 7, t.n - 1)):
            last = i
            if not (np.isfinite(t.x[i]).all() and np.isfinite(t.f[i]).all()) or d * (c[i] - mid) <= 0 or d * (fc[i] - fmid) <= 0:
                break                                               # the impulse midpoint is lost: no second wave
            if d * (c[i] - ext) > 0 and d * (fc[i] - fext) > 0:
                if vols and np.isfinite(base) and np.isfinite(vols).all() and float(np.mean(vols)) >= base and _avail(t, i, d):
                    dirs[i] = d; sd[i] = abs(c[i] - mid)
                break
            vols.append(fv[i])                                       # a pause bar
        k = last + 1
    return dirs, sd, td


def _pin(t):
    dirs, sd, td = _blank(t); c, fc = t.close, t.f[:, 3]
    for i in range(31, t.n):
        if not 855 <= t.minute[i] < 900 or not np.isfinite(c[i - 30:i + 1]).all() or not np.isfinite(fc[i - 2:i + 1]).all():
            continue
        w = c[i - 30:i]; K = round(float(np.mean(w)) / 50) * 50
        if np.mean(np.abs(w - K) <= .001 * K) < .8:
            continue
        d = 1 if c[i] - K >= .0015 * K and c[i - 1] - K >= .0005 * K else -1 if K - c[i] >= .0015 * K and K - c[i - 1] >= .0005 * K else 0
        if d and d * (fc[i] - fc[i - 2]) > 0:
            if _avail(t, i, d):
                dirs[i] = d; sd[i] = abs(c[i] - K)
            break                                                   # one attempt a day, taken or not
    return dirs, sd, td


def _lasthalf(t):
    dirs, sd, td = _blank(t)
    at = {int(m): i for i, m in enumerate(t.minute)}
    i0, i1, i2 = at.get(585), at.get(870), at.get(900)
    if None in (i0, i1, i2) or not np.isfinite([t.x[0, 0], t.close[i0], t.close[i1], t.close[i2]]).all():
        return dirs, sd, td
    r1 = t.close[i0] / t.x[0, 0] - 1; r12 = t.close[i2] / t.close[i1] - 1
    if r1 and r12 and np.sign(r1) == np.sign(r12):
        d = int(np.sign(r1))
        if _avail(t, i2, d):
            dirs[i2] = d; sd[i2] = np.inf                             # no structure exit
    return dirs, sd, td


def null_flip(t, dirs):
    out = np.zeros_like(dirs)
    for i in np.flatnonzero(dirs):
        d = random.Random(f"{NULL}-{t.day}-{int(i)}").choice((1, -1))
        out[i] = d if _avail(t, int(i), d) else 0
    return out


def vol_filter(t, dirs):
    fv = futvol(t); out = dirs.copy()
    for i in np.flatnonzero(dirs):
        prev = fv[max(0, i - 30):i]; prev = prev[np.isfinite(prev)]
        if len(prev) < 20 or not np.isfinite(fv[i]) or fv[i] < float(np.median(prev)):
            out[i] = 0
    return out


# ---------------------------------------------------------------- the day loop
def _sell(pos, i, decided, reason, filled, price):
    cost = E.fee(price, filled * LOT, False); gross = round((price - pos["entry"]) * filled * LOT, 2)
    pos["net"] = round(pos["net"] + gross - cost, 2); pos["fees"] = round(pos["fees"] + cost, 2); pos["open"] -= filled
    pos["events"].append(dict(i=i, decision_i=decided, side="SELL", reason=reason, lots=filled, price=price, fees=cost))
    pos["add_lots"] = 0


def _fast(t, i, pos, rule, scenario):
    r = t.q[i, pos["j"]]
    if not np.isfinite(r).all():
        return None
    cap = int(r[4] * .2) // LOT
    if cap <= 0:
        return None
    o, l, c = float(r[0]), float(r[2]), float(r[3])
    bo, bl, bc = E.down(o - E.half(o)), E.down(l - E.half(l)), E.down(c - E.half(c))
    n = min(pos["open"], cap); st = pos["stop"]
    if st > 0 and bl <= st:
        px = bo if bo <= st else E.down(st)
        if scenario == "adverse":
            px = max(bl, E.down(px - E.half(px) - max(.05, px * .01)))
        elif scenario == "catastrophe":
            px = bl
        return (n, px, "STOP_FAST" if st < pos["entry"] else "TRAIL_FAST") if px > 0 else None
    d = pos["direction"]
    if rule.underlying_stop > 0 and np.isfinite(t.x[i]).all() and np.isfinite(t.f[i]).all() and np.isfinite(pos["fut_stop"]):
        ix = t.x[i, 2] if d > 0 else t.x[i, 1]; fx = t.f[i, 2] if d > 0 else t.f[i, 1]
        if d * (ix - pos["underlying_stop"]) < 0 and d * (fx - pos["fut_stop"]) < 0:
            px = bc
            if scenario == "adverse":
                px = max(bl, E.down(bc - max(.05, bc * .01)))
            elif scenario == "catastrophe":
                px = bl
            return (n, px, "STRUCTURE_FAST") if px > 0 else None
    return None


def run_day(t, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False):
    if rule.setup3 == "PAIR":
        return pair_day(t, rule, scenario, cash, budget, details)
    if rule.setup3:
        dirs, sdist, tdist = setup_signals(t, rule)
        if NULL is not None:
            dirs = null_flip(t, dirs)
    else:
        dirs = M.directions(t, rule); sdist = tdist = None
        if rule.fut_vol:
            dirs = vol_filter(t, dirs)
    calm = bool(rule.regime_min) and not (M.morning_range(t) >= rule.regime_min)
    spent = 0.0; positions = []; next_i = 0; pending_entry = None; pending_exit = None; pending_add = None; pos = None
    rejected = 0; missed = []; stopped = None
    for i in range(int(np.searchsorted(t.minute, rule.start)), t.n):
        if pending_exit:
            qty, reason, decided = pending_exit
            filled, price = E.executable(t, i, pos["j"], "SELL", scenario, min(qty, pos["open"]))
            if filled:
                _sell(pos, i, decided, reason, filled, price)
                if reason in ("TARGET_BASE", "PUT_RUNNER"):
                    pos["runner"] = True
                    pos["stop"] = max(round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
                if not pos["open"]:
                    cash = round(cash + pos["net"], 2); pos["exit_i"] = i; positions.append(pos)
                    stopped = _stopped(t, pos, stopped); pos = None; pending_exit = None; next_i = i + 5
                else:
                    pending_exit = (pos["open"], reason, decided) if reason not in PARTIAL + ("PUT_RUNNER",) else None
            elif reason in PARTIAL + ("PUT_RUNNER",):
                pending_exit = None
            if pending_exit:
                continue
        if pending_add and pos:
            n, decided, lim = pending_add; pending_add = None; pos["add_lots"] = 0
            filled, price = E.executable(t, i, pos["j"], "BUY", scenario, n)
            if filled and price is not None and price <= lim:
                left = pos["room"] - pos["reserve"]
                while filled and E.reserve(price, filled) > left + .01:
                    filled -= 1
                if filled:
                    risk = E.reserve(price, filled); spent += risk; pos["reserve"] = round(pos["reserve"] + risk, 2)
                    fee = E.fee(price, filled * LOT, True)
                    avg = (pos["entry"] * pos["lots"] + price * filled) / (pos["lots"] + filled)
                    pos["net"] = round(pos["net"] - fee, 2); pos["fees"] = round(pos["fees"] + fee, 2)
                    pos["lots"] += filled; pos["open"] += filled; pos["entry"] = avg; pos["added"] = filled
                    pos["stop"] = round(avg * (1 - rule.stop), 2)
                    pos["events"].append(dict(i=i, decision_i=decided, side="BUY", reason="ADD", lots=filled, price=price, fees=fee))
        if pending_entry:
            j, lots, limit, decision, sign, atr, room, origin, meta = pending_entry
            if rule.passive:
                r = t.q[i, j]; P = meta["passive"]; thr = P - (.05 if scenario == "ordinary" else .10)
                cap = int(r[4] * .2) // LOT if np.isfinite(r).all() else 0
                if cap > 0 and r[2] <= thr + 1e-9:
                    filled, price = min(lots, cap), P; pending_entry = None
                elif i - decision < 2:
                    continue                                         # the limit rests one more bar
                else:
                    pending_entry = None; missed.append(dict(day=t.day, decision_i=decision, direction=sign, j=j)); continue
            else:
                pending_entry = None
                filled, price = E.executable(t, i, j, "BUY", scenario, lots)
            if filled < max(1, math.ceil(lots * .25)) or price is None or price > limit:
                rejected += 1; continue
            risk = E.reserve(price, filled); assert risk <= room + .01
            spent += risk
            if "slevel" in meta:
                us = float(meta["slevel"])
            elif "sd" in meta:
                us = float(t.close[decision] - sign * meta["sd"]) if np.isfinite(meta["sd"]) else -sign * math.inf
            else:
                us = float(t.close[decision] - sign * atr * rule.underlying_stop)
            dist = float(t.close[decision]) - us
            fut_stop = float(t.f[decision, 3] - dist) if np.isfinite(t.f[decision, 3]) else math.nan
            td = meta.get("td", math.nan)
            pos = dict(day=t.day, j=j, symbol=t.symbols[j], direction=sign, entry_i=i, decision_i=decision, entry=price, lots=filled,
                       open=filled, reserve=round(risk, 2), peak=price, stop=0.0 if rule.no_pstop else round(price * (1 - rule.stop), 2),
                       banked=False, origin=origin, net=-E.fee(price, filled * LOT, True), fees=E.fee(price, filled * LOT, True),
                       underlying_stop=us, fut_stop=fut_stop, dec_close=float(t.close[decision]), room=room, first=price,
                       tlevel=float(t.close[decision] + sign * td) if np.isfinite(td) else None,
                       add_lots=meta.get("add", 0), planned=meta.get("planned", filled), retry="slevel" in meta,
                       events=[dict(i=i, decision_i=decision, side="BUY", lots=filled, price=price, fees=E.fee(price, filled * LOT, True))])
        if pos:
            row = t.q[i, pos["j"]]
            bid = E.down(float(row[3]) - E.half(float(row[3]))) if np.isfinite(row[3]) and np.isfinite(row[4]) and row[4] * .2 >= LOT else None
            if rule.fast_exit and not pos.get("runner") and t.minute[i] < rule.flat:
                fx = _fast(t, i, pos, rule, scenario)
                if fx:
                    filled, price, reason = fx; _sell(pos, i, i, reason, filled, price)
                    if not pos["open"]:
                        cash = round(cash + pos["net"], 2); pos["exit_i"] = i; positions.append(pos)
                        stopped = _stopped(t, pos, stopped); pos = None; next_i = i + 5
                    elif i < t.n - 1:
                        pending_exit = (pos["open"], reason, i)
                    continue
            reason = None; qty = pos["open"]
            if t.minute[i] >= rule.flat:
                reason = "FLAT_TIME"
            elif bid is not None and bid > 0 and pos.get("runner") and rule.split:
                pos["peak"] = max(pos["peak"], bid)
                pos["stop"] = max(pos["stop"], round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
                if bid <= pos["stop"]:
                    reason = "RUNNER_TRAIL"
                elif rule.hero_target and bid >= pos["entry"] * (1 + rule.hero_target):
                    reason = "HERO_TARGET"
                elif rule.runner_struct and np.isfinite(t.close[i]) and pos["direction"] * (t.close[i] - pos["dec_close"]) < 0:
                    reason = "RUNNER_STRUCT"
            elif bid is not None and bid > 0:
                pos["peak"] = max(pos["peak"], bid)
                gain = pos["peak"] / pos["entry"] - 1
                if gain >= rule.arm:
                    pos["stop"] = max(pos["stop"], round(pos["peak"] * rule.keep, 2))
                if rule.lock_arm and gain >= rule.lock_arm:
                    pos["stop"] = max(pos["stop"], round(pos["entry"] * rule.lock_floor, 2))
                intact = not (np.isfinite(t.close[i]) and rule.underlying_stop > 0 and pos["direction"] * (t.close[i] - pos["underlying_stop"]) < 0)
                if bid <= pos["stop"]:
                    reason = "TRAIL" if pos["stop"] >= pos["entry"] else "STOP"
                elif not intact:
                    reason = "STRUCTURE"
                elif pos["tlevel"] is not None and np.isfinite(t.close[i]) and pos["direction"] * (t.close[i] - pos["tlevel"]) >= 0:
                    reason = "SETUP_TARGET"
                elif bid >= pos["entry"] * (1 + rule.target):
                    reason = "TARGET"
                    if rule.split and pos["open"] >= 2:
                        if rule.cover:
                            k = X.recover_lots(pos, bid)
                            if 1 <= k < pos["open"]:
                                reason, qty = "TARGET_BASE", k
                        else:
                            reason, qty = "TARGET_BASE", pos["open"] - pos["open"] // 2
                    elif rule.split and rule.solo_runner and pos["open"] == 1:
                        reason = None; pos["runner"] = True
                        pos["stop"] = max(round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
                elif rule.bank_r and pos["lots"] == 1 and i - pos["entry_i"] < rule.hold and bid >= M._bank_price(pos, rule):
                    reason = "ONE_LOT_BANK"
                elif L.stalled(rule, i, pos, bid):
                    reason = "STALL"
                elif not rule.no_clock and L.timed_out(t, rule, i, pos, bid, gain):
                    reason = "TIME"
                    if rule.put_runner and pos["direction"] < 0 and pos["open"] >= 2 and bid >= pos["entry"] * rule.put_runner:
                        reason, qty = "PUT_RUNNER", pos["open"] - pos["open"] // 2
                if reason is None and rule.scale_in and pos["add_lots"] and not pos.get("runner") and i - pos["entry_i"] <= 3 \
                        and intact and bid >= pos["first"] * 1.2 and np.isfinite(row[3]):
                    pending_add = (pos["add_lots"], i, E.down(E.up(float(row[3]) + E.half(float(row[3]))) * (1 + rule.chase)))
            if reason and i < t.n - 1:
                pending_exit = (qty, reason, i)
            continue
        if calm or pending_exit or pending_entry or i < next_i or i >= t.n - 1 or len(positions) >= rule.slots:
            continue
        sign = int(dirs[i])
        if not sign:
            continue
        meta = {}
        if sdist is not None:
            meta.update(sd=float(sdist[i]), td=float(tdist[i]))
        if stopped and rule.no_retry_after_stop:
            continue
        if stopped and rule.retry_gate and sign == stopped["d"]:
            if not (np.isfinite(t.x[i - 2:i]).all() and np.isfinite(t.f[i, 3])):
                continue
            pull = float(np.min(t.x[i - 2:i, 2]) if sign > 0 else np.max(t.x[i - 2:i, 1]))
            c0, f0 = stopped["c0"], stopped["f0"]
            if not (sign * (t.close[i] - c0) > 0 and sign * (t.f[i, 3] - f0) > 0 and sign * (pull - c0) > 0):
                continue
            meta.update(slevel=pull, max_lots=stopped["lots"])
        mult = rule.put_mult if sign < 0 else rule.call_mult
        room = min(E.BUDGET / rule.slots * mult, budget - spent, cash)
        if room <= 0:
            continue
        cap = int(round(rule.max_lots * mult))
        pick = L.choose(t, i, sign, replace(rule, max_lots=cap) if cap != rule.max_lots else rule, room, cash)
        if pick:
            j, lots, limit = pick
            if meta.get("max_lots"):
                lots = min(lots, meta["max_lots"])
            if rule.scale_in and lots >= 2:
                first = math.ceil(lots / 2); meta.update(add=lots - first, planned=lots); lots = first
            if rule.passive:
                qc = float(t.q[i, j, 3]); meta["passive"] = E.down(qc - E.half(qc))
                if meta["passive"] <= 0:
                    continue
            origin = "E032" if not rule.setup3 else rule.setup3
            pending_entry = (j, lots, limit, i, sign, t.features[rule.look][i, 4], room, origin, meta)
    unresolved = 0
    if pos:
        unresolved = 1
        pos["net"] = round(pos["net"] - pos["entry"] * pos["open"] * LOT, 2); pos["unresolved"] = True; positions.append(pos)
    net = round(sum(p["net"] for p in positions), 2)
    assert spent <= budget + .02 and net >= -spent - .03
    return dict(day=t.day, net=net, trades=len(positions), spent=round(spent, 2), fees=round(sum(p["fees"] for p in positions), 2),
                unresolved=unresolved, rejected=rejected, positions=positions if details else [], marked_worst=0., calm=calm,
                missed=missed if details else [])


def _stopped(t, pos, prev):
    first = next((e["reason"] for e in pos["events"] if e["side"] == "SELL"), "")
    if pos["net"] < 0 and first in LOSS_FIRST:
        dec = pos["decision_i"]
        return dict(d=pos["direction"], c0=float(t.close[dec]), f0=float(t.f[dec, 3]), lots=pos["lots"])
    return prev


# ---------------------------------------------------------------- EN17: paired call + put on a volatility burst
_PAIR = {}


def _pair_pick(t, i, rule):
    c = t.close[i]; asks = t.q[i, :, 3]; out = []
    if not np.isfinite(c):
        return None
    for d in (1, -1):
        ok = (t.kinds == d) & (d * (t.strikes - c) > 0) & (np.abs(t.strikes - c) <= 200) & np.isfinite(asks) \
            & (asks >= rule.premium_low) & (asks <= rule.premium_high)
        js = sorted(np.flatnonzero(ok), key=lambda j: d * t.strikes[j])
        if not js:
            return None
        out.append(int(js[0]))
    return tuple(out)


def pair_signals(t, rule):
    key = (id(t), id(AVAIL))
    if key in _PAIR:
        return _PAIR[key]
    x, c = t.x, t.close
    tr = np.full(t.n, np.nan)
    for i in range(1, t.n):
        if np.isfinite(x[i]).all() and np.isfinite(c[i - 1]):
            tr[i] = max(x[i, 1], c[i - 1]) - min(x[i, 2], c[i - 1])
    tr5 = np.full(t.n, np.nan)
    for i in range(5, t.n):
        w = tr[i - 4:i + 1]
        if np.isfinite(w).all():
            tr5[i] = float(w.sum())
    sig, pool = {}, {}
    for i in range(40, t.n - 1):
        if not 780 <= t.minute[i] < 885 or not np.isfinite(tr5[i]):
            continue
        pick = _pair_pick(t, i, rule)
        if not pick or not (_avail(t, i, 1) and _avail(t, i, -1)):
            continue
        pool[i] = pick
        ref = tr5[(t.minute >= 585) & (t.minute <= t.minute[i] - 5)]; ref = ref[np.isfinite(ref)]
        er = t.features[10][i, 2]
        if len(ref) < 30 or not np.isfinite(er) or abs(er) >= .5 or tr5[i] < 2 * float(np.median(ref)):
            continue
        q0, q5 = t.q[i, list(pick), 3], t.q[i - 5, list(pick), 3]
        if np.isfinite(q5).all() and q0.sum() >= q5.sum():           # the pair held its value through 5 minutes of decay
            sig[i] = pick
    _PAIR[key] = (sig, pool)
    return sig, pool


def pair_day(t, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False):
    sig, pool = pair_signals(t, rule)
    if NULL is not None:
        rng = random.Random(f"{NULL}-{t.day}"); keys = sorted(pool)
        sig = {i: pool[i] for i in rng.sample(keys, min(len(keys), len(sig)))}
    spent = 0.0; pairs = []; pend = None; legs = None; pexit = None; next_i = 0; rejected = 0; entry_i = 0; dec_i = 0
    for i in range(int(np.searchsorted(t.minute, rule.start)), t.n):
        if pexit:
            for g in legs:
                if g["open"]:
                    f, p = E.executable(t, i, g["j"], "SELL", scenario, g["open"])
                    if f:
                        cost = E.fee(p, f * LOT, False)
                        g["net"] = round(g["net"] + round((p - g["entry"]) * f * LOT, 2) - cost, 2); g["fees"] = round(g["fees"] + cost, 2)
                        g["open"] -= f; g["sells"].append(dict(i=i, reason=pexit, lots=f, price=p))
            if not any(g["open"] for g in legs):
                net = round(sum(g["net"] for g in legs), 2); cash = round(cash + net, 2)
                pairs.append(dict(day=t.day, decision_i=dec_i, entry_i=entry_i, exit_i=i, direction=0, lots=sum(g["lots"] for g in legs),
                                  entry=round(sum(g["entry"] for g in legs), 2), net=net, fees=round(sum(g["fees"] for g in legs), 2),
                                  peak=0., legs=legs, origin="PAIR", symbol="+".join(t.symbols[g["j"]] for g in legs),
                                  events=[dict(side="BUY", reason="")] + [dict(side="SELL", reason=pexit)]))
                legs = None; pexit = None; next_i = i + 5
            continue
        if pend:
            dec, js, n, lims = pend; pend = None; got = []
            for j, lim in zip(js, lims):
                f, p = E.executable(t, i, j, "BUY", scenario, n)
                if f >= 1 and p is not None and p <= lim:
                    fee = E.fee(p, f * LOT, True); spent += E.reserve(p, f)
                    got.append(dict(j=j, entry=p, lots=f, open=f, net=-fee, fees=fee, sells=[]))
            if not got:
                rejected += 1; continue
            legs = got; entry_i = i; dec_i = dec
            if len(got) == 1:
                pexit = "ONE_LEG"; continue
        if legs:
            bids = []
            for g in legs:
                row = t.q[i, g["j"]]
                bids.append(E.down(float(row[3]) - E.half(float(row[3]))) if np.isfinite(row[3]) and np.isfinite(row[4]) and row[4] * .2 >= LOT else None)
            reason = None
            if t.minute[i] >= rule.flat:
                reason = "FLAT_TIME"
            elif all(b is not None and b > 0 for b in bids):
                V = sum(b * g["open"] * LOT - E.fee(b, g["open"] * LOT, False) for b, g in zip(bids, legs))
                D = sum(g["entry"] * g["lots"] * LOT + E.fee(g["entry"], g["lots"] * LOT, True) for g in legs)
                age = i - entry_i
                reason = "PAIR_TARGET" if V >= 1.5 * D else "PAIR_STOP" if V <= .7 * D else "FADE" if age >= 4 and V < D else "CLOCK" if age >= 10 else None
            if reason and i < t.n - 1:
                pexit = reason
            continue
        if i < next_i or i >= t.n - 1 or len(pairs) >= rule.slots or i not in sig:
            continue
        room = min(2500., budget - spent, cash)
        js = sig[i]; asks = [E.up(float(t.q[i, j, 3]) + E.half(float(t.q[i, j, 3]))) for j in js]
        lims = [E.down(a * (1 + rule.chase)) for a in asks]
        n = 3
        while n and E.reserve(lims[0], n) + E.reserve(lims[1], n) > room + .01:
            n -= 1
        if n:
            pend = (i, js, n, lims)
    unresolved = 0
    if legs:
        unresolved = 1
        for g in legs:
            g["net"] = round(g["net"] - g["entry"] * g["open"] * LOT, 2)
        pairs.append(dict(day=t.day, decision_i=dec_i, entry_i=entry_i, direction=0, lots=sum(g["lots"] for g in legs),
                          entry=round(sum(g["entry"] for g in legs), 2), net=round(sum(g["net"] for g in legs), 2),
                          fees=round(sum(g["fees"] for g in legs), 2), peak=0., legs=legs, origin="PAIR", unresolved=True,
                          symbol="", events=[dict(side="BUY", reason="")]))
    net = round(sum(p["net"] for p in pairs), 2)
    assert spent <= budget + .02 and net >= -spent - .03
    return dict(day=t.day, net=net, trades=len(pairs), spent=round(spent, 2), fees=round(sum(p["fees"] for p in pairs), 2),
                unresolved=unresolved, rejected=rejected, positions=pairs if details else [], marked_worst=0., calm=False, missed=[])


def run(tapes, rule, scenario="ordinary", details=False):
    cash = peak = E.START_CASH; days = []
    full = rule.day_budget or E.BUDGET * R.day_scale(rule)
    for t in tapes:
        dd = peak - cash
        scale = 0. if dd >= 4000 else .25 if dd >= 3000 else .5 if dd >= 1500 else 1.
        row = run_day(t, rule, scenario, cash, min(full * scale, cash), details)
        cash = round(cash + row["net"], 2); peak = max(peak, cash); assert cash >= -.01
        row.update(cash_after=cash, scale=scale); days.append(row)
    return dict(rule=asdict(rule), scenario=scenario, summary=E.summary(days), days=days)


tapes = M.tapes


def check():
    """Hooks off = E03.2 (all years, all fill levels); then signal counts only (no rupees)."""
    global AVAIL
    import exam2023b as C
    T = tapes()
    for y in (2023, 2024, 2025):
        for sc in ("ordinary", "adverse", "catastrophe"):
            a, b = run(T[y], E032, sc), M.run(T[y], M.E032, sc)
            assert [d["net"] for d in a["days"]] == [d["net"] for d in b["days"]], (y, sc)
    AVAIL = C.available_at
    try:
        counts = {}
        for name in ("EN13", "EN14", "EN14_immediate_diag", "EN19", "EN23"):
            counts[name] = {y: int(sum(np.count_nonzero(setup_signals(t, ARMS[name])[0]) for t in T[y])) for y in T}
        counts["EN17"] = {y: int(sum(len(pair_signals(t, ARMS["EN17"])[0]) for t in T[y])) for y in T}
        fv = {y: round(float(np.mean([np.isfinite(futvol(t)[240:345]).mean() for t in T[y]])), 3) for y in T}
        for name, rule in ARMS.items():                                 # every arm runs (results not printed)
            for y in T:
                run(T[y], rule, "ordinary")
    finally:
        AVAIL = None
    print("CHECK_OK en_lab3 hooks-off = E03.2 day by day (2023-25 x 3 fill levels); every arm runs")
    print("signal days/counts (coverage rule on):", counts, "futures-volume coverage 13:00-14:45:", fv)


if __name__ == "__main__":
    check()

"""EN26-EN40 lab (PLAN4.md): en_lab3.run_day generalised to an index specification (NIFTY / SENSEX), plus the new
hooks, every one off by default. en_lab3 and its receipts stay immutable; check() proves this loop reproduces
E03.2, E03.1 and every frozen round-3 arm used here day by day on NIFTY 2023-25 at all three fill levels, and that
choose4 equals the native pick on every signal minute. Decisions read the completed bar and earlier bars; fills are
the next bar's (EN28's resting bid: the resting bar's observed range under a stated conservative bound).

New Rule fields:
  damage        EN26 minute-cadence confirmed-damage exit; 'cat' = EN26_cat_diag catastrophe trigger only
  scout         EN27 half first, one add in completed minutes 2-6 on confirmed progress, stop never lowered
  patient       EN28 'cons' / 'opt': rest one bar at the decision bid, then one capped marketable fallback
  runner_stall  EN29 exit the runner after two no-new-extreme minutes plus a futures swing break
  setup3 'BASE' EN30 second wave at a held retrace base
  reverse       EN31 'accept' (accepted opposite move after a failed ticket) / 'flip' (diagnostic: immediate)
  atm_itm       EN32 range signals bought ATM / first ITM, one lot inside the same reserve
  cheap         EN36 keep a signal only when straddle / (ATR10 x sqrt(930 - minute)) <= cheap
  flow          EN37 keep a signal only when its side's OTM turnover accelerates more than the other side's
  basis         EN38 keep a signal only when the futures basis widened in its direction over 5 bars
  size_k        risk dial K1: ticket and day reserves, lot cap and brakes scaled by k
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, replace
import hashlib, json, math, random
import numpy as np
import en_lab3 as L3

M, R, L, X, E = L3.M, L3.R, L3.L, L3.X, L3.E
PARTIAL, LOSS_FIRST = L3.PARTIAL, L3.LOSS_FIRST
FAMILY = None          # set by check(): the 2023-25 tapes


@dataclass(frozen=True)
class Spec:
    name: str
    lot: int
    exchange: str
    step: int
    pscale: float            # premium band multiple of NIFTY's Rs 5-20
    cap: int                 # e03 choose: max OTM distance
    pre: int                 # e02 choose: pre-filter distance
    cover: int               # coverage rule distance

    def __post_init__(self):
        f = E.EP.fee_schedule(self.exchange); o = E.EP.order_fee(f)
        object.__setattr__(self, "order", o)
        object.__setattr__(self, "buy_rate", (E.EP.buy_charges(100, 1, f) - o) / 100)
        object.__setattr__(self, "sell_rate", (E.EP.sell_charges(100, 1, f) - o) / 100)


NIFTY = Spec("NIFTY", 65, "NFO", 50, 1., 200, 400, 200)
SENSEX = Spec("SENSEX", 20, "BFO", 100, 3.25, 400, 800, 400)
SPECS = {"NIFTY": NIFTY, "SENSEX": SENSEX}


def spec_of(t):
    return SPECS[getattr(t, "und", "NIFTY")]


def fee(sp, price, qty, buy):
    return round(sp.order + price * qty * (sp.buy_rate if buy else sp.sell_rate), 2)


def reserve(sp, price, lots):
    return price * lots * sp.lot + fee(sp, price, lots * sp.lot, True) + lots * sp.order


def executable(sp, t, i, j, side, scenario, lots, share=.2):
    r = t.q[i, j]
    if not np.isfinite(r).all():
        return 0, None
    capacity = int(r[4] * share) // sp.lot
    if capacity <= 0:
        return 0, None
    raw = float(r[1 if side == "BUY" else 2] if scenario == "catastrophe" else r[0])
    slip = E.half(raw) * (1 if scenario == "ordinary" else 2)
    if scenario == "adverse":
        slip += max(.05, raw * .01)
    price = E.up(raw + slip) if side == "BUY" else E.down(raw - slip)
    return (min(lots, capacity), price) if price > 0 else (0, None)


def ask_of(close):
    return E.up(float(close) + E.half(float(close)))


def bid_of(close):
    return E.down(float(close) - E.half(float(close)))


def choose4(sp, t, i, d, rule, budget, cash):
    """L.choose(X.choose(E.choose)) with the index's lot, fees, band and distances (check() proves NIFTY == native)."""
    assert rule.setup != "E011" and not rule.ivrv_max
    if not np.isfinite(t.close[i]):
        return None
    c = float(t.close[i]); asks = t.q[i, :, 3]; lo, hi = rule.premium_low * sp.pscale, rule.premium_high * sp.pscale
    valid = (t.kinds == d) & (d * (t.strikes - c) > 0) & (np.abs(t.strikes - c) <= sp.pre)
    valid &= np.isfinite(asks) & (asks >= lo) & (asks <= hi)
    picked = None
    for j in sorted(np.flatnonzero(valid), key=lambda j: d * t.strikes[j]):
        row = t.q[i, j]; ask = ask_of(row[3])
        if rule.reach:
            expected = t.features[rule.look][i, 4] * math.sqrt(max(1, 930 - t.minute[i]))
            if not np.isfinite(expected) or expected <= 0 or abs(t.strikes[j] - c) > rule.reach * expected:
                continue
        if rule.option_rise:
            old = t.q[i - 5, j, 3] if i >= 5 else np.nan
            if not np.isfinite(old) or old <= 0 or ask / old < rule.option_rise:
                continue
        cap = min(10, int(row[4] * .2) // sp.lot)
        for lots in range(cap, 0, -1):
            limit = E.down(min(ask * 1.10, (min(budget, cash) - sp.order - lots * sp.order) / (lots * sp.lot * (1 + sp.buy_rate))))
            if limit >= ask and reserve(sp, limit, lots) <= min(budget, cash) + .01:
                picked = (int(j), lots, limit); break
        if picked:
            break
    if picked is None:
        return None
    j, lots, limit = picked
    if d * (t.strikes[j] - c) > sp.cap:
        return None
    lots = min(lots, rule.max_lots); ask = ask_of(t.q[i, j, 3]); room = min(budget, cash); got = None
    while lots:
        limit = E.down(min(ask * 1.1, (room - sp.order - lots * sp.order) / (lots * sp.lot * (1 + sp.buy_rate))))
        if limit >= ask and reserve(sp, limit, lots) <= room + .01:
            got = (j, lots, limit); break
        lots -= 1
    if got is None:
        return None
    j, lots, limit = got
    limit = min(limit, E.down(ask * (1 + rule.chase)))
    return (j, lots, limit) if limit >= ask else None


def choose_atm(sp, t, i, d, room, chase=.08):
    """EN32: one lot of the ATM or first ITM strike, the smaller round-trip cost share, inside `room`."""
    c = float(t.close[i]); atm = round(c / sp.step) * sp.step; best = None
    for k in (atm, atm - d * sp.step):
        js = [j for j in range(len(t.strikes)) if t.kinds[j] == d and float(t.strikes[j]) == float(k)]
        if not js or not np.isfinite(t.q[i, js[0]]).all() or int(t.q[i, js[0], 4] * .2) // sp.lot < 1:
            continue
        j = js[0]; cl = float(t.q[i, j, 3]); ask = ask_of(cl)
        limit = E.down(min(ask * (1 + chase), (room - 2 * sp.order) / (sp.lot * (1 + sp.buy_rate))))
        if limit < ask or reserve(sp, limit, 1) > room + .01:
            continue
        share = (2 * E.half(cl) + (fee(sp, ask, sp.lot, True) + fee(sp, ask, sp.lot, False)) / sp.lot) / ask
        if best is None or share < best[0]:
            best = (share, j, limit)
    return (best[1], 1, best[2]) if best else None


def recover_lots(sp, pos, bid):
    paid = pos["entry"] * pos["lots"] * sp.lot + fee(sp, pos["entry"], pos["lots"] * sp.lot, True)
    for take in range(1, pos["open"]):
        if bid * take * sp.lot - fee(sp, bid, take * sp.lot, False) - (pos["open"] - take) * sp.order >= paid:
            return take
    return 0


# ---------------------------------------------------------------- coverage (exam2023b's rule at the index's strikes)
def required(sp, t, i, d):
    c = float(t.close[i]); s = sp.step
    first = math.floor(c / s) * s + s if d > 0 else math.ceil(c / s) * s - s
    return [first + d * s * n for n in range(sp.cover // s + 1) if 0 < d * (first + d * s * n - c) <= sp.cover]


def available(t, i, d):
    sp = spec_of(t)
    cols = {(float(k), int(kind)): j for j, (k, kind) in enumerate(zip(t.strikes, t.kinds))}
    for k in required(sp, t, i, d):
        j = cols.get((float(k), d))
        if j is None or not np.isfinite(t.q[i, j, :4]).all():
            return False
    return True


UNAV = {}


def masked(t, rule, dirs):
    out = dirs.copy()
    for i in np.flatnonzero(out):
        if not available(t, int(i), int(out[i])):
            UNAV[(t.day, int(i), int(out[i]))] = 1; out[i] = 0
    return out


# ---------------------------------------------------------------- the new rule
@dataclass(frozen=True)
class Rule(L3.Rule):
    damage: str = ""
    scout: bool = False
    patient: str = ""
    runner_stall: bool = False
    reverse: str = ""
    atm_itm: bool = False
    cheap: float = 0.
    flow: bool = False
    basis: bool = False
    size_k: float = 1.

    @property
    def key(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:16]


E032 = Rule(**asdict(L3.E032))
E031 = Rule(**{**asdict(L3.E032), **{k: getattr(R.E031, k) for k in ("put_mult", "chase", "flat")}})
THETA = 0.6924          # EN36 threshold: en_lab4.theta() on NIFTY 2023-25 signal features, written into PLAN4.md before the freeze
NEW = dict(put_mult=1.)
ARMS = {
    # frozen round-3 definitions (controls and held parts), through run_day4
    **{k: Rule(**asdict(L3.ARMS[k])) for k in ("EN11", "EN12", "EN12_full_sale_diag", "EN13", "EN14", "EN14_immediate_diag", "EN21", "EN25")},
    "EN26": replace(E032, damage="confirm"),
    "EN26_cat_diag": replace(E032, damage="cat"),
    "EN27": replace(E032, scout=True),
    "EN28": replace(E032, patient="cons"),
    "EN28_opt_diag": replace(E032, patient="opt"),
    "EN29": replace(E032, runner_stall=True),
    "EN30": replace(E032, setup3="BASE", **NEW),
    "EN31": replace(E032, reverse="accept"),
    "EN31_flip_diag": replace(E032, reverse="flip"),
    "EN32": replace(E032, setup3="RANGE", atm_itm=True, **NEW),
    "EN35_diag": replace(E032, patient="cons", scout=True, runner_stall=True),
    "EN36": replace(E032, cheap=-1.),          # -1: THETA (resolved by rule_for)
    "EN37": replace(E032, flow=True),
    "EN38": replace(E032, basis=True),
    "EN39": replace(E032, start=840, end=870),
    "EN40": replace(E032, put_mult=1.),
}


def rule_for(name):
    r = ARMS[name]
    if r.cheap < 0:
        assert THETA is not None and THETA > 0, "THETA must be fixed in PLAN4.md before scoring"
        r = replace(r, cheap=THETA)
    return r


# ---------------------------------------------------------------- signals
def _avail(t, i, d):
    return available(t, i, d)


def straddle_ratio(t, i):
    sp = spec_of(t); c = float(t.close[i]); k = round(c / sp.step) * sp.step
    js = {int(t.kinds[j]): j for j in range(len(t.strikes)) if float(t.strikes[j]) == float(k)}
    if 1 not in js or -1 not in js:
        return math.nan
    a, b = t.q[i, js[1], 3], t.q[i, js[-1], 3]; atr = t.features[10][i, 4]
    if not np.isfinite([a, b, atr]).all() or atr <= 0:
        return math.nan
    return float((a + b) / (atr * math.sqrt(max(1, 930 - t.minute[i]))))


def flow_ok(t, i, d):
    sp = spec_of(t); c = float(t.close[i])
    if i < 19 or not np.isfinite(c):
        return False
    acc = {}
    for side in (1, -1):
        js = [j for j in range(len(t.strikes)) if t.kinds[j] == side and 0 < side * (t.strikes[j] - c) <= 4 * sp.step]
        if len(js) < 3:
            return False
        q = t.q[:, js, :]
        tov = q[:, :, 3] * q[:, :, 4]
        a, b = tov[i - 4:i + 1], tov[i - 19:i - 4]
        if not np.isfinite(a).all() or not np.isfinite(b).all():
            return False
        base = float(b.sum()) / 15
        if base <= 0:
            return False
        acc[side] = float(a.sum()) / 5 / base
    return acc[d] > acc[-d]


def basis_ok(t, i, d):
    if i < 5 or not np.isfinite([t.f[i, 3], t.close[i], t.f[i - 5, 3], t.close[i - 5]]).all():
        return False
    return d * ((t.f[i, 3] - t.close[i]) - (t.f[i - 5, 3] - t.close[i - 5])) > 0


def filters(t, rule, dirs):
    if not (rule.cheap or rule.flow or rule.basis):
        return dirs
    out = dirs.copy()
    for i in np.flatnonzero(dirs):
        d = int(dirs[i])
        if rule.cheap and not (straddle_ratio(t, int(i)) <= rule.cheap):
            out[i] = 0
        elif rule.flow and not flow_ok(t, int(i), d):
            out[i] = 0
        elif rule.basis and not basis_ok(t, int(i), d):
            out[i] = 0
    return out


_SIG = {}


def base_signals(t):
    """EN30: EN14's impulse, then a 25-50% retrace that holds the midpoint, then a close through the prior bar."""
    if id(t) in _SIG:
        return _SIG[id(t)]
    dirs, sd, td = L3._blank(t); c, hi, lo, fc, fh, fl = t.close, t.x[:, 1], t.x[:, 2], t.f[:, 3], t.f[:, 1], t.f[:, 2]
    atr = t.features[10][:, 4]; k = 40
    while k < t.n - 1:
        if not 780 <= t.minute[k] < 885 or not np.isfinite(c[k - 3:k + 1]).all() or not np.isfinite(fc[k - 3:k + 1]).all() \
                or not np.isfinite(atr[k]) or not np.isfinite(t.x[k - 2:k + 1]).all() or not np.isfinite(t.f[k - 2:k + 1]).all():
            k += 1; continue
        im, fm = c[k] - c[k - 3], fc[k] - fc[k - 3]
        if not (abs(im) >= 2.5 * atr[k] and np.sign(fm) == np.sign(im) and abs(fm) >= .6 * abs(im)):
            k += 1; continue
        d = int(np.sign(im)); S0 = c[k - 3]
        ext = float(np.max(hi[k - 2:k + 1]) if d > 0 else np.min(lo[k - 2:k + 1])); R0 = abs(ext - S0)
        mid = (S0 + ext) / 2; fmid = (fc[k - 3] + fc[k]) / 2; base = None; last = k
        for i in range(k + 1, min(k + 7, t.n - 1)):
            last = i
            if not (np.isfinite(t.x[i]).all() and np.isfinite(t.f[i]).all()) or d * (c[i] - mid) <= 0 or d * (fc[i] - fmid) <= 0:
                break
            against = lo[i] if d > 0 else hi[i]
            if base is not None:
                if d * (c[i] - (base - d * .25 * atr[k])) < 0:
                    break                                                  # the base failed
                if d * (c[i] - (hi[i - 1] if d > 0 else lo[i - 1])) > 0 and d * (fc[i] - (fh[i - 1] if d > 0 else fl[i - 1])) > 0:
                    if t.minute[i] < 900 and _avail(t, i, d):
                        dirs[i] = d; sd[i] = abs(c[i] - (base - d * .25 * atr[k]))
                    break
            depth = d * (ext - against)
            if base is None and .25 * R0 <= depth <= .5 * R0:
                base = float(against)
            ext = float(max(ext, hi[i]) if d > 0 else min(ext, lo[i]))
        k = last + 1
    _SIG[id(t)] = (dirs, sd, td)
    return _SIG[id(t)]


def setup_signals(t, rule):
    if rule.setup3 == "BASE":
        return base_signals(t)
    return L3.setup_signals(t, rule)


def random_dirs(t, rule, seed, real):
    """E03.2 / E03.1 random-entry control: the same count per day, (minute, side) drawn from available pairs."""
    rng = random.Random(f"{seed}-{t.day}")
    lo, hi = int(np.searchsorted(t.minute, rule.start)), int(np.searchsorted(t.minute, rule.end))
    pairs = [(i, d) for i in range(lo, hi) for d in (1, -1) if np.isfinite(t.close[i]) and available(t, i, d)]
    out = np.zeros(t.n, dtype=np.int8)
    for i, d in rng.sample(pairs, min(len(pairs), int(np.count_nonzero(real)))):
        out[i] = d
    return out


RANDOM = None           # seed string: E03.2-family random-entry control


def signals(t, rule):
    """(dirs, structure distance, target distance) after coverage, nulls and filters."""
    if rule.setup3:
        dirs, sd, td = setup_signals(t, rule)
        if L3.NULL is not None:
            dirs = L3.null_flip(t, dirs)
        return dirs, sd, td
    dirs = masked(t, rule, M.directions(t, rule))
    if RANDOM is not None:
        dirs = random_dirs(t, rule, RANDOM, dirs)
    if rule.fut_vol:
        dirs = L3.vol_filter(t, dirs)
    return filters(t, rule, dirs), None, None


# ---------------------------------------------------------------- the day loop
def _sell(sp, pos, i, decided, reason, filled, price):
    cost = fee(sp, price, filled * sp.lot, False); gross = round((price - pos["entry"]) * filled * sp.lot, 2)
    pos["net"] = round(pos["net"] + gross - cost, 2); pos["fees"] = round(pos["fees"] + cost, 2); pos["open"] -= filled
    pos["events"].append(dict(i=i, decision_i=decided, side="SELL", reason=reason, lots=filled, price=price, fees=cost))
    pos["add_lots"] = 0; pos["fallback"] = None


def _fast(sp, t, i, pos, rule, scenario):
    r = t.q[i, pos["j"]]
    if not np.isfinite(r).all():
        return None
    cap = int(r[4] * .2) // sp.lot
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


def _open(sp, t, i, rule, j, filled, price, decision, sign, atr, room, origin, meta):
    if "slevel" in meta:
        us = float(meta["slevel"])
    elif "sd" in meta:
        us = float(t.close[decision] - sign * meta["sd"]) if np.isfinite(meta["sd"]) else -sign * math.inf
    else:
        us = float(t.close[decision] - sign * atr * rule.underlying_stop)
    dist = float(t.close[decision]) - us
    fut_stop = float(t.f[decision, 3] - dist) if np.isfinite(t.f[decision, 3]) else math.nan
    td = meta.get("td", math.nan); f0 = fee(sp, price, filled * sp.lot, True)
    return dict(day=t.day, j=j, symbol=t.symbols[j], direction=sign, entry_i=i, decision_i=decision, entry=price, lots=filled,
                open=filled, reserve=round(reserve(sp, price, filled), 2), peak=price,
                stop=0.0 if rule.no_pstop else round(price * (1 - rule.stop), 2),
                banked=False, origin=origin, net=-f0, fees=f0, underlying_stop=us, fut_stop=fut_stop,
                dec_close=float(t.close[decision]), dec_fut=float(t.f[decision, 3]), dec_atr=float(atr), room=room, first=price,
                tlevel=float(t.close[decision] + sign * td) if np.isfinite(td) else None,
                add_lots=meta.get("add", 0), planned=meta.get("planned", filled), retry="slevel" in meta, fallback=None,
                events=[dict(i=i, decision_i=decision, side="BUY", lots=filled, price=price, fees=f0)])


def _buy_more(sp, pos, i, decided, filled, price, reason, reset_stop):
    risk = reserve(sp, price, filled); fee0 = fee(sp, price, filled * sp.lot, True)
    avg = (pos["entry"] * pos["lots"] + price * filled) / (pos["lots"] + filled)
    pos["reserve"] = round(pos["reserve"] + risk, 2)
    pos["net"] = round(pos["net"] - fee0, 2); pos["fees"] = round(pos["fees"] + fee0, 2)
    pos["lots"] += filled; pos["open"] += filled; pos["entry"] = avg
    if reason == "ADD":
        pos["added"] = pos.get("added", 0) + filled
    else:
        pos["fallback_lots"] = pos.get("fallback_lots", 0) + filled
    if reset_stop == "reset":
        pos["stop"] = round(avg * (1 - pos["rule_stop"]), 2)
    elif reset_stop == "max":
        pos["stop"] = max(pos["stop"], round(avg * (1 - pos["rule_stop"]), 2))
    pos["events"].append(dict(i=i, decision_i=decided, side="BUY", reason=reason, lots=filled, price=price, fees=fee0))
    return risk


def run_day4(t, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False):
    sp = spec_of(t); LOT = sp.lot; k = rule.size_k
    assert rule.setup3 not in ("PAIR", "PIN", "LASTHALF") and not rule.bank_r and not rule.regime_min and not rule.squeeze
    dirs, sdist, tdist = signals(t, rule)
    spent = 0.0; positions = []; next_i = 0; pending_entry = None; pending_exit = None; pending_add = None; pos = None
    rejected = 0; missed = []; stopped = None; watch = None; notes = []
    for i in range(int(np.searchsorted(t.minute, rule.start)), t.n):
        closed = None
        if pending_exit:
            qty, reason, decided = pending_exit
            filled, price = executable(sp, t, i, pos["j"], "SELL", scenario, min(qty, pos["open"]))
            if filled:
                _sell(sp, pos, i, decided, reason, filled, price)
                if reason in ("TARGET_BASE", "PUT_RUNNER"):
                    pos["runner"] = True
                    pos["stop"] = max(round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
                if not pos["open"]:
                    cash = round(cash + pos["net"], 2); pos["exit_i"] = i; positions.append(pos); closed = pos
                    stopped = L3._stopped(t, pos, stopped); pos = None; pending_exit = None; next_i = i + 5
                else:
                    pending_exit = (pos["open"], reason, decided) if reason not in PARTIAL + ("PUT_RUNNER",) else None
            elif reason in PARTIAL + ("PUT_RUNNER",):
                pending_exit = None
            if pending_exit:
                continue
        if pending_add and pos:
            n, decided, lim, why = pending_add; pending_add = None
            if why == "ADD":
                pos["add_lots"] = 0
            filled, price = executable(sp, t, i, pos["j"], "BUY", scenario, n)
            if filled and price is not None and price <= lim:
                left = pos["room"] - pos["reserve"]
                while filled and reserve(sp, price, filled) > left + .01:
                    filled -= 1
                if filled:
                    spent += _buy_more(sp, pos, i, decided, filled, price, why,
                                       "max" if (rule.scout or why == "FALLBACK") and not rule.no_pstop else "none" if rule.no_pstop else "reset")
        if pending_entry:
            j, lots, limit, decision, sign, atr, room, origin, meta = pending_entry
            share = .2
            if rule.passive:
                r = t.q[i, j]; P = meta["passive"]; thr = P - (.05 if scenario == "ordinary" else .10)
                cap = int(r[4] * .2) // LOT if np.isfinite(r).all() else 0
                if cap > 0 and r[2] <= thr + 1e-9:
                    filled, price = min(lots, cap), P; pending_entry = None
                elif i - decision < 2:
                    continue
                else:
                    pending_entry = None; missed.append(dict(day=t.day, decision_i=decision, direction=sign, j=j)); continue
            elif rule.patient and meta.get("stage") != "fallback":
                r = t.q[i, j]; P = meta["passive"]; pending_entry = None
                if rule.patient == "cons":
                    thr, share = P - (.05 if scenario == "ordinary" else .10), .10
                else:
                    thr, share = P, .2
                cap = int(r[4] * share) // LOT if np.isfinite(r).all() else 0
                filled, price = (min(lots, cap), P) if cap > 0 and r[2] <= thr + 1e-9 else (0, None)
                rest = lots - filled
                ok_fb = rest > 0 and np.isfinite([t.f[i, 3], t.f[decision, 3], t.close[i]]).all() and sign * (t.f[i, 3] - t.f[decision, 3]) > 0
                lim2 = min(E.down(meta["ask0"] * 1.04), limit)
                if filled:
                    while filled and reserve(sp, price, filled) > room + .01:
                        filled -= 1
                if not filled:
                    us = _us(t, rule, decision, sign, atr, meta)
                    if ok_fb and sign * (t.close[i] - us) > 0 and t.minute[i] < rule.end + 1 and i < t.n - 1:
                        meta = dict(meta, stage="fallback"); pending_entry = (j, lots, lim2, decision, sign, atr, room, origin, meta)
                    else:
                        missed.append(dict(day=t.day, decision_i=decision, direction=sign, j=j))
                    continue
                if rest and ok_fb:
                    meta = dict(meta, fb=(rest, lim2))
            else:
                pending_entry = None
                filled, price = executable(sp, t, i, j, "BUY", scenario, lots)
            if filled < max(1, math.ceil(lots * .25)) or price is None or price > limit:
                if not (rule.patient and filled and price is not None and price <= limit):
                    rejected += 1; continue
            risk = reserve(sp, price, filled); assert risk <= room + .01
            spent += risk
            pos = _open(sp, t, i, rule, j, filled, price, decision, sign, atr, room, origin, meta); pos["rule_stop"] = rule.stop
            if meta.get("fb"):
                pos["fallback"] = (meta["fb"][0], decision, meta["fb"][1])
        if pos:
            row = t.q[i, pos["j"]]
            bid = E.down(float(row[3]) - E.half(float(row[3]))) if np.isfinite(row[3]) and np.isfinite(row[4]) and row[4] * .2 >= LOT else None
            if rule.fast_exit and not pos.get("runner") and t.minute[i] < rule.flat:
                fx = _fast(sp, t, i, pos, rule, scenario)
                if fx:
                    filled, price, reason = fx; _sell(sp, pos, i, i, reason, filled, price)
                    if not pos["open"]:
                        cash = round(cash + pos["net"], 2); pos["exit_i"] = i; positions.append(pos); closed = pos
                        stopped = L3._stopped(t, pos, stopped); pos = None; next_i = i + 5
                    elif i < t.n - 1:
                        pending_exit = (pos["open"], reason, i)
                    if pos is not None:
                        continue
            if pos is not None:
                reason, qty = _decide(sp, t, i, pos, rule, bid, row)
                if reason is None and pos.get("fallback") and i < t.n - 1:
                    n, decided, lim2 = pos["fallback"]; pos["fallback"] = None
                    if pos["direction"] * (t.close[i] - pos["underlying_stop"]) > 0:
                        pending_add = (n, decided, lim2, "FALLBACK")
                elif reason is None and rule.scout and pos["add_lots"] and not pos.get("runner") and 2 <= i - pos["entry_i"] <= 6 \
                        and i - pos["entry_i"] < rule.hold and bid is not None and i >= 1 and _progress(t, i, pos):
                    pending_add = (pos["add_lots"], i, E.down(ask_of(row[3]) * (1 + rule.chase)), "ADD")
                elif reason is None and rule.scale_in and pos["add_lots"] and not pos.get("runner") and i - pos["entry_i"] <= 3 \
                        and pos.get("_intact") and bid is not None and bid >= pos["first"] * 1.2 and np.isfinite(row[3]):
                    pending_add = (pos["add_lots"], i, E.down(E.up(float(row[3]) + E.half(float(row[3]))) * (1 + rule.chase)), "ADD")
                if reason:
                    pos["fallback"] = None
                if reason and i < t.n - 1:
                    pending_exit = (qty, reason, i)
                continue
        if closed is not None and rule.reverse:
            watch = _arm_watch(t, rule, closed, i, len(positions))
        if pending_exit or pending_entry or i >= t.n - 1 or len(positions) >= rule.slots:
            continue
        sign, meta, normal = 0, {}, False
        if watch:
            sign, meta, watch = _watch(t, rule, watch, i)
        if not sign:
            normal = True
            if i < next_i:
                continue
            sign = int(dirs[i])
            if not sign:
                continue
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
        room = min(E.BUDGET / rule.slots * mult * k, budget - spent, cash)
        if room <= 0:
            continue
        cap = int(round(rule.max_lots * mult * k))
        if rule.atm_itm:
            pick = choose_atm(sp, t, i, sign, room, rule.chase)
        else:
            pick = choose4(sp, t, i, sign, replace(rule, max_lots=cap) if cap != rule.max_lots else rule, room, cash)
        if pick:
            j, lots, limit = pick
            if meta.get("max_lots"):
                lots = min(lots, meta["max_lots"])
            if (rule.scale_in or rule.scout) and lots >= 2:
                first = math.ceil(lots / 2); meta.update(add=lots - first, planned=lots); lots = first
            if rule.passive or rule.patient:
                qc = float(t.q[i, j, 3]); meta["passive"] = E.down(qc - E.half(qc)); meta["ask0"] = ask_of(qc)
                if meta["passive"] <= 0:
                    continue
            origin = meta.pop("origin", None) or ("E032" if not rule.setup3 else rule.setup3)
            pending_entry = (j, lots, limit, i, sign, t.features[rule.look][i, 4], room, origin, meta)
            if normal:
                watch = None
    unresolved = 0
    if pos:
        unresolved = 1
        pos["net"] = round(pos["net"] - pos["entry"] * pos["open"] * LOT, 2); pos["unresolved"] = True; positions.append(pos)
    net = round(sum(p["net"] for p in positions), 2)
    assert spent <= budget + .02 and net >= -spent - .03, (t.day, spent, budget, net)
    return dict(day=t.day, net=net, trades=len(positions), spent=round(spent, 2), fees=round(sum(p["fees"] for p in positions), 2),
                unresolved=unresolved, rejected=rejected, positions=positions if details else [], marked_worst=0., calm=False,
                missed=missed if details else [])


def _us(t, rule, decision, sign, atr, meta):
    if "slevel" in meta:
        return float(meta["slevel"])
    if "sd" in meta:
        return float(t.close[decision] - sign * meta["sd"]) if np.isfinite(meta["sd"]) else -sign * math.inf
    return float(t.close[decision] - sign * atr * rule.underlying_stop)


def _progress(t, i, pos):
    d = pos["direction"]
    if not np.isfinite([t.close[i], t.close[i - 1], t.f[i, 3], t.f[i - 1, 3]]).all() or not pos.get("_intact"):
        return False
    row = t.q[i, pos["j"]]; bid = E.down(float(row[3]) - E.half(float(row[3])))
    return (d * (t.close[i] - pos["dec_close"]) >= .25 * pos["dec_atr"] and d * (t.close[i] - t.close[i - 1]) > 0
            and d * (t.f[i, 3] - t.f[i - 1, 3]) > 0 and bid > pos["first"])


def _decide(sp, t, i, pos, rule, bid, row):
    """en_lab3's exit ladder (unchanged order), with EN26 / EN29 appended where PLAN4.md puts them."""
    reason = None; qty = pos["open"]; pos["_intact"] = False
    if t.minute[i] >= rule.flat:
        return "FLAT_TIME", qty
    if bid is not None and bid > 0 and pos.get("runner") and rule.split:
        pos["peak"] = max(pos["peak"], bid)
        pos["stop"] = max(pos["stop"], round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
        if bid <= pos["stop"]:
            reason = "RUNNER_TRAIL"
        elif rule.hero_target and bid >= pos["entry"] * (1 + rule.hero_target):
            reason = "HERO_TARGET"
        elif rule.runner_struct and np.isfinite(t.close[i]) and pos["direction"] * (t.close[i] - pos["dec_close"]) < 0:
            reason = "RUNNER_STRUCT"
        elif rule.runner_stall and _stall(t, i, pos):
            reason = "RUNNER_STALL"
        return reason, qty
    if bid is None or bid <= 0:
        return None, qty
    pos["peak"] = max(pos["peak"], bid)
    gain = pos["peak"] / pos["entry"] - 1
    if gain >= rule.arm:
        pos["stop"] = max(pos["stop"], round(pos["peak"] * rule.keep, 2))
    if rule.lock_arm and gain >= rule.lock_arm:
        pos["stop"] = max(pos["stop"], round(pos["entry"] * rule.lock_floor, 2))
    intact = not (np.isfinite(t.close[i]) and rule.underlying_stop > 0 and pos["direction"] * (t.close[i] - pos["underlying_stop"]) < 0)
    pos["_intact"] = intact
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
                kk = recover_lots(sp, pos, bid)
                if 1 <= kk < pos["open"]:
                    reason, qty = "TARGET_BASE", kk
            else:
                reason, qty = "TARGET_BASE", pos["open"] - pos["open"] // 2
        elif rule.split and rule.solo_runner and pos["open"] == 1:
            reason = None; pos["runner"] = True
            pos["stop"] = max(round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
    elif L.stalled(rule, i, pos, bid):
        reason = "STALL"
    elif not rule.no_clock and L.timed_out(t, rule, i, pos, bid, gain):
        reason = "TIME"
        if rule.put_runner and pos["direction"] < 0 and pos["open"] >= 2 and bid >= pos["entry"] * rule.put_runner:
            reason, qty = "PUT_RUNNER", pos["open"] - pos["open"] // 2
    if reason is None and rule.damage:
        reason = _damage(t, i, pos, rule, bid, row)
    return reason, qty


def _damage(t, i, pos, rule, bid, row):
    """EN26 (minute adaptation) and its catastrophe diagnostic; only on the loss stop (stop below entry)."""
    if not np.isfinite(row).all():
        pos["suspect"] = None; return None
    lbid = E.down(float(row[2]) - E.half(float(row[2]))); st = pos["stop"]
    if rule.damage == "cat":
        return "CATASTROPHE" if lbid <= .40 * pos["entry"] else None
    d = pos["direction"]
    if pos.get("suspect") == i - 1:
        pos["suspect"] = None
        ok = np.isfinite([t.close[i], t.f[i, 3], pos["dec_fut"], pos["dec_atr"]]).all()
        if ok and bid <= 1.10 * st and d * (t.close[i] - pos["dec_close"]) <= -.5 * pos["dec_atr"] and d * (t.f[i, 3] - pos["dec_fut"]) < 0:
            return "DAMAGE"
    if 0 < st < pos["entry"] and lbid <= st < bid:
        pos["suspect"] = i
    return None


def _stall(t, i, pos):
    """EN29: two completed minutes without a new favourable index extreme and a futures close through the prior
    two-minute opposing swing. The extreme is tracked from the bar of the 2x sale."""
    d = pos["direction"]
    if not np.isfinite(t.x[i]).all() or not np.isfinite(t.f[i - 2:i + 1]).all():
        return False
    ext = t.x[i, 1] if d > 0 else t.x[i, 2]
    if "rx" not in pos:
        pos["rx"], pos["stall"] = float(ext), 0; return False
    if d * (ext - pos["rx"]) > 0:
        pos["rx"], pos["stall"] = float(ext), 0; return False
    pos["stall"] += 1
    brk = t.f[i, 3] < min(t.f[i - 1, 2], t.f[i - 2, 2]) if d > 0 else t.f[i, 3] > max(t.f[i - 1, 1], t.f[i - 2, 1])
    return pos["stall"] >= 2 and bool(brk)


def _arm_watch(t, rule, closed, i, n_positions):
    """EN31: after an E03.2 ticket closes at a loss whose first sale was STOP/STRUCTURE, with an intent left."""
    first = next((e["reason"] for e in closed["events"] if e["side"] == "SELL"), "")
    if closed["origin"] != "E032" or closed["net"] >= 0 or first not in ("STOP", "STRUCTURE") or n_positions >= rule.slots:
        return None
    d = closed["direction"]; dec = closed["decision_i"]
    if rule.reverse == "flip":
        return dict(flip=True, d=-d, at=i)
    w = slice(dec - 10, dec)
    if dec < 10 or not np.isfinite(t.x[w]).all() or not np.isfinite(t.f[w]).all():
        return None
    hi, lo = float(np.max(t.x[w, 1])), float(np.min(t.x[w, 2])); fhi, flo = float(np.max(t.f[w, 1])), float(np.min(t.f[w, 2]))
    nd = -d
    return dict(flip=False, d=nd, until=i + 10, edge=lo if nd < 0 else hi, fedge=flo if nd < 0 else fhi, mid=(hi + lo) / 2,
                beyond=0, counter=False, start=i)


def _watch(t, rule, w, i):
    """Returns (sign, meta, watch-after)."""
    nd = w["d"]
    if w["flip"]:
        if t.minute[i] < rule.end and _avail(t, i, nd):
            return nd, dict(origin="FLIP"), None
        return 0, {}, None
    if i > w["until"] or t.minute[i] >= rule.end:
        return 0, {}, None
    c, f = t.close[i], t.f[i, 3]
    if not np.isfinite([c, f, t.close[i - 1]]).all():
        return 0, {}, w
    if nd * (c - w["mid"]) < 0:
        return 0, {}, None                                                  # the old midpoint was regained
    if i > w["start"] and nd * (c - t.close[i - 1]) < 0:
        w["counter"] = True
    w["beyond"] = w["beyond"] + 1 if nd * (c - w["edge"]) > 0 and nd * (f - w["fedge"]) > 0 else 0
    if w["beyond"] >= 2 and w["counter"] and _avail(t, i, nd):
        return nd, dict(origin="REVERSE", sd=float(nd * (c - w["edge"])), td=math.nan), None
    return 0, {}, w


def run4(tapes, rule, scenario="ordinary", details=False):
    cash = peak = E.START_CASH; days = []; k = rule.size_k
    full = (rule.day_budget or E.BUDGET * R.day_scale(rule)) * k
    for t in tapes:
        dd = peak - cash
        scale = 0. if dd >= 4000 * k else .25 if dd >= 3000 * k else .5 if dd >= 1500 * k else 1.
        row = run_day4(t, rule, scenario, cash, min(full * scale, cash), details)
        cash = round(cash + row["net"], 2); peak = max(peak, cash); assert cash >= -.01
        row.update(cash_after=cash, scale=scale); days.append(row)
    return dict(rule=asdict(rule), scenario=scenario, summary=E.summary(days), days=days)


# ---------------------------------------------------------------- checks (counts only)
def _patch():
    """en_lab3's frozen setup signals read futures volume and coverage through module globals."""
    import en4_data as D4
    orig = L3.futvol

    def futvol(t):
        return D4.futvol(t) if hasattr(t, "und") else orig(t)
    L3.futvol = futvol; L3.AVAIL = available; M.AVAIL = available
    L3.futvol.orig = orig


def theta():
    """EN36's threshold: the median straddle ratio over every coverage-available E03.2 signal minute, NIFTY 2023-25."""
    T = M.tapes(); v = []
    for y in (2023, 2024, 2025):
        for t in T[y]:
            d = masked(t, E032, M.directions(t, E032))
            v += [straddle_ratio(t, int(i)) for i in np.flatnonzero(d)]
    ok = [x for x in v if np.isfinite(x)]
    return round(float(np.median(ok)), 4), len(v), len(ok)


def check(quick=False):
    import exam2023b as C
    _patch()
    T = M.tapes(); years = (2023, 2024, 2025)
    # 1-2. hooks off == E03.2; frozen round-3 arms == en_lab3 (en_lab3 under the same coverage rule)
    saved = E.directions
    E.directions = C.masked; L.CACHE.clear()
    try:
        L3.AVAIL = C.available_at; L3.M.AVAIL = C.available_at
        pairs = [("E032", E032, L3.E032)] + [(k, ARMS[k], L3.ARMS[k]) for k in ("EN11", "EN12", "EN12_full_sale_diag", "EN13", "EN14",
                                                                                "EN14_immediate_diag", "EN21", "EN25")]
        ref = {}
        for name, _, old in pairs:
            for y in years:
                for sc in ("ordinary", "adverse", "catastrophe"):
                    ref[name, y, sc] = [d["net"] for d in L3.run(T[y], old, sc)["days"]]
    finally:
        E.directions = saved; L.CACHE.clear(); L3._SIG.clear()
    L3.AVAIL = available; M.AVAIL = available
    for name, new, _ in pairs:
        for y in years:
            for sc in ("ordinary", "adverse", "catastrophe"):
                got = [d["net"] for d in run4(T[y], new, sc)["days"]]
                assert got == ref[name, y, sc], (name, y, sc, [(a, b) for a, b in zip(got, ref[name, y, sc]) if a != b][:3])
    # 3. E03.1 through run_day4 == r8b_lab E03.1 (masked the same way)
    E.directions = C.masked; L.CACHE.clear()
    try:
        e031m = {(y, sc): [d["net"] for d in R.run(T[y], R.E031, sc)["days"]] for y in years for sc in ("ordinary", "adverse", "catastrophe")}
    finally:
        E.directions = saved; L.CACHE.clear()
    for y in years:
        for sc in ("ordinary", "adverse", "catastrophe"):
            got = [d["net"] for d in run4(T[y], E031, sc)["days"]]
            assert got == e031m[y, sc], ("E031", y, sc)
    # 4. choose4 == native pick on every signal minute, every reachable room
    n = 0
    for y in years:
        for t in T[y]:
            dd = masked(t, E032, M.directions(t, E032))
            for i in np.flatnonzero(dd):
                for room in (1250., 2500., 800.):
                    for cap in (3, 6):
                        r = replace(E032, max_lots=cap)
                        assert choose4(NIFTY, t, int(i), int(dd[i]), r, room, 25000.) == L.choose(t, int(i), int(dd[i]), r, room, 25000.)
                        n += 1
    # 5. SENSEX arithmetic
    assert SENSEX.lot == 20 and SENSEX.step == 100 and abs(SENSEX.order - 23.6) < 1e-9
    f = E.EP.fee_schedule("BFO")
    assert abs(fee(SENSEX, 40., 40, True) - round(E.EP.buy_charges(40., 40, f), 2)) <= .011
    assert abs(fee(SENSEX, 40., 40, False) - round(E.EP.sell_charges(40., 40, f), 2)) <= .011
    assert abs(reserve(SENSEX, 40., 2) - (40 * 40 + fee(SENSEX, 40., 40, True) + 2 * 23.6)) < 1e-9
    print("CHECK_OK en_lab4: run_day4 == E03.2, E03.1 and 8 frozen round-3 arms day by day (2023-25 x 3 fills);",
          n, "choose4 == native picks; SENSEX lot/fees/steps")
    print(synthetic())
    if quick:
        return
    # counts only: every new arm runs on development and on every exam cohort
    import en4_data as D4
    X4 = D4.tapes(); counts = {}
    for name in ARMS:
        if name == "EN36":
            continue
        for y in years:
            run4(T[y], ARMS[name], "ordinary")
        for c, ts in X4.items():
            run4(ts, ARMS[name], "ordinary")
    for name in ("EN13", "EN14", "EN30", "EN32"):
        counts[name] = {y: int(sum(np.count_nonzero(setup_signals(t, ARMS[name])[0]) for t in T[y])) for y in years}
        counts[name].update({c: int(sum(np.count_nonzero(setup_signals(t, ARMS[name])[0]) for t in ts)) for c, ts in X4.items()})
    feas = {}
    for y in years:
        tot = ok = 0
        for t in T[y]:
            dd = setup_signals(t, ARMS["EN32"])[0]
            for i in np.flatnonzero(dd):
                tot += 1; ok += choose_atm(NIFTY, t, int(i), int(dd[i]), 1250.) is not None
        feas[y] = (ok, tot)
    print("signal counts:", counts)
    print("EN32 affordable ATM/ITM one lot among range signals (count only):", feas)




# ---------------------------------------------------------------- synthetic mechanism checks (no market data)
def _synthetic_tape(prem, index_step=0., fut_step=None, vol=None, lows=None, highs=None, opens=None, day="2099-01-06"):
    import en4_data as D4
    D = D4._D(); n = 375
    base = 25000. + np.cumsum(np.full(n, index_step)); wob = np.where(np.arange(n) % 2, 7., -7.)
    c = base + wob; x = np.column_stack([c, c + 8., c - 8., c])
    fs = index_step if fut_step is None else fut_step
    fc = 25100. + np.cumsum(np.full(n, fs)) + wob; f = np.column_stack([fc, fc + 8., fc - 8., fc])
    q = np.full((n, 1, 5), np.nan); p = np.asarray(prem, float)
    o = p.copy() if opens is None else np.asarray(opens, float)
    lo = np.minimum(o, p) - .02 if lows is None else np.asarray(lows, float)
    hi = np.maximum(o, p) + .02 if highs is None else np.asarray(highs, float)
    q[:, 0, 0], q[:, 0, 1], q[:, 0, 2], q[:, 0, 3] = o, hi, lo, p
    q[:, 0, 4] = 1e6 if vol is None else vol
    from datetime import datetime, timedelta
    now = [datetime.fromisoformat(day + "T09:15:00").replace(tzinfo=D.EP.IST) + timedelta(minutes=i + 1) for i in range(n)]
    t = D.Tape(day, x, f, q, np.array([25100.]), np.array([1]), ["SYN-25100-CE"], now, np.arange(556, 931), 0)
    return t


def _run_synth(t, rule, i0, d=1):
    global signals
    saved = signals
    def fake(tt, rr):
        dirs = np.zeros(tt.n, dtype=np.int8); dirs[i0] = d; return dirs, None, None
    signals = fake
    try:
        return run_day4(t, rule, "ordinary", details=True)
    finally:
        signals = saved


def synthetic():
    i0 = 244                                                    # 13:00 bar end + 20 minutes
    n = 375
    # EN27: three planned lots -> two first, one add on confirmed progress; the stop never moves down
    p = np.full(n, 5.0); p[i0 + 1:] = np.linspace(5.0, 8.0, n - i0 - 1)
    t = _synthetic_tape(p, index_step=0.)
    t.x[i0 + 1:, 3] = t.x[i0 + 1:, 0] = t.close[i0] + np.arange(1, n - i0) * 6.; t.x[i0 + 1:, 1] = t.x[i0 + 1:, 3] + 8; t.x[i0 + 1:, 2] = t.x[i0 + 1:, 3] - 8
    t.f[i0 + 1:, 3] = t.f[i0, 3] + np.arange(1, n - i0) * 6.; t.f[i0 + 1:, 1] = t.f[i0 + 1:, 3] + 8; t.f[i0 + 1:, 2] = t.f[i0 + 1:, 3] - 8
    t.__post_init__()
    r = _run_synth(t, ARMS["EN27"], i0)
    pos = r["positions"][0]; buys = [e for e in pos["events"] if e["side"] == "BUY"]
    assert [e["lots"] for e in buys] == [2, 1] and buys[1]["reason"] == "ADD", buys
    assert 3 <= buys[1]["i"] - buys[0]["i"] <= 7 and pos["stop"] >= round(buys[0]["price"] * .65, 2), pos
    r21 = _run_synth(t, ARMS["EN21"], i0)                      # EN21's own deadline (3 bars at +20%) on the same path
    assert sum(e["lots"] for e in r21["positions"][0]["events"] if e["side"] == "BUY") in (2, 3)
    # EN28: no passive trade-through -> fallback at i0+2 inside 1.04 x decision ask; exits start at that fill
    p = np.full(n, 5.0); lows = p - .02; lows[i0 + 1] = 4.95
    t = _synthetic_tape(p, index_step=0., lows=lows)
    r = _run_synth(t, ARMS["EN28"], i0)
    pos = r["positions"][0]; b0 = pos["events"][0]
    assert b0["i"] == i0 + 2 and b0["price"] <= E.down(ask_of(5.0) * 1.04) and pos["entry_i"] == i0 + 2, pos["events"]
    # EN28: one passive lot (thin bar), the rest by the fallback at the next bar; fees per fill
    vol = np.full(n, 1e6); vol[i0 + 1] = 700.; lows = p - .02; lows[i0 + 1] = 4.80
    t = _synthetic_tape(p, index_step=0., lows=lows, vol=vol)
    r = _run_synth(t, ARMS["EN28"], i0)
    ev = [e for e in r["positions"][0]["events"] if e["side"] == "BUY"]
    assert ev[0]["i"] == i0 + 1 and ev[0]["lots"] == 1 and ev[0]["price"] == E.down(5.0 - E.half(5.0)), ev
    assert len(ev) == 2 and ev[1]["i"] == i0 + 2 and ev[1]["reason"] == "FALLBACK" and r["positions"][0]["entry_i"] == i0 + 1, ev
    # EN28: futures falling after the decision -> no fallback, the ticket is missed
    lows = p - .02; lows[i0 + 1] = 4.95
    t = _synthetic_tape(p, index_step=0., fut_step=-20., lows=lows)
    r = _run_synth(t, ARMS["EN28"], i0)
    assert not r["positions"] and len(r["missed"]) == 1
    # EN26: a wick through the stop starts SUSPECT; the next completed minute near the stop with the index and future
    # adverse confirms -> DAMAGE sold at the bar after; E03.2 on the same path holds until its own stop
    p = np.full(n, 5.0); p[i0 + 3:] = 3.6; lows = p - .02; lows[i0 + 3] = 3.2
    t = _synthetic_tape(p, index_step=0., lows=lows)
    t.x[i0 + 3:, 3] = t.x[i0 + 3:, 0] = t.close[i0] - 40.; t.x[i0 + 3:, 1] = t.x[i0 + 3:, 3] + 8; t.x[i0 + 3:, 2] = t.x[i0 + 3:, 3] - 8
    t.f[i0 + 3:, 3] = t.f[i0, 3] - 40.; t.f[i0 + 3:, 1] = t.f[i0 + 3:, 3] + 8; t.f[i0 + 3:, 2] = t.f[i0 + 3:, 3] - 8
    t.__post_init__()
    r = _run_synth(t, replace(ARMS["EN26"], underlying_stop=50.), i0)
    sells = [e for e in r["positions"][0]["events"] if e["side"] == "SELL"]
    assert sells[0]["reason"] == "DAMAGE" and sells[0]["i"] == i0 + 5 and sells[0]["decision_i"] == i0 + 4, sells
    r0 = _run_synth(t, replace(E032, underlying_stop=50.), i0)
    assert [e["reason"] for e in r0["positions"][0]["events"] if e["side"] == "SELL"][0] != "DAMAGE"
    # EN29: 2x partial sale, then two minutes without a new index high and a futures break -> RUNNER_STALL
    p = np.full(n, 5.0); p[i0 + 2:] = 10.6
    t = _synthetic_tape(p, index_step=0.)
    up_ = np.arange(1, n - i0) * 5.
    t.x[i0 + 1:, 3] = t.x[i0 + 1:, 0] = t.close[i0] + up_; t.x[i0 + 1:, 1] = t.x[i0 + 1:, 3] + 8; t.x[i0 + 1:, 2] = t.x[i0 + 1:, 3] - 8
    t.f[i0 + 1:, 3] = t.f[i0, 3] + up_; t.f[i0 + 1:, 1] = t.f[i0 + 1:, 3] + 8; t.f[i0 + 1:, 2] = t.f[i0 + 1:, 3] - 8
    k0 = i0 + 6                                                  # from here the index stops making highs and the future breaks
    t.x[k0:, :] = t.x[k0 - 1, :] - 3.; t.f[k0:, 3] = t.f[k0 - 1, 2] - 20. - 20. * np.arange(n - k0); t.f[k0:, 1] = t.f[k0:, 3] + 4; t.f[k0:, 2] = t.f[k0:, 3] - 4
    t.f[k0:, 0] = t.f[k0:, 3]
    t.__post_init__()
    r = _run_synth(t, ARMS["EN29"], i0)
    path = [e["reason"] for e in r["positions"][0]["events"] if e["side"] == "SELL"]
    assert path[0] == "TARGET_BASE" and "RUNNER_STALL" in path, path
    stall_i = [e["decision_i"] for e in r["positions"][0]["events"] if e.get("reason") == "RUNNER_STALL"][0]
    assert stall_i == k0 + 1, (stall_i, k0)                   # the second minute without a new high, with the break
    r0 = _run_synth(t, E032, i0)
    assert "RUNNER_STALL" not in [e["reason"] for e in r0["positions"][0]["events"] if e["side"] == "SELL"]
    # EN31: the call is stopped; the index and the future then close below the pre-signal lows twice, with a counter-move
    # and no close back above the old midpoint -> one put, decided on the second close beyond; the flip diagnostic buys
    # the put on the exit bar itself
    global available
    p = np.full(n, 5.0); p[i0 + 2:] = 3.0
    t = _synthetic_tape(p, index_step=0.)
    D = __import__("en4_data")._D()
    q = np.full((n, 2, 5), np.nan); q[:, 0, :] = t.q[:, 0, :]
    q[:, 1, 0] = q[:, 1, 3] = 8.; q[:, 1, 1] = 8.02; q[:, 1, 2] = 7.98; q[:, 1, 4] = 1e6
    t = D.Tape(t.day, t.x, t.f, q, np.array([25100., 24850.]), np.array([1, -1]), ["SYN-25100-CE", "SYN-24850-PE"], t.now, t.minute, 0)
    lo_pre, flo_pre = float(np.min(t.x[i0 - 10:i0, 2])), float(np.min(t.f[i0 - 10:i0, 2]))
    path_c = [lo_pre - 10, lo_pre - 15, lo_pre - 13, lo_pre - 25, lo_pre - 35]
    for kk, cc in enumerate(path_c):
        ii = i0 + 3 + kk; t.x[ii] = [cc, cc + 2, cc - 2, cc]; ff = flo_pre - 10 - 5 * kk; t.f[ii] = [ff, ff + 2, ff - 2, ff]
    t.x[i0 + 8:] = t.x[i0 + 7]; t.f[i0 + 8:] = t.f[i0 + 7]
    t.__post_init__()
    saved_av = available
    available = lambda tt, ii, dd: True  # noqa: E731
    try:
        r = _run_synth(t, ARMS["EN31"], i0)
        assert len(r["positions"]) == 2 and r["positions"][0]["events"][1]["reason"] == "STOP", r["positions"]
        rv = r["positions"][1]
        assert rv["origin"] == "REVERSE" and rv["direction"] == -1 and rv["decision_i"] == i0 + 5, (rv["origin"], rv["decision_i"])
        assert abs(rv["underlying_stop"] - lo_pre) < 1e-6
        r = _run_synth(t, ARMS["EN31_flip_diag"], i0)
        fl = r["positions"][1]
        assert fl["origin"] == "FLIP" and fl["decision_i"] == r["positions"][0]["exit_i"], (fl["origin"], fl["decision_i"])
        r = _run_synth(t, E032, i0)
        assert len(r["positions"]) == 1
    finally:
        available = saved_av
    return "SYNTHETIC_OK EN26 EN27 EN28 EN29 EN31"


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "theta":
        _patch(); print("THETA", theta())
    else:
        check(quick=len(sys.argv) > 1 and sys.argv[1] == "quick")

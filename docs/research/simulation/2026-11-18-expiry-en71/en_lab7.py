"""EN71-EN85 lab (PLAN7.md). `run_day7` is a hooked copy of the frozen en_lab6.run_day6; with every round-7 hook off it
reproduces run_day6 day by day (check_parity). Round 7 adds no monkeypatch.

Round-7 Rule fields (all off by default):
  room_mode    'loss': the auditor's daily room - day budget minus realised losses so far (profits add nothing), and the
               open parent's commitment; every initial buy and add must fit it. '' = run_day6's reserve accounting.
  max_parents  parents a day (0 = rule.slots, as run_day6)
  entry_delay  EN81: whole bars between the decision and the entry order (the capped limit still binds)
  gate         EN82 'ADX30' / 'ADX25' / 'ADX30_INV' (yesterday's NIFTY daily ADX(14), the pinned engine's formula);
               EN84 'RVOL' / 'RVOL_INV' (the last closed 5-minute NIFTY future bar's time-adjusted volume >= 1.2)
  blind_add    EN72's control: the scout's split, the second half bought two bars later without the favourable check
Setups (setup3 in SETUPS7, precomputed causally per tape by prepare7): RIDGE73*, SYNF75*, N11_76, BASIS78*, OI83*.
Stress: PERT7 sell_delay (every sale one bar late: missed exits) and extra_fee (one more order charge per parent)."""
from __future__ import annotations
from contextlib import contextmanager
from dataclasses import dataclass, asdict, replace
import hashlib, json, math, random, sys
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-18-expiry-en56"))
import en_lab6 as L6  # noqa: E402
import fut7  # noqa: E402

L5, L4, L3, M, R, X, E, D4 = L6.L5, L6.L4, L6.L3, L6.M, L6.R, L6.X, L6.E, L6.D4
YM = L6.YM
SEED = 20261119
und, at, atr, forward, ivol, price = L6.und, L6.at, L6.atr, L6.forward, L6.ivol, L6.price
LOCAL = HERE / "_local"
FACTS = json.loads((HERE / "facts7.json").read_text()) if (HERE / "facts7.json").exists() else {}
FUT_SPREAD = {"NIFTY": 4.4, "SENSEX": 4.4}        # PLAN7 s.6: Nov 17 recorder median (NIFTY); SENSEX has no measurement, same number


@dataclass(frozen=True)
class Rule(L6.Rule):
    room_mode: str = ""
    max_parents: int = 0
    entry_delay: int = 0
    gate: str = ""
    blind_add: bool = False


def R7(rule, **kw):
    return replace(Rule(**asdict(rule)), **kw)


E032 = R7(L6.E032)
EN55 = R7(L6.EN55)
ENV7 = dict(slots=1, put_mult=1., call_mult=1., day_budget=2500., max_lots=3, max_intents=2, max_parents=2, room_mode="loss",
            start=780, end=870)
E03_ENV = R7(E032, **ENV7)

PERT7 = dict(sell_delay=0, extra_fee=0.)


@contextmanager
def stress(**kw):
    old = dict(PERT7); PERT7.update(kw)
    try:
        yield
    finally:
        PERT7.clear(); PERT7.update(old)


def _exe7(sp, t, i, j, side, scenario, lots):
    if side == "SELL" and PERT7["sell_delay"]:
        i += PERT7["sell_delay"]
        if i >= t.n:
            return 0, None
    return L6._exe(sp, t, i, j, side, scenario, lots)


# ---------------------------------------------------------------- vectorised Black (parity-checked against L5.price)
def _ncdf(x):
    from scipy.special import ndtr
    return ndtr(x)


def bsv(F, K, T, v, call):
    F = np.asarray(F, float)
    if T <= 0 or v <= 0:
        return np.maximum(0., F - K) if call else np.maximum(0., K - F)
    sd = v * math.sqrt(T); d1 = (np.log(F / K) + .5 * sd * sd) / sd; d2 = d1 - sd
    return F * _ncdf(d1) - K * _ncdf(d2) if call else K * _ncdf(-d2) - F * _ncdf(-d1)


# ---------------------------------------------------------------- precomputed setups and gates
PRE7 = {}          # (setup, und, day) -> np.int8 dirs (window-free; the window is applied in signals7)
META7 = {}         # (setup, und, day) -> list of event dicts (diagnostics)
GATE7 = {}         # ('ADX', day) -> float | None ; ('RVOL', day) -> {bar-end minute: float}
N11 = {}           # (und, day) -> n11x day record
SETUPS7 = {"RIDGE73", "RIDGE73_ZERO", "RIDGE73_ICPT", "RIDGE73_EXP", "RIDGE73_IVS", "SYNF75", "SYNF75_FUT", "SYNF75_LAG", "SYNF75_ONE",
           "N11_76", "BASIS78", "BASIS78_FUT", "BASIS78_MR", "BASIS78_MOM", "OI83", "OI83_PX", "OI83_INV"}


def signals7(t, rule):
    if rule.setup3 in SETUPS7:
        key = (rule.setup3, und(t), t.day)
        dirs = PRE7.get(key)
        dirs = np.zeros(t.n, np.int8) if dirs is None else dirs.copy()
        lo, hi = int(np.searchsorted(t.minute, rule.start)), int(np.searchsorted(t.minute, rule.end))
        dirs[:lo] = 0; dirs[hi:] = 0
        for i in np.flatnonzero(dirs):
            if not (L4._avail(t, int(i), int(dirs[i])) and np.isfinite(t.close[i])):
                dirs[i] = 0
        if L3.NULL is not None:
            dirs = L3.null_flip(t, dirs)
        return dirs, None, None
    dirs, sd, td = L6.signals6(t, rule)
    if rule.setup3 in L6.SETUPS6:                      # a round-6 setup inside the round-7 window (EN79's EN60 expert)
        lo, hi = int(np.searchsorted(t.minute, rule.start)), int(np.searchsorted(t.minute, rule.end))
        dirs = dirs.copy(); dirs[:lo] = 0; dirs[hi:] = 0
    return dirs, sd, td


def gated(t, rule, dirs):
    if not rule.gate:
        return dirs
    out = dirs.copy()
    if rule.gate.startswith("ADX"):
        v = GATE7.get(("ADX", t.day))
        lim = 25. if rule.gate == "ADX25" else 30.
        ok = v is not None and np.isfinite(v) and ((v < lim) if rule.gate.endswith("INV") else (v >= lim))
        if not ok:
            out[:] = 0
        return out
    rv = GATE7.get(("RVOL", t.day), {})
    for i in np.flatnonzero(dirs):
        m = int(t.minute[i]); m5 = 555 + 5 * ((m - 555) // 5)          # the last 5-minute bar closed by minute m
        v = rv.get(m5)
        ok = v is not None and np.isfinite(v) and ((v < 1.2) if rule.gate.endswith("INV") else (v >= 1.2))
        if not ok:
            out[i] = 0
    return out


# ---------------------------------------------------------------- the day loop (hooked copy of en_lab6.run_day6)
LOG_INTENTS = None
KEEP7 = []


def run_day7(t, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False):
    sp = L4.spec_of(t); LOT = sp.lot; k = rule.size_k
    assert rule.setup3 not in ("PAIR", "PIN", "LASTHALF") and not rule.bank_r and not rule.regime_min and not rule.squeeze
    assert not (rule.core_bank or rule.core_child or rule.ladder or rule.liq_pick), "round-6 EN63/EN65/ladder hooks: use run_day6"
    dirs, sdist, tdist = signals7(t, rule)
    dirs = gated(t, rule, dirs)
    spent = 0.0; positions = []; next_i = 0; pending_entry = None; pending_exit = None; pending_add = None; pos = None
    rejected = 0; missed = []; stopped = None; watch = None; intents = 0; due = -1
    cap_parents = rule.max_parents or rule.slots
    for i in range(int(np.searchsorted(t.minute, rule.start)), t.n):
        closed = None
        if pending_exit:
            qty, reason, decided = pending_exit
            filled, px = _exe7(sp, t, i, pos["j"], "SELL", scenario, min(qty, pos["open"]))
            if filled:
                L4._sell(sp, pos, i, decided, reason, filled, px)
                if reason in ("TARGET_BASE", "PUT_RUNNER"):
                    pos["runner"] = True
                    pos["stop"] = max(round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
                if not pos["open"]:
                    cash = round(cash + pos["net"], 2); pos["exit_i"] = i; positions.append(pos); closed = pos
                    stopped = L3._stopped(t, pos, stopped); pos = None; pending_exit = None; next_i = i + 5
                else:
                    pending_exit = (pos["open"], reason, decided) if reason not in L6.PARTIAL + ("PUT_RUNNER",) else None
            elif reason in L6.PARTIAL + ("PUT_RUNNER",):
                pending_exit = None
            if pending_exit:
                continue
        if pending_add and pos:
            n, decided, lim, why = pending_add; pending_add = None
            if why in ("ADD", "BLIND"):
                pos["add_lots"] = 0
            filled, px = _exe7(sp, t, i, pos["j"], "BUY", scenario, n)
            if filled and px is not None and px <= lim:
                left = pos["room"] - pos["reserve"]
                while filled and L4.reserve(sp, px, filled) > left + .01:
                    filled -= 1
                if filled:
                    spent += L4._buy_more(sp, pos, i, decided, filled, px, "ADD" if why == "BLIND" else why,
                                          "max" if (rule.scout or rule.blind_add or why == "FALLBACK") and not rule.no_pstop else "none" if rule.no_pstop else "reset")
        if pending_entry and i < due:
            continue
        if pending_entry:
            j, lots, limit, decision, sign, a_, room, origin, meta = pending_entry
            share = .2
            if rule.passive:
                r = t.q[i, j]; P = meta["passive"]; thr = P - (.05 if scenario == "ordinary" else .10)
                cap = int(r[4] * .2) // LOT if np.isfinite(r).all() else 0
                if cap > 0 and r[2] <= thr + 1e-9:
                    filled, px = min(lots, cap), P; pending_entry = None
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
                thr -= L6.PERT["ticks"] * .05
                cap = int(r[4] * share) // LOT if np.isfinite(r).all() else 0
                hit = cap > 0 and r[2] <= thr + 1e-9
                if hit and L6.PERT["passive"] == "none":
                    hit = False
                elif hit and L6.PERT["passive"] == "adversarial":
                    hit = L6._loses_later(t, j, decision, P)
                filled, px = (min(lots, cap), P) if hit else (0, None)
                rest = lots - filled
                ok_fb = rest > 0 and np.isfinite([t.f[i, 3], t.f[decision, 3], t.close[i]]).all() and sign * (t.f[i, 3] - t.f[decision, 3]) > 0
                lim2 = min(E.down(meta["ask0"] * 1.04), limit)
                if filled:
                    while filled and L4.reserve(sp, px, filled) > room + .01:
                        filled -= 1
                if not filled:
                    us = L4._us(t, rule, decision, sign, a_, meta)
                    if ok_fb and sign * (t.close[i] - us) > 0 and t.minute[i] < rule.end + 1 and i < t.n - 1:
                        meta = dict(meta, stage="fallback"); pending_entry = (j, lots, lim2, decision, sign, a_, room, origin, meta)
                    else:
                        missed.append(dict(day=t.day, decision_i=decision, direction=sign, j=j))
                    continue
                if rest and ok_fb:
                    meta = dict(meta, fb=(rest, lim2))
            else:
                pending_entry = None
                filled, px = _exe7(sp, t, i, j, "BUY", scenario, lots)
            if filled < max(1, math.ceil(lots * .25)) or px is None or px > limit:
                if not (rule.patient and filled and px is not None and px <= limit):
                    rejected += 1; continue
            risk = L4.reserve(sp, px, filled); assert risk <= room + .01
            spent += risk
            pos = L4._open(sp, t, i, rule, j, filled, px, decision, sign, a_, room, origin, meta); pos["rule_stop"] = rule.stop
            if meta.get("fb"):
                pos["fallback"] = (meta["fb"][0], decision, meta["fb"][1])
            if meta.get("xspec"):
                pos["xspec"] = dict(meta["xspec"])
        if pos:
            row = t.q[i, pos["j"]]
            bid = E.down(float(row[3]) - E.half(float(row[3]))) if np.isfinite(row[3]) and np.isfinite(row[4]) and row[4] * .2 >= LOT else None
            if rule.fast_exit and not pos.get("runner") and t.minute[i] < rule.flat:
                fx = L4._fast(sp, t, i, pos, rule, scenario)
                if fx:
                    filled, px, reason = fx; L4._sell(sp, pos, i, i, reason, filled, px)
                    if not pos["open"]:
                        cash = round(cash + pos["net"], 2); pos["exit_i"] = i; positions.append(pos); closed = pos
                        stopped = L3._stopped(t, pos, stopped); pos = None; next_i = i + 5
                    elif i < t.n - 1:
                        pending_exit = (pos["open"], reason, i)
                    if pos is not None:
                        continue
            if pos is not None:
                reason, qty = L6.decide6(sp, t, i, pos, rule, bid, row)
                if reason is None and pos.get("fallback") and i < t.n - 1:
                    n, decided, lim2 = pos["fallback"]; pos["fallback"] = None
                    if pos["direction"] * (t.close[i] - pos["underlying_stop"]) > 0:
                        pending_add = (n, decided, lim2, "FALLBACK")
                elif reason is None and rule.scout and pos["add_lots"] and not pos.get("runner") and 2 <= i - pos["entry_i"] <= 6 \
                        and i - pos["entry_i"] < rule.hold and bid is not None and i >= 1 and L4._progress(t, i, pos):
                    pending_add = (pos["add_lots"], i, E.down(L4.ask_of(row[3]) * (1 + rule.chase)), "ADD")
                elif reason is None and rule.blind_add and pos["add_lots"] and not pos.get("runner") and i - pos["entry_i"] == 2 \
                        and bid is not None and np.isfinite(row[3]):
                    pending_add = (pos["add_lots"], i, E.down(L4.ask_of(row[3]) * (1 + rule.chase)), "BLIND")
                elif reason is None and rule.scale_in and pos["add_lots"] and not pos.get("runner") and i - pos["entry_i"] <= 3 \
                        and pos.get("_intact") and bid is not None and bid >= pos["first"] * 1.2 and np.isfinite(row[3]):
                    pending_add = (pos["add_lots"], i, E.down(E.up(float(row[3]) + E.half(float(row[3]))) * (1 + rule.chase)), "ADD")
                if reason:
                    pos["fallback"] = None
                if reason and i < t.n - 1:
                    pending_exit = (qty, reason, i)
                continue
        if closed is not None and rule.reverse:
            watch = L4._arm_watch(t, rule, closed, i, len(positions))
        if pending_exit or pending_entry or i >= t.n - 1 or len(positions) >= cap_parents:
            continue
        if rule.max_intents and intents >= rule.max_intents:
            continue
        sign, meta, normal = 0, {}, False
        if watch:
            sign, meta, watch = L4._watch(t, rule, watch, i)
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
        if rule.room_mode == "loss":
            day_left = budget - max(0., -sum(p["net"] for p in positions))
        else:
            day_left = budget - spent
        room = min(E.BUDGET / rule.slots * mult * k, day_left, cash)
        if rule.parent_cap:
            room = min(room, rule.parent_cap)
        if room <= 0:
            continue
        cap = int(round(rule.max_lots * mult * k))
        if rule.atm_itm:
            pick = L4.choose_atm(sp, t, i, sign, room, rule.chase)
        else:
            pick = L4.choose4(sp, t, i, sign, replace(rule, max_lots=cap) if cap != rule.max_lots else rule, room, cash)
        if pick:
            j, lots, limit = pick
            if meta.get("max_lots"):
                lots = min(lots, meta["max_lots"])
            if (rule.scale_in or rule.scout or rule.blind_add) and lots >= 2:
                first = math.ceil(lots / 2); meta.update(add=lots - first, planned=lots); lots = first
            if rule.passive or rule.patient:
                qc = float(t.q[i, j, 3]); meta["passive"] = E.down(qc - E.half(qc)); meta["ask0"] = L4.ask_of(qc)
                if meta["passive"] <= 0:
                    continue
            origin = meta.pop("origin", None) or ("E032" if not rule.setup3 else rule.setup3)
            if rule.setup3 in L6.SETUPS6:
                meta["xspec"] = L6.XSPEC.get((und(t), t.day, int(i), rule.setup3))
            pending_entry = (j, lots, limit, i, sign, t.features[rule.look][i, 4], room, origin, meta); intents += 1
            due = i + 1 + rule.entry_delay
            if LOG_INTENTS is not None:
                LOG_INTENTS.append(dict(day=t.day, i=int(i), d=int(sign), j=int(j), lots=int(lots), limit=float(limit), room=float(room),
                                        ask0=float(L4.ask_of(t.q[i, j, 3])), passive=meta.get("passive"), planned=int(meta.get("planned", lots))))
            if normal:
                watch = None
    unresolved = 0
    if pos:
        unresolved = 1
        pos["net"] = round(pos["net"] - pos["entry"] * pos["open"] * LOT, 2); pos["unresolved"] = True; positions.append(pos)
    if PERT7["extra_fee"]:
        for p in positions:
            p["net"] = round(p["net"] - PERT7["extra_fee"], 2); p["fees"] = round(p["fees"] + PERT7["extra_fee"], 2)
    net = round(sum(p["net"] for p in positions), 2)
    if rule.room_mode == "loss":
        assert net >= -budget - .03 - PERT7["extra_fee"] * len(positions), (t.day, net, budget)
    else:
        assert spent <= budget + .02 and net >= -spent - .03 - PERT7["extra_fee"] * len(positions), (t.day, spent, budget, net)
    mw = L6.marked_worst(sp, t, positions)
    tim = sum(max(0, int(p.get("exit_i", t.n)) - int(p["entry_i"])) for p in positions)
    return dict(day=t.day, net=net, trades=len(positions), spent=round(spent, 2),
                fees=round(sum(p["fees"] for p in positions), 2), unresolved=unresolved, rejected=rejected,
                positions=positions if details else [], marked_worst=mw, calm=False, missed=missed if details else [], intents=intents,
                minutes_in=tim)


# ---------------------------------------------------------------- arms (PLAN7.md)
ARMS = {
    "E032_30k": E032, "EN55": EN55, "E03_env": E03_ENV, "EN55_env": R7(EN55, **ENV7),
    # EN72: the scout, marketable
    "EN72": R7(E032, scout=True, **ENV7), "EN72_blind_ctl": R7(E032, blind_add=True, **ENV7),
    "EN72_e8_diag": R7(E032, scout=True, efficiency=.8, **ENV7),
    # EN73: ridge on all-session futures
    "EN73": R7(E032, setup3="RIDGE73", **ENV7), "EN73_zero_ctl": R7(E032, setup3="RIDGE73_ZERO", **ENV7),
    "EN73_icpt_ctl": R7(E032, setup3="RIDGE73_ICPT", **ENV7), "EN73_exp_ctl": R7(E032, setup3="RIDGE73_EXP", **ENV7),
    "EN73_ivs_diag": R7(E032, setup3="RIDGE73_IVS", **ENV7),
    # EN75: synthetic forward (bar level)
    "EN75": R7(E032, setup3="SYNF75", **ENV7), "EN75_fut_ctl": R7(E032, setup3="SYNF75_FUT", **ENV7),
    "EN75_lag_ctl": R7(E032, setup3="SYNF75_LAG", **ENV7), "EN75_one_ctl": R7(E032, setup3="SYNF75_ONE", **ENV7),
    # EN76: the pinned N11 signal
    "EN76": R7(E032, setup3="N11_76", **ENV7),
    # EN78: basis repair (bar level)
    "EN78": R7(E032, setup3="BASIS78", **ENV7), "EN78_fut_ctl": R7(E032, setup3="BASIS78_FUT", **ENV7),
    "EN78_mr_ctl": R7(E032, setup3="BASIS78_MR", **ENV7), "EN78_mom_ctl": R7(E032, setup3="BASIS78_MOM", **ENV7),
    # EN81: one bar later
    "EN81": R7(E032, entry_delay=1, **ENV7), "EN81_d2_diag": R7(E032, entry_delay=2, **ENV7), "EN81_d3_diag": R7(E032, entry_delay=3, **ENV7),
    "EN81_native": R7(E032, entry_delay=1),
    # EN82: N11's regime gate on E03
    "EN82": R7(E032, gate="ADX30", **ENV7), "EN82_adx25_diag": R7(E032, gate="ADX25", **ENV7), "EN82_inv_ctl": R7(E032, gate="ADX30_INV", **ENV7),
    # EN83: option writers' OI flow (NIFTY)
    "EN83": R7(E032, setup3="OI83", **ENV7), "EN83_px_ctl": R7(E032, setup3="OI83_PX", **ENV7), "EN83_inv_diag": R7(E032, setup3="OI83_INV", **ENV7),
    # EN84: participation gate
    "EN84": R7(E032, gate="RVOL", **ENV7), "EN84_inv_ctl": R7(E032, gate="RVOL_INV", **ENV7),
}
PRIMARY = {"EN72": "EN72", "EN73": "EN73", "EN75": "EN75", "EN76": "EN76", "EN78": "EN78", "EN81": "EN81", "EN82": "EN82", "EN83": "EN83", "EN84": "EN84"}
NULLS = {"EN73": "EN73", "EN75": "EN75", "EN76": "EN76", "EN78": "EN78", "EN83": "EN83"}     # random-side nulls (40 seeds)


def budget_of(arm):
    return L6.budget_of(arm)


def day7(t, arm, scenario, cash, budget, details):
    if isinstance(arm, Rule):
        return run_day7(t, arm, scenario, cash, budget, details)
    return L6.day6(t, arm, scenario, cash, budget, details)


def run_fixed7(book, arm, scenario="ordinary", details=False, cash=30000.):
    days = [day7(t, arm, scenario, cash, budget_of(arm), details) for t in book]
    return dict(days=days, summary=E.summary(days))


def run_wallet7(book, arm, scenario="ordinary", start=30000., retain=.5, details=False, pre=None):
    """A copy of L6.run_wallet6 calling day7: Rs 30,000, brakes 1,500 / 3,000 / 4,000 on the trading high-water, sweep
    max(0, retain x max(P, 0) - W), liquidation drawdown from the marked worst."""
    P = W = peakP = 0.; days = []; full = budget_of(arm); liq = 0.
    for t in book:
        cash = start + P - W; dd = peakP - P
        scale = 0. if dd >= 4000 else .25 if dd >= 3000 else .5 if dd >= 1500 else 1.
        row = dict(pre[(und(t), t.day, scale)]) if pre is not None else day7(t, arm, scenario, cash, min(full * scale, cash), details)
        liq = max(liq, peakP - (P + min(0., row.get("marked_worst", 0.))))
        P = round(P + row["net"], 2); peakP = max(peakP, P)
        sweep = round(max(0., retain * max(P, 0.) - W), 2) if retain else 0.
        W = round(W + sweep, 2)
        assert abs((start + P - W) + W - (start + P)) < 1e-6 and start + P - W >= -.01
        row.update(scale=scale, P=P, W=W, cash_after=round(start + P - W, 2), sweep=sweep); days.append(row)
    hw = 0.; cdd = 0.
    for d in days:
        hw = max(hw, d["P"]); cdd = max(cdd, hw - d["P"])
    return dict(days=days, summary=E.summary(days), P=P, swept=W, wallet=round(start + P - W, 2), halted=sum(d["scale"] == 0. for d in days),
                first_halt=next((d["day"] for d in days if d["scale"] == 0.), None), liq_dd=round(liq, 2), close_dd=round(cdd, 2))

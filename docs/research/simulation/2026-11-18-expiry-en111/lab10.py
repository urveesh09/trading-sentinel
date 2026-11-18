"""Round-10 policy hooks (IMPL10.md section 2). run_day10 is a checked copy of lab9.run_day9: with every round-10 field at
its default and no per-event profile it reproduces run_day9 on every round-9 configuration (test10 parity). No prior file
is edited.

New Rule10 fields (all off by default):
  mg10 / mgp10   management hook: EN113 fast OI, EN114 activity clock, HOLDALL fixed clock incl. runner, VOLRATIO,
                 EN116 state-conditional minute-8 continuation, EN117 range exits, EN125 OI wall
  resp10         EN115 response chooser (chooser9 = "RESP"): (window, ridge, residual_penalty, mode)
  cov10          EN117 cost-coverage gate multiple (0 = off) on the chosen contract's causal response fit
  stress10       run-level execution stress (L7.PERT7 sell_delay / extra_fee) for EN124
Per-event profiles: meta["prof10"] = ((field, value), ...) replaces Rule fields for that event's contract choice and the
whole position life (target, hold, runner, stop, hooks). The decision, room and day accounting stay the book's.
"""
from contextlib import nullcontext
from dataclasses import dataclass, asdict, replace
import math
import numpy as np
import round10  # noqa: F401
import lab8, lab9
from data8 import L7, basket as basket8
import signals9 as S9
L6, L5, L4, L3, E = L7.L6, L7.L5, L7.L4, L7.L3, L7.E
REF = S9.REF_REP


@dataclass(frozen=True)
class Rule10(lab9.Rule9):
    mg10: str = ""
    mgp10: tuple = ()
    resp10: tuple = ()
    cov10: float = 0.
    stress10: tuple = ()


def R10(rule=None, **kw):
    return replace(Rule10(**asdict(rule or L7.E03_ENV)), **kw)


_PROF = {}


def profiled(rule, prof):
    if not prof:
        return rule
    key = (rule, prof)
    r = _PROF.get(key)
    if r is None:
        r = _PROF[key] = replace(rule, **dict(prof))
        if len(_PROF) > 20000:
            _PROF.clear()
    return r


# ------------------------------------------------------------------ EN115 causal response fit
def bid_close(c):
    return E.down(float(c) - E.half(float(c)))


def response_fit(t, i, j, W, lam):
    """Ridge of 3-minute premium change on 3-minute futures change over bars (i-W, i]; x in decision-ATR units, y in
    current-premium units, unpenalised intercept. Returns (alpha, beta, mad, n) or None (unusable)."""
    P, F = t.q[:, j, 3], t.f[:, 3]; A = t.features[10][i, 4]; P0 = P[i]
    if not (np.isfinite(A) and A > 0 and np.isfinite(P0) and P0 > 0):
        return None
    k = np.arange(max(3, i - W + 4), i + 1)
    if len(k) == 0:
        return None
    ok = np.isfinite(P[k]) & np.isfinite(P[k - 3]) & np.isfinite(F[k]) & np.isfinite(F[k - 3])
    k = k[ok]
    if len(k) < 15:
        return None
    x = (F[k] - F[k - 3]) / A; y = (P[k] - P[k - 3]) / P0
    xm, ym = x.mean(), y.mean(); sxx = float(((x - xm) ** 2).sum())
    if sxx <= 1e-12:
        return None
    b = float(((x - xm) * (y - ym)).sum()) / (sxx + lam); a = float(ym - b * xm)
    e = y - a - b * x
    return a, b, float(np.median(np.abs(e - np.median(e)))), int(len(k))


def costs1(sp, t, i, j):
    cl = float(t.q[i, j, 3]); ask = L4.ask_of(cl); bid = L4.bid_of(cl)
    return (ask - bid) * sp.lot + L4.fee(sp, ask, sp.lot, True) + L4.fee(sp, bid, sp.lot, False)


def resp_pick(sp, t, i, d, r, room, cash, note=None):
    if not np.isfinite(t.close[i]):
        return None
    legacy1 = L4.choose4(sp, t, i, d, replace(r, max_lots=1), room, cash)
    if r.admit9 and legacy1 is None:
        return None
    W, lam, rp, mode = r.resp10
    cs = lab9.candidates(sp, t, i, d, r, room, cash)
    fits = []
    for c in cs:
        f = response_fit(t, i, c["j"], W, lam)
        if f is not None:
            fits.append((c, f))
    if not fits:
        if note is not None:
            note.append(("RESP_FALLBACK", int(i)))
        return legacy1
    bmed = float(np.median([f[1] for _, f in fits]))
    best = None
    for c, (a, b, mad, n) in fits:
        j = c["j"]; P0 = float(t.q[i, j, 3]); beta = bmed if mode == "CONSTBETA" else b
        score = sp.lot * P0 * (a + beta * d - rp * mad) - costs1(sp, t, i, j)
        key = (-round(score, 6), round(L4.reserve(sp, c["lim"], 1), 2), c["K"], j)
        if best is None or key < best[0]:
            best = (key, j, c["lim"])
    if mode == "EQRES":                         # control: the legacy chooser given the response pick's one-lot reserve
        R_ = L4.reserve(sp, best[2], 1)
        return L4.choose4(sp, t, i, d, replace(r, max_lots=3), R_ + .005, cash)
    return best[1], 1, best[2]


def cost_gate(sp, t, i, d, j, meta, cov, note=None):
    """EN117: the chosen contract's fixed causal fit (window 40, ridge 10) must make the scenario premium movement to the
    frozen target exceed cov x (spread + buy and sell order charges). No fit -> unavailable (never delta = 1)."""
    f = response_fit(t, i, j, 40, 10.)
    if f is None:
        if note is not None:
            note.append(("GATE_NOFIT", int(i)))
        return False
    a, b, _, _ = f; A = float(t.features[10][i, 4]); P0 = float(t.q[i, j, 3])
    dist = d * (meta["range10"][1] - float(t.f[i, 3]))
    gain = sp.lot * P0 * (a + b * d * max(dist, 0.) / A)
    ok = gain > cov * costs1(sp, t, i, j)
    if not ok and note is not None:
        note.append(("GATE_COST", int(i)))
    return ok


def choose10(sp, t, i, d, r, room, cash, meta, note):
    if "pick" in meta:
        return lab9.arm_pick(sp, t, i, r, room, cash, meta["pick"])
    if r.chooser9 == "RESP":
        pick = resp_pick(sp, t, i, d, r, room, cash, note)
    else:
        pick = lab9.choose9(sp, t, i, d, r, room, cash, meta)
    if pick and r.cov10 and not cost_gate(sp, t, i, d, pick[0], meta, r.cov10, note):
        return None
    return pick


# ------------------------------------------------------------------ management hooks
def liq_net(sp, pos, bid):
    return pos["net"] + (bid - pos["entry"]) * pos["open"] * sp.lot - L4.fee(sp, bid, pos["open"] * sp.lot, False)


def best_prev_bid(t, pos, i, n=3):
    k0 = max(pos["entry_i"], i - n)
    if i - k0 < n:
        return None
    c = t.q[k0:i, pos["j"], 3]
    if not np.isfinite(c).all():
        return None
    return max(bid_close(x) for x in c)


def fast_D(t, i, pos, L, q):
    """d*S_L < -q on the fixed entry basket (round-8 accumulation). None when an input is missing."""
    pairs = lab9.fixed_pairs(t, pos, REF)
    if not pairs or not np.isfinite(q):
        return None
    s = S9.ref_score(t, i, L, pairs)
    if not np.isfinite(s):
        return None
    return bool(pos["direction"] * s < -q)


def hook113(sp, t, i, pos, r, bid, reason, qty):
    L, qkey, mode, stale = r.mgp10
    q = t.q10.get(qkey, math.nan) if mode != "PRICE_ONLY" else math.nan
    age = i - pos["entry_i"]; st = pos.setdefault("_h113", {})
    conf = None
    if mode != "PRICE_ONLY" and i - 1 - stale >= pos["entry_i"]:
        a, b = fast_D(t, i - stale, pos, L, q), fast_D(t, i - 1 - stale, pos, L, q)
        conf = None if a is None or b is None else (a and b)
        if conf:
            st["confirmed"] = st.get("confirmed", 0) + 1
    if reason is not None:
        return reason, qty
    if not pos.get("runner") and age >= 8 and not st.get("c8"):
        st["c8"] = True
        if mode != "PRICE_ONLY" and conf is None:
            st["fallback"] = True
            return "TIME_MISSING", pos["open"]
        if mode == "DENY" and conf:
            return "OI_DENY", pos["open"]
    if mode == "DENY":
        return None, qty
    if mode in ("GIVEBACK", "PRICE_ONLY"):
        if mode == "GIVEBACK" and not conf:
            return None, qty
        best = best_prev_bid(t, pos, i)
        if bid is not None and best is not None and bid <= .9 * best + 1e-9:
            return ("OI_GIVEBACK" if mode == "GIVEBACK" else "PRICE_GIVEBACK"), pos["open"]
        return None, qty
    if mode == "OI_ONLY" and conf:
        return "OI_FAST", pos["open"]
    return None, qty


def v0_of(t, k):
    F = t.f[:, 3]
    if k < 30:
        return math.nan
    w = F[k - 30:k + 1]
    if not np.isfinite(w).all():
        return math.nan
    v = float(np.mean(np.diff(w) ** 2))
    return v if v > 0 else math.nan


def hook114(sp, t, i, pos, r, bid, reason, qty):
    budget, wall, scope = r.mgp10
    st = pos.setdefault("_h114", {})
    if "v0" not in st:
        st["v0"] = v0_of(t, pos["decision_i"])
    F = t.f[:, 3]; age = i - pos["entry_i"]
    a = math.nan
    if np.isfinite(st["v0"]):
        seg = F[pos["entry_i"] - 1:i + 1]
        if np.isfinite(seg).all():
            a = float(np.sum(np.diff(seg) ** 2)) / st["v0"]
    st["A"] = None if not np.isfinite(a) else round(a, 4)
    if reason is not None:
        return reason, qty
    if pos.get("runner") and scope != "BASE_AND_RUNNER":
        return None, qty
    if not np.isfinite(a):
        st["fallback"] = True
        return ("TIME_FALLBACK", pos["open"]) if age >= 8 else (None, qty)
    if age >= 4 and a >= budget:
        return "ACTIVITY", pos["open"]
    if age >= wall:
        return "WALL", pos["open"]
    return None, qty


def hook_holdall(sp, t, i, pos, r, bid, reason, qty):
    if reason is None and pos.get("runner") and i - pos["entry_i"] >= r.mgp10[0]:
        return "WALL", pos["open"]
    return reason, qty


def hook_volratio(sp, t, i, pos, r, bid, reason, qty):
    st = pos.setdefault("_hvr", {})
    if "h" not in st:
        v0 = v0_of(t, pos["decision_i"]); vr = getattr(t, "vref10", math.nan)
        st["h"] = int(min(16, max(4, round(8 * math.sqrt(vr / v0))))) if np.isfinite(v0) and np.isfinite(vr) and vr > 0 else 8
    if reason is None and not pos.get("runner") and i - pos["entry_i"] >= st["h"]:
        return "TIME_VR", pos["open"]
    return reason, qty


def hook116(sp, t, i, pos, r, bid, reason, qty):
    if reason is not None or pos.get("runner"):
        return reason, qty
    age = i - pos["entry_i"]
    if 8 <= age < r.hold:
        act = bool(t.state10[r.mgp10[0]][i])
        if not (act and bid is not None and liq_net(sp, pos, bid) > 0):
            return "STATE_TIME", pos["open"]
    return None, qty


def hook117(sp, t, i, pos, r, bid, reason, qty):
    if reason is not None:
        return reason, qty
    d, target, struct = pos["range10"][0], pos["range10"][1], pos["range10"][2]
    Fi = t.f[i, 3]
    if not np.isfinite(Fi):
        return None, qty
    if d * (Fi - struct) < 0:
        return "RANGE_STRUCT", pos["open"]
    if d * (Fi - target) >= 0:
        return "RANGE_TARGET", pos["open"]
    return None, qty


def wall_of(t, b, d):
    """Strike with the largest own-kind OI among the four nearest strikes strictly ahead of the index close at bar b."""
    c = t.close[b]
    if not np.isfinite(c):
        return None
    js = [j for j in range(len(t.strikes)) if t.kinds[j] == d and d * (float(t.strikes[j]) - float(c)) > 0]
    js = sorted(js, key=lambda j: d * float(t.strikes[j]))[:4]
    vals = [(float(t.oi8[b, j]), j) for j in js if np.isfinite(t.oi8[b, j])]
    if len(vals) < 2:
        return None
    best = max(vals, key=lambda v: (v[0], -abs(float(t.strikes[v[1]]) - float(c))))    # ties: the nearer strike
    return float(t.strikes[best[1]])


def hook125(sp, t, i, pos, r, bid, reason, qty):
    frozen, trigger, action = r.mgp10
    st = pos.setdefault("_h125", {})
    d = pos["direction"]; step = sp.step
    if st.get("tight"):
        pos["stop"] = max(pos["stop"], round(.8 * pos["peak"], 2))
    if reason is not None:
        return reason, qty
    if frozen == "FROZEN_AT_ENTRY":
        if "W" not in st:
            st["W"] = wall_of(t, pos["entry_i"], d)
        W = st["W"]
    else:
        W = wall_of(t, i - 1, d) if i - 1 >= pos["entry_i"] else None
    if W is None or not np.isfinite(t.close[i]):
        st["missing"] = st.get("missing", 0) + 1
        return None, qty
    off = .5 * step if trigger == "HALF_STEP_BEFORE" else 0.
    if d * (float(t.close[i]) - W) >= -off - 1e-9:
        st["reached"] = st.get("reached", 0) + 1
        if action == "EXIT_ALL":
            return "OI_WALL", pos["open"]
        if not st.get("tight"):
            st["tight"] = True; pos["stop"] = max(pos["stop"], round(.8 * pos["peak"], 2))
    return None, qty


HOOKS = dict(EN113=hook113, EN114=hook114, HOLDALL=hook_holdall, VOLRATIO=hook_volratio, EN116=hook116, EN117=hook117,
             EN125=hook125)


def decide10(sp, t, i, pos, r, bid, row):
    reason, qty = lab9.decide9(sp, t, i, pos, r, bid, row)
    if r.mg10:
        reason, qty = HOOKS[r.mg10](sp, t, i, pos, r, bid, reason, qty)
    return reason, qty


# ------------------------------------------------------------------ the day loop (copy of run_day9 + hooks)
def run_day10(t, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False, direct=None):
    with (L7.stress(**dict(rule.stress10)) if rule.stress10 else nullcontext()):
        return _run_day10(t, rule, scenario, cash, budget, details, direct)


def _run_day10(t, rule, scenario, cash, budget, details, direct):
    sp = L4.spec_of(t); LOT = sp.lot; k = rule.size_k
    assert rule.setup3 not in ("PAIR", "PIN", "LASTHALF") and not rule.bank_r and not rule.regime_min and not rule.squeeze
    assert not (rule.core_bank or rule.core_child or rule.ladder or rule.liq_pick), "round-6 EN63/EN65/ladder hooks: use run_day6"
    dirs, sdist, tdist = lab9.signals9(t, rule) if direct is None else (direct.copy(), None, None)
    dirs = L7.gated(t, rule, dirs)
    meta9 = t.meta9.get(rule.sig9, {}) if rule.sig9 else {}
    spent = 0.0; positions = []; next_i = 0; pending_entry = None; pending_exit = None; pending_add = None; pos = None
    rejected = 0; missed = []; stopped = None; watch = None; intents = 0; due = -1; adds9 = 0; notes = []
    cap_parents = rule.max_parents or rule.slots
    for i in range(int(np.searchsorted(t.minute, rule.start)), t.n):
        closed = None
        if pending_exit:
            qty, reason, decided = pending_exit
            pr = pos.get("r10", rule)
            filled, px = L7._exe7(sp, t, i, pos["j"], "SELL", scenario, min(qty, pos["open"]))
            if filled:
                L4._sell(sp, pos, i, decided, reason, filled, px)
                if reason in ("TARGET_BASE", "PUT_RUNNER"):
                    pos["runner"] = True
                    pos["stop"] = max(round(pos["entry"] * pr.runner_floor, 2), round(pos["peak"] * pr.runner_keep, 2))
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
            pr = pos.get("r10", rule)
            n, decided, lim, why = pending_add; pending_add = None
            if why in ("ADD", "BLIND"):
                pos["add_lots"] = 0
            filled, px = L7._exe7(sp, t, i, pos["j"], "BUY", scenario, n)
            if filled and px is not None and px <= lim:
                left = pos["room"] - pos["reserve"]
                if why == "STAGE_ADD":
                    left = min(left, cash - pos["reserve"])
                while filled and L4.reserve(sp, px, filled) > left + .01:
                    filled -= 1
                if filled and why == "STAGE_ADD":
                    spent += lab9.buy_more9(sp, pos, i, decided, filled, px, why)
                elif filled:
                    spent += L4._buy_more(sp, pos, i, decided, filled, px, "ADD" if why == "BLIND" else why,
                                          "max" if (pr.scout or pr.blind_add or why == "FALLBACK") and not pr.no_pstop else "none" if pr.no_pstop else "reset")
            elif why == "STAGE_ADD":
                pos["stage_unfilled"] = pos.get("stage_unfilled", 0) + 1
        if pending_entry and i < due:
            continue
        if pending_entry:
            j, lots, limit, decision, sign, a_, room, origin, meta = pending_entry
            er = meta.get("_r10", rule)
            share = .2
            if er.passive:
                r = t.q[i, j]; P = meta["passive"]; thr = P - (.05 if scenario == "ordinary" else .10)
                cap = int(r[4] * .2) // LOT if np.isfinite(r).all() else 0
                if cap > 0 and r[2] <= thr + 1e-9:
                    filled, px = min(lots, cap), P; pending_entry = None
                elif i - decision < 2:
                    continue
                else:
                    pending_entry = None; missed.append(dict(day=t.day, decision_i=decision, direction=sign, j=j)); continue
            elif er.patient and meta.get("stage") != "fallback":
                r = t.q[i, j]; P = meta["passive"]; pending_entry = None
                if er.patient == "cons":
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
                    us = L4._us(t, er, decision, sign, a_, meta)
                    if ok_fb and sign * (t.close[i] - us) > 0 and t.minute[i] < er.end + 1 and i < t.n - 1:
                        meta = dict(meta, stage="fallback"); pending_entry = (j, lots, lim2, decision, sign, a_, room, origin, meta)
                    else:
                        missed.append(dict(day=t.day, decision_i=decision, direction=sign, j=j))
                    continue
                if rest and ok_fb:
                    meta = dict(meta, fb=(rest, lim2))
            else:
                pending_entry = None
                filled, px = L7._exe7(sp, t, i, j, "BUY", scenario, lots)
            if filled < max(1, math.ceil(lots * .25)) or px is None or px > limit:
                if not (er.patient and filled and px is not None and px <= limit):
                    rejected += 1; continue
            risk = L4.reserve(sp, px, filled); assert risk <= room + .01
            spent += risk
            pos = L4._open(sp, t, i, er, j, filled, px, decision, sign, a_, room, origin, meta); pos["rule_stop"] = er.stop; pos["policy8"] = er.setup8
            pos["reserve0"] = pos["reserve"]
            if er is not rule:
                pos["r10"] = er
            if meta.get("fb"):
                pos["fallback"] = (meta["fb"][0], decision, meta["fb"][1])
            if meta.get("xspec"):
                pos["xspec"] = dict(meta["xspec"])
            if "add9" in meta:
                pos["add9"] = meta["add9"]; pos["planned9"] = meta["planned9"]
            for key in ("z", "event_i"):
                if key in meta:
                    pos[key + "9"] = meta[key]
            for key in ("range10", "tag10"):
                if key in meta:
                    pos[key] = meta[key]
            if er.stage9 > 0 and er.oiadd9 == "AT_LEAST_ENTRY_STRENGTH":
                s0 = lab9.fixed_score(t, i, pos, er)
                pos["_strength9"] = float(sign * s0) if np.isfinite(s0) else None
        if pos:
            pr = pos.get("r10", rule)
            row = t.q[i, pos["j"]]
            bid = E.down(float(row[3]) - E.half(float(row[3]))) if np.isfinite(row[3]) and np.isfinite(row[4]) and row[4] * .2 >= LOT else None
            if pr.fast_exit and not pos.get("runner") and t.minute[i] < pr.flat:
                fx = L4._fast(sp, t, i, pos, pr, scenario)
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
                reason, qty = decide10(sp, t, i, pos, pr, bid, row)
                if reason is None and pos.get("fallback") and i < t.n - 1:
                    n, decided, lim2 = pos["fallback"]; pos["fallback"] = None
                    if pos["direction"] * (t.close[i] - pos["underlying_stop"]) > 0:
                        pending_add = (n, decided, lim2, "FALLBACK")
                elif reason is None and pr.scout and pos["add_lots"] and not pos.get("runner") and 2 <= i - pos["entry_i"] <= 6 \
                        and i - pos["entry_i"] < pr.hold and bid is not None and i >= 1 and L4._progress(t, i, pos):
                    pending_add = (pos["add_lots"], i, E.down(L4.ask_of(row[3]) * (1 + pr.chase)), "ADD")
                elif reason is None and pr.blind_add and pos["add_lots"] and not pos.get("runner") and i - pos["entry_i"] == 2 \
                        and bid is not None and np.isfinite(row[3]):
                    pending_add = (pos["add_lots"], i, E.down(L4.ask_of(row[3]) * (1 + pr.chase)), "BLIND")
                elif reason is None and pr.scale_in and pos["add_lots"] and not pos.get("runner") and i - pos["entry_i"] <= 3 \
                        and pos.get("_intact") and bid is not None and bid >= pos["first"] * 1.2 and np.isfinite(row[3]):
                    pending_add = (pos["add_lots"], i, E.down(E.up(float(row[3]) + E.half(float(row[3]))) * (1 + pr.chase)), "ADD")
                elif reason is None and pr.stage9 > 0 and pos.get("add9") and pos["add9"][0] > 0 and not pos.get("runner") \
                        and t.minute[i] < 870 and i < t.n - 1 and np.isfinite(row).all() \
                        and (not rule.max_intents or intents < rule.max_intents) and lab9.stage_trigger(t, i, pos, pr, bid):
                    n2, ask0, addp = pos["add9"]
                    ask = L4.ask_of(row[3]); lim = E.down(min(ask * (1 + pr.chase), addp))
                    if lim >= ask:
                        pos["add9"] = (0, ask0, addp); intents += 1; adds9 += 1
                        pending_add = (n2, i, lim, "STAGE_ADD")
                    else:
                        pos["stage_over_cap"] = pos.get("stage_over_cap", 0) + 1
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
            if i in meta9:
                meta.update(meta9[i])
        er = profiled(rule, meta.get("prof10"))
        mult = rule.put_mult if sign < 0 else rule.call_mult
        if rule.room_mode == "loss":
            day_left = budget - sum(max(0., -p["net"]) for p in positions)
        else:
            day_left = budget - spent
        room = min(E.BUDGET / rule.slots * mult * k, day_left, cash)
        if rule.parent_cap:
            room = min(room, rule.parent_cap)
        if room <= 0:
            continue
        cap = int(round(er.max_lots * mult * k))
        if er.atm_itm:
            pick = L4.choose_atm(sp, t, i, sign, room, er.chase)
        else:
            pick = choose10(sp, t, i, sign, replace(er, max_lots=cap) if cap != er.max_lots else er, room, cash, meta, notes)
        if pick:
            j, lots, limit = pick
            if meta.get("max_lots"):
                lots = min(lots, meta["max_lots"])
            if (er.scale_in or er.scout or er.blind_add) and lots >= 2:
                first = math.ceil(lots / 2); meta.update(add=lots - first, planned=lots); lots = first
            if er.stage9:
                N, n1, n2, ask0 = lab9.staged_plan(sp, t, i, j, lots, limit, er, room, cash)
                lots = n1; meta["planned9"] = N
                meta["add9"] = (n2, ask0, E.down(lab9.ADD_PRICE * ask0))
            if er.passive or er.patient:
                qc = float(t.q[i, j, 3]); meta["passive"] = E.down(qc - E.half(qc)); meta["ask0"] = L4.ask_of(qc)
                if meta["passive"] <= 0:
                    continue
            origin = meta.pop("origin", None) or ("E032" if not er.setup3 else er.setup3)
            if er.setup3 in L6.SETUPS6:
                meta["xspec"] = L6.XSPEC.get((L7.und(t), t.day, int(i), er.setup3))
            meta = {key: v for key, v in meta.items() if key != "pick"} | ({"event_i": meta["pick"]["event_i"]} if "pick" in meta else {})
            if er is not rule:
                meta["_r10"] = er
            pending_entry = (j, lots, limit, i, sign, t.features[er.look][i, 4], room, origin, meta); intents += 1
            due = i + 1 + er.entry_delay
            if lab8.LOG_INTENTS is not None:
                lab8.LOG_INTENTS.append(dict(day=t.day, i=int(i), d=int(sign), j=int(j), lots=int(lots), limit=float(limit), room=float(room),
                                             ask0=float(L4.ask_of(t.q[i, j, 3])), passive=meta.get("passive"), planned=int(meta.get("planned", lots))))
            if normal:
                watch = None
    unresolved = 0
    if pos:
        unresolved = 1
        pos["net"] = round(pos["net"] - pos["entry"] * pos["open"] * LOT, 2); pos["unresolved"] = True; positions.append(pos)
    if L7.PERT7["extra_fee"]:
        for p in positions:
            p["net"] = round(p["net"] - L7.PERT7["extra_fee"], 2); p["fees"] = round(p["fees"] + L7.PERT7["extra_fee"], 2)
    net = round(sum(p["net"] for p in positions), 2)
    if rule.room_mode == "loss":
        assert net >= -budget - .03 - L7.PERT7["extra_fee"] * len(positions), (t.day, net, budget)
    else:
        assert spent <= budget + .02 and net >= -spent - .03 - L7.PERT7["extra_fee"] * len(positions), (t.day, spent, budget, net)
    for p in positions:
        assert p["reserve"] <= p["room"] + .02, (t.day, p["reserve"], p["room"])
    mw = L6.marked_worst(sp, t, positions)
    tim = sum(max(0, int(p.get("exit_i", t.n)) - int(p["entry_i"])) for p in positions)
    return dict(day=t.day, net=net, trades=len(positions), spent=round(spent, 2),
                fees=round(sum(p["fees"] for p in positions), 2), unresolved=unresolved, rejected=rejected,
                positions=positions if details else [], marked_worst=mw, calm=False, missed=missed if details else [], intents=intents,
                minutes_in=tim, adds9=adds9, notes=len(notes), notes_detail=notes if details else [])


# ------------------------------------------------------------------ wallets (lab9 semantics, round-10 day loop)
def wallet_steps(pairs, scenario="ordinary", start=30000., retain=.5):
    P = W = peak = liq = 0.; rows = []
    for t, r in pairs:
        cash = start + P - W; dd = peak - P; scale = lab9.scale_of(dd)
        row = run_day10(t, r, scenario, cash, min(L7.budget_of(r) * scale, cash), False)
        liq = max(liq, peak - (P + min(0., row["marked_worst"])))
        P = round(P + row["net"], 2); peak = max(peak, P)
        W = round(W + max(0., round(retain * max(P, 0.) - W, 2)), 2)
        assert cash >= 0 and start + P - W >= -.01
        rows.append(dict(day=row["day"], net=row["net"], trades=row["trades"], P=P, W=W, scale=scale, cash_after=round(start + P - W, 2)))
    return dict(P=P, swept=W, wallet=round(start + P - W, 2), combined=round(start + P, 2), liq_dd=round(liq, 2),
                halted=sum(x["scale"] == 0 for x in rows), first_halt=next((x["day"] for x in rows if x["scale"] == 0), None), days=rows)


def wallet10(book, r, scenario="ordinary", start=30000., retain=.5):
    return wallet_steps([(t, r) for t in book], scenario, start, retain)

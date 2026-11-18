"""Round-9 policy hooks. run_day9 is a checked copy of lab8.run_day8: with every round-9 field at its default it
reproduces run_day8 on every round-8 arm, session and fill level (test9 parity). No prior file is edited.

New Rule9 fields (all off by default):
  sig9      key of a precomputed direction array t.sig9[key]; per-minute meta in t.meta9[key][i]
            ('pick' = frozen arm contract/ceiling, 'max_lots' = information cap)
  chooser9  EN100/EN105 contract rule LEGACY / NEAREST / MINFRIC; fric9 = friction/reserve cap (0 = none);
            admit9 = the legacy one-lot chooser must be able to fund an entry first
  rep9/qkey9  representation and day-threshold key used by information management (fixed entry basket)
  ext9 / extcap9 / extact9 / rndext9   EN101 conditional continuation (absolute cap from the actual fill)
  dmg9 / dmgk9 / dmgn9                 EN102 confirmed damage exit (dmgk9 < 0: no OI requirement)
  stage9 / gain9 / oiadd9              EN103 staged entry (stage9 < 0: conservative full-entry control)
"""
from dataclasses import dataclass, asdict, replace
import hashlib, math
import numpy as np
import round8  # noqa: F401
import lab8
from data8 import L7, basket
import signals9 as S9
L6, L5, L4, L3, E, D4 = L7.L6, L7.L5, L7.L4, L7.L3, L7.E, L7.D4
und = L7.und
ADD_PRICE = 1.40


@dataclass(frozen=True)
class Rule9(lab8.Rule8):
    sig9: str = ""
    chooser9: str = ""
    fric9: float = 0.
    admit9: bool = False
    rep9: tuple = ()
    qkey9: str = ""
    ext9: str = ""
    extcap9: int = 0
    extact9: float = 0.
    rndext9: float = -1.
    seed9: int = 0
    dmg9: str = ""
    dmgk9: float = -1.
    dmgn9: int = 0
    stage9: float = 0.
    gain9: float = 0.
    oiadd9: str = ""


def R9(rule=None, **kw):
    return replace(Rule9(**asdict(rule or L7.E03_ENV)), **kw)


# ------------------------------------------------------------------ signals and contracts
def signals9(t, r):
    if not r.sig9:
        return lab8.signals8(t, r)
    a = t.sig9[r.sig9].copy()
    a[(t.minute < r.start) | (t.minute >= r.end)] = 0
    for i in np.flatnonzero(a):
        if not np.isfinite(t.close[i]) or not L4._avail(t, int(i), int(a[i])):
            a[i] = 0
    return a, None, None


def arm_pick(sp, t, i, r, room, cash, p):
    j, ask0 = p["j"], p["ask0"]; row = t.q[i, j]
    if not np.isfinite(row).all():
        return None
    ask = L4.ask_of(row[3]); limit = E.down(min(ask * (1 + r.chase), ask0 * p["ceil"]))
    cap = min(r.max_lots, int(row[4] * .2) // sp.lot)
    while cap and L4.reserve(sp, limit, cap) > min(room, cash) + .01:
        cap -= 1
    return (j, cap, limit) if cap and limit >= ask else None


def friction(sp, t, i, j, lim):
    cl = float(t.q[i, j, 3]); ask = L4.ask_of(cl); bid = L4.bid_of(cl)
    return ((ask - bid) * sp.lot + L4.fee(sp, ask, sp.lot, True) + L4.fee(sp, bid, sp.lot, False)) / L4.reserve(sp, lim, 1)


def candidates(sp, t, i, d, r, room, cash):
    """Every one-lot affordable contract of the signal's kind at the current clock (full premium and charges fit)."""
    out = []; c = float(t.close[i]); rm = min(room, cash)
    for j in range(len(t.strikes)):
        if t.kinds[j] != d or not np.isfinite(t.q[i, j]).all():
            continue
        cl = float(t.q[i, j, 3]); ask = L4.ask_of(cl); bid = L4.bid_of(cl)
        if bid <= 0 or int(t.q[i, j, 4] * .2) // sp.lot < 1:
            continue
        lim = E.down(min(ask * (1 + r.chase), (rm - 2 * sp.order) / (sp.lot * (1 + sp.buy_rate))))
        if lim < ask or L4.reserve(sp, lim, 1) > rm + .01:
            continue
        out.append(dict(j=j, lim=lim, fric=friction(sp, t, i, j, lim), dist=abs(float(t.strikes[j]) - c), K=float(t.strikes[j])))
    return out


def size_for(sp, t, i, j, r, room, cash):
    """choose4's sizing loop for a given contract: most whole lots (<= max_lots, 10, 20% bar volume) whose reserve fits."""
    row = t.q[i, j]; ask = L4.ask_of(row[3]); rm = min(room, cash)
    for lots in range(min(r.max_lots, 10, int(row[4] * .2) // sp.lot), 0, -1):
        limit = E.down(min(ask * 1.1, (rm - sp.order - lots * sp.order) / (lots * sp.lot * (1 + sp.buy_rate))))
        if limit >= ask and L4.reserve(sp, limit, lots) <= rm + .01:
            limit = min(limit, E.down(ask * (1 + r.chase)))
            return (j, lots, limit) if limit >= ask else None
    return None


def contract_pick(sp, t, i, d, r, room, cash):
    if not np.isfinite(t.close[i]):
        return None
    legacy1 = L4.choose4(sp, t, i, d, replace(r, max_lots=1), room, cash)
    if r.admit9 and legacy1 is None:
        return None
    if r.chooser9 == "LEGACY":
        pick = legacy1 if r.max_lots == 1 else L4.choose4(sp, t, i, d, r, room, cash)
        if pick is None or legacy1 is None:
            return None
        if r.fric9 and friction(sp, t, i, legacy1[0], legacy1[2]) > r.fric9 + 1e-12:
            return None
        return pick
    cs = [c for c in candidates(sp, t, i, d, r, room, cash) if not r.fric9 or c["fric"] <= r.fric9 + 1e-12]
    if not cs:
        return None
    key = (lambda c: (c["dist"], c["K"], c["j"])) if r.chooser9 == "NEAREST" else (lambda c: (c["fric"], c["dist"], c["K"], c["j"]))
    c = min(cs, key=key)
    if r.max_lots == 1:
        return (c["j"], 1, c["lim"])
    return size_for(sp, t, i, c["j"], r, room, cash)


def choose9(sp, t, i, d, r, room, cash, meta):
    if "pick" in meta:
        return arm_pick(sp, t, i, r, room, cash, meta["pick"])
    if r.chooser9:
        return contract_pick(sp, t, i, d, r, room, cash)
    return lab8.choose8(sp, t, i, d, r, room, cash)


def staged_plan(sp, t, i, j, lots, limit, r, room, cash):
    """EN103: planned lots N so that first tranche + an add at 1.40x the decision ask (with its own charges) fit."""
    ask0 = L4.ask_of(t.q[i, j, 3]); addp = E.down(ADD_PRICE * ask0); rm = min(room, cash)
    frac = .5 if r.stage9 < 0 else r.stage9
    for n in range(lots, 0, -1):
        n1 = max(1, math.floor(n * frac + 1e-9)); n2 = n - n1
        if L4.reserve(sp, limit, n1) + (L4.reserve(sp, addp, n2) if n2 else 0.) <= rm + .01:
            return (n, n, 0, ask0) if r.stage9 < 0 else (n, n1, n2, ask0)
    return (1, 1, 0, ask0)


# ------------------------------------------------------------------ information management
def fixed_pairs(t, pos, rep):
    if "_pairs9" not in pos:
        k = pos["entry_i"]
        if not rep or rep[1:] == S9.REF_REP[1:]:
            pos["_pairs9"] = basket(t, k)
        else:
            pos["_pairs9"] = S9.strict_pairs(t, S9.anchor_of(t, k, rep[2]), rep[1])
    return pos["_pairs9"]


def fixed_score(t, i, pos, r):
    rep = r.rep9 or S9.REF_REP; pairs = fixed_pairs(t, pos, rep)
    if pairs is None:
        return math.nan
    return S9.rep_score(t, i, rep, pairs)


def q_entry(t, r):
    return t.q9.get(r.qkey9 or "REF", math.nan)


def price_ok(t, i, d):
    F, FH, FL = t.f[:, 3], t.f[:, 1], t.f[:, 2]
    if i < 3 or not np.isfinite([F[i], F[i - 3]]).all() or not np.isfinite(FL[i - 3:i]).all() or not np.isfinite(FH[i - 3:i]).all():
        return None
    hold = F[i] >= np.min(FL[i - 3:i]) if d > 0 else F[i] <= np.max(FH[i - 3:i])
    return bool(d * (F[i] - F[i - 3]) > 0 and hold)


def info_ok(t, i, pos, r, mult=.5):
    s = fixed_score(t, i, pos, r); q = q_entry(t, r)
    if not (np.isfinite(s) and np.isfinite(q)):
        return None
    return bool(pos["direction"] * s > mult * q)


def permission(t, i, pos, r):
    d = pos["direction"]
    if r.ext9 == "INFORMATION":
        return info_ok(t, i, pos, r)
    if r.ext9 == "PRICE":
        return price_ok(t, i, d)
    a, b = info_ok(t, i, pos, r), price_ok(t, i, d)
    return None if a is None or b is None else (a and b)


def coin(r, t, pos):
    h = hashlib.sha256(f"{r.seed9}|{t.day}|{pos['entry_i']}|{pos['direction']}".encode()).digest()
    return int.from_bytes(h[:8], "big") / 2 ** 64


def extension9(sp, t, i, pos, r, bid, reason, qty):
    if pos.get("runner"):
        return reason, qty                                  # the native runner keeps its own rules (no time cap)
    st = pos.get("_ext9")
    if isinstance(st, dict):
        if i - pos["entry_i"] >= r.extcap9:
            return ("TIME_CAP", pos["open"]) if reason is None or reason == "TIME" else (reason, qty)
        if reason not in (None, "TIME"):
            return reason, qty                              # native protective/target exits keep priority
        if st.get("random"):
            return None, qty
        ok = permission(t, i, pos, r) if bid is not None else None
        if ok is None:
            st["missing"] = st.get("missing", 0) + 1
            return "EXT_MISSING", pos["open"]
        st["fails"] = 0 if ok else st["fails"] + 1
        st["checks"] = st.get("checks", 0) + 1
        return ("EXT_FAIL", pos["open"]) if st["fails"] >= 2 else (None, qty)
    if reason != "TIME" or st is False:
        return reason, qty
    if r.rndext9 >= 0:
        go = coin(r, t, pos) < r.rndext9
        pos["_ext9"] = dict(fails=0, random=True, start=i) if go else False
        return (None, qty) if go else (reason, qty)
    liq = pos["net"] + (bid - pos["entry"]) * pos["open"] * sp.lot - L4.fee(sp, bid, pos["open"] * sp.lot, False)
    ok = permission(t, i, pos, r)
    if liq > r.extact9 * pos["reserve0"] and ok:
        pos["_ext9"] = dict(fails=0, start=i, liq=round(liq, 2)); return None, qty
    pos["_ext9"] = False
    return reason, qty


def damage9(sp, t, i, pos, r):
    d = pos["direction"]; F, FH, FL = t.f[:, 3], t.f[:, 1], t.f[:, 2]
    oi = True
    if r.dmgk9 >= 0:
        s = fixed_score(t, i, pos, r); q = q_entry(t, r)
        if not (np.isfinite(s) and np.isfinite(q)):
            pos["_dmg9"] = (i, 0); return None
        oi = d * s < -r.dmgk9 * q
    if r.dmg9 == "ENTRY":
        if not np.isfinite([F[i], pos["dec_fut"], pos["dec_atr"]]).all():
            pos["_dmg9"] = (i, 0); return None
        dmg = d * (F[i] - pos["dec_fut"]) < -.25 * pos["dec_atr"]
    elif r.dmg9 == "STRUCTURE":
        if i < 3 or not np.isfinite(F[i]) or not np.isfinite(FL[i - 3:i]).all() or not np.isfinite(FH[i - 3:i]).all():
            pos["_dmg9"] = (i, 0); return None
        dmg = F[i] < np.min(FL[i - 3:i]) if d > 0 else F[i] > np.max(FH[i - 3:i])
    else:
        dmg = True
    last, n = pos.get("_dmg9", (-9, 0))
    n = (n + 1 if last == i - 1 else 1) if (oi and dmg) else 0
    pos["_dmg9"] = (i, n)
    return "DAMAGE9" if n >= r.dmgn9 else None


def decide9(sp, t, i, pos, r, bid, row):
    reason, qty = lab8.decide8(sp, t, i, pos, r, bid, row)
    if r.ext9 or r.rndext9 >= 0:
        reason, qty = extension9(sp, t, i, pos, r, bid, reason, qty)
    if reason is None and r.dmg9:
        x = damage9(sp, t, i, pos, r)
        if x:
            reason, qty = x, pos["open"]
    return reason, qty


def stage_trigger(t, i, pos, r, bid):
    if bid is None or bid < pos["first"] * (1 + r.gain9) - 1e-9:
        return False
    s = fixed_score(t, i, pos, r); q = q_entry(t, r)
    if not (np.isfinite(s) and np.isfinite(q)):
        return False
    v = pos["direction"] * s
    if r.oiadd9 == "AT_LEAST_ENTRY_STRENGTH":
        e = pos.get("_strength9")
        return e is not None and v >= e and v > q
    return v > q


def buy_more9(sp, pos, i, decided, filled, price, reason):
    risk = L4.reserve(sp, price, filled); fee0 = L4.fee(sp, price, filled * sp.lot, True)
    avg = (pos["entry"] * pos["lots"] + price * filled) / (pos["lots"] + filled)
    pos["reserve"] = round(pos["reserve"] + risk, 2)
    pos["net"] = round(pos["net"] - fee0, 2); pos["fees"] = round(pos["fees"] + fee0, 2)
    pos["lots"] += filled; pos["open"] += filled; pos["entry"] = avg
    pos["stage_added"] = pos.get("stage_added", 0) + filled
    pos["stop"] = max(pos["stop"], round(avg * (1 - pos["rule_stop"]), 2))
    pos["events"].append(dict(i=i, decision_i=decided, side="BUY", reason=reason, lots=filled, price=price, fees=fee0))
    return risk


# ------------------------------------------------------------------ the day loop (copy of run_day8 + hooks)
def run_day9(t, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False, direct=None):
    sp = L4.spec_of(t); LOT = sp.lot; k = rule.size_k
    assert rule.setup3 not in ("PAIR", "PIN", "LASTHALF") and not rule.bank_r and not rule.regime_min and not rule.squeeze
    assert not (rule.core_bank or rule.core_child or rule.ladder or rule.liq_pick), "round-6 EN63/EN65/ladder hooks: use run_day6"
    dirs, sdist, tdist = signals9(t, rule) if direct is None else (direct.copy(), None, None)
    dirs = L7.gated(t, rule, dirs)
    meta9 = t.meta9.get(rule.sig9, {}) if rule.sig9 else {}
    spent = 0.0; positions = []; next_i = 0; pending_entry = None; pending_exit = None; pending_add = None; pos = None
    rejected = 0; missed = []; stopped = None; watch = None; intents = 0; due = -1; adds9 = 0
    cap_parents = rule.max_parents or rule.slots
    for i in range(int(np.searchsorted(t.minute, rule.start)), t.n):
        closed = None
        if pending_exit:
            qty, reason, decided = pending_exit
            filled, px = L7._exe7(sp, t, i, pos["j"], "SELL", scenario, min(qty, pos["open"]))
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
            filled, px = L7._exe7(sp, t, i, pos["j"], "BUY", scenario, n)
            if filled and px is not None and px <= lim:
                left = pos["room"] - pos["reserve"]
                if why == "STAGE_ADD":
                    left = min(left, cash - pos["reserve"])
                while filled and L4.reserve(sp, px, filled) > left + .01:
                    filled -= 1
                if filled and why == "STAGE_ADD":
                    spent += buy_more9(sp, pos, i, decided, filled, px, why)
                elif filled:
                    spent += L4._buy_more(sp, pos, i, decided, filled, px, "ADD" if why == "BLIND" else why,
                                          "max" if (rule.scout or rule.blind_add or why == "FALLBACK") and not rule.no_pstop else "none" if rule.no_pstop else "reset")
            elif why == "STAGE_ADD":
                pos["stage_unfilled"] = pos.get("stage_unfilled", 0) + 1
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
                filled, px = L7._exe7(sp, t, i, j, "BUY", scenario, lots)
            if filled < max(1, math.ceil(lots * .25)) or px is None or px > limit:
                if not (rule.patient and filled and px is not None and px <= limit):
                    rejected += 1; continue
            risk = L4.reserve(sp, px, filled); assert risk <= room + .01
            spent += risk
            pos = L4._open(sp, t, i, rule, j, filled, px, decision, sign, a_, room, origin, meta); pos["rule_stop"] = rule.stop; pos["policy8"] = rule.setup8
            pos["reserve0"] = pos["reserve"]
            if meta.get("fb"):
                pos["fallback"] = (meta["fb"][0], decision, meta["fb"][1])
            if meta.get("xspec"):
                pos["xspec"] = dict(meta["xspec"])
            if "add9" in meta:
                pos["add9"] = meta["add9"]; pos["planned9"] = meta["planned9"]
            for key in ("z", "event_i"):
                if key in meta:
                    pos[key + "9"] = meta[key]
            if rule.stage9 > 0 and rule.oiadd9 == "AT_LEAST_ENTRY_STRENGTH":
                s0 = fixed_score(t, i, pos, rule)
                pos["_strength9"] = float(sign * s0) if np.isfinite(s0) else None
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
                reason, qty = decide9(sp, t, i, pos, rule, bid, row)
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
                elif reason is None and rule.stage9 > 0 and pos.get("add9") and pos["add9"][0] > 0 and not pos.get("runner") \
                        and t.minute[i] < 870 and i < t.n - 1 and np.isfinite(row).all() \
                        and (not rule.max_intents or intents < rule.max_intents) and stage_trigger(t, i, pos, rule, bid):
                    n2, ask0, addp = pos["add9"]
                    ask = L4.ask_of(row[3]); lim = E.down(min(ask * (1 + rule.chase), addp))
                    if lim >= ask:                              # submittable: one add, one buy submission
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
        cap = int(round(rule.max_lots * mult * k))
        if rule.atm_itm:
            pick = L4.choose_atm(sp, t, i, sign, room, rule.chase)
        else:
            pick = choose9(sp, t, i, sign, replace(rule, max_lots=cap) if cap != rule.max_lots else rule, room, cash, meta)
        if pick:
            j, lots, limit = pick
            if meta.get("max_lots"):
                lots = min(lots, meta["max_lots"])
            if (rule.scale_in or rule.scout or rule.blind_add) and lots >= 2:
                first = math.ceil(lots / 2); meta.update(add=lots - first, planned=lots); lots = first
            if rule.stage9:
                N, n1, n2, ask0 = staged_plan(sp, t, i, j, lots, limit, rule, room, cash)
                lots = n1; meta["planned9"] = N
                meta["add9"] = (n2, ask0, E.down(ADD_PRICE * ask0))
            if rule.passive or rule.patient:
                qc = float(t.q[i, j, 3]); meta["passive"] = E.down(qc - E.half(qc)); meta["ask0"] = L4.ask_of(qc)
                if meta["passive"] <= 0:
                    continue
            origin = meta.pop("origin", None) or ("E032" if not rule.setup3 else rule.setup3)
            if rule.setup3 in L6.SETUPS6:
                meta["xspec"] = L6.XSPEC.get((und(t), t.day, int(i), rule.setup3))
            meta = {key: v for key, v in meta.items() if key != "pick"} | ({"event_i": meta["pick"]["event_i"]} if "pick" in meta else {})
            pending_entry = (j, lots, limit, i, sign, t.features[rule.look][i, 4], room, origin, meta); intents += 1
            due = i + 1 + rule.entry_delay
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
                minutes_in=tim, adds9=adds9)


# ------------------------------------------------------------------ wallets
BRAKES = ((4000, 0.), (3000, .25), (1500, .5))


def scale_of(dd):
    for lim, s in BRAKES:
        if dd >= lim:
            return s
    return 1.


def wallet_steps(pairs, scenario="ordinary", start=30000., retain=.5):
    """Continuous own-cash wallet over (tape, rule) pairs: lab8.wallet semantics, rule may change between sessions."""
    P = W = peak = liq = 0.; rows = []
    for t, r in pairs:
        cash = start + P - W; dd = peak - P; scale = scale_of(dd)
        row = run_day9(t, r, scenario, cash, min(L7.budget_of(r) * scale, cash), False)
        liq = max(liq, peak - (P + min(0., row["marked_worst"])))
        P = round(P + row["net"], 2); peak = max(peak, P)
        W = round(W + max(0., round(retain * max(P, 0.) - W, 2)), 2)
        assert cash >= 0 and start + P - W >= -.01
        rows.append(dict(day=row["day"], net=row["net"], trades=row["trades"], P=P, W=W, scale=scale, cash_after=round(start + P - W, 2)))
    return dict(P=P, swept=W, wallet=round(start + P - W, 2), combined=round(start + P, 2), liq_dd=round(liq, 2),
                halted=sum(x["scale"] == 0 for x in rows), first_halt=next((x["day"] for x in rows if x["scale"] == 0), None), days=rows)


def wallet9(book, r, scenario="ordinary", start=30000., retain=.5):
    return wallet_steps([(t, r) for t in book], scenario, start, retain)

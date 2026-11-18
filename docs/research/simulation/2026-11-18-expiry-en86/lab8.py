"""Isolated round-8 policy hooks. The day loop is a checked copy of run_day7.

No prior file or runtime global is edited. Hooks off must reproduce round7.
"""
from dataclasses import dataclass,asdict,replace
import math
import numpy as np
from data8 import L7,basket,components
L6,L5,L4,L3,E,D4=L7.L6,L7.L5,L7.L4,L7.L3,L7.E,L7.D4
und=L7.und
LOG_INTENTS=None

@dataclass(frozen=True)
class Rule8(L7.Rule):
    setup8: str=''
    selector8: str=''
    info_exit8: bool=False

def R8(rule=None,**kw):
    return replace(Rule8(**asdict(rule or L7.E03_ENV)),**kw)

def signals8(t,r):
    if not r.setup8: return L7.signals7(t,r)
    a=t.signals8.get(r.setup8,np.zeros(t.n,dtype=np.int8)).copy()
    a[(t.minute<r.start)|(t.minute>=r.end)]=0
    for i in np.flatnonzero(a):
        if not np.isfinite(t.close[i]) or not L4._avail(t,int(i),int(a[i])):a[i]=0
    return a,None,None

def highest(sp,t,i,d,r,room,cash):
    candidates=[]
    for j in range(len(t.strikes)):
        if t.kinds[j]!=d or not np.isfinite(t.q[i,j]).all(): continue
        cl=float(t.q[i,j,3]); ask=L4.ask_of(cl); bid=L4.bid_of(cl)
        if bid<=0 or int(t.q[i,j,4]*.2)//sp.lot<1: continue
        lim=E.down(min(ask*(1+r.chase),(min(room,cash)-2*sp.order)/(sp.lot*(1+sp.buy_rate))))
        if lim<ask or L4.reserve(sp,lim,1)>min(room,cash)+.01: continue
        friction=(ask-bid)*sp.lot+L4.fee(sp,ask,sp.lot,True)+L4.fee(sp,bid,sp.lot,False)
        candidates.append((d*(float(t.strikes[j])-float(t.close[i])),friction,float(t.strikes[j]),j,lim))
    if not candidates: return None
    x=min(candidates)
    return x[3],1,x[4]

def choose8(sp,t,i,d,r,room,cash):
    if r.selector8 in ('pullback','pullback_high'):
        meta=t.picks8.get((r.setup8,i))
        if meta is None: return None
        j,ask0=meta['j'],meta['ask0']
        row=t.q[i,j]
        if not np.isfinite(row).all(): return None
        ask=L4.ask_of(row[3]); limit=E.down(min(ask*(1+r.chase),ask0*1.08))
        cap=1 if r.selector8=='pullback_high' else r.max_lots
        cap=min(cap,int(row[4]*.2)//sp.lot)
        while cap and L4.reserve(sp,limit,cap)>min(room,cash)+.01: cap-=1
        return (j,cap,limit) if cap and limit>=ask else None
    if r.selector8=='highest': return highest(sp,t,i,d,r,room,cash)
    return L4.choose4(sp,t,i,d,r,room,cash)

def decide8(sp,t,i,pos,r,bid,row):
    reason,qty=L6.decide6(sp,t,i,pos,r,bid,row)
    if not r.info_exit8 or reason: return reason,qty
    if '_basket8' not in pos: pos['_basket8']=basket(t,pos['entry_i'])
    score=components(t,i,pos['_basket8'])[0]
    previous=pos.get('_info_last8')
    count=pos.get('_info_count8',0) if previous==i-1 else 0
    count=count+1 if np.isfinite(score) and pos['direction']*score<0 else 0
    pos['_info_last8']=i; pos['_info_count8']=count
    return ('OI_REVERSAL',pos['open']) if count>=2 else (None,qty)

def run_day8(t, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False, direct=None):
    sp = L4.spec_of(t); LOT = sp.lot; k = rule.size_k
    assert rule.setup3 not in ("PAIR", "PIN", "LASTHALF") and not rule.bank_r and not rule.regime_min and not rule.squeeze
    assert not (rule.core_bank or rule.core_child or rule.ladder or rule.liq_pick), "round-6 EN63/EN65/ladder hooks: use run_day6"
    dirs, sdist, tdist = signals8(t, rule) if direct is None else (direct.copy(), None, None)
    dirs = L7.gated(t, rule, dirs)
    spent = 0.0; positions = []; next_i = 0; pending_entry = None; pending_exit = None; pending_add = None; pos = None
    rejected = 0; missed = []; stopped = None; watch = None; intents = 0; due = -1
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
                filled, px = L7._exe7(sp, t, i, j, "BUY", scenario, lots)
            if filled < max(1, math.ceil(lots * .25)) or px is None or px > limit:
                if not (rule.patient and filled and px is not None and px <= limit):
                    rejected += 1; continue
            risk = L4.reserve(sp, px, filled); assert risk <= room + .01
            spent += risk
            pos = L4._open(sp, t, i, rule, j, filled, px, decision, sign, a_, room, origin, meta); pos["rule_stop"] = rule.stop; pos["policy8"] = rule.setup8
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
                reason, qty = decide8(sp, t, i, pos, rule, bid, row)
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
            pick = choose8(sp, t, i, sign, replace(rule, max_lots=cap) if cap != rule.max_lots else rule, room, cash)
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
    if L7.PERT7["extra_fee"]:
        for p in positions:
            p["net"] = round(p["net"] - L7.PERT7["extra_fee"], 2); p["fees"] = round(p["fees"] + L7.PERT7["extra_fee"], 2)
    net = round(sum(p["net"] for p in positions), 2)
    if rule.room_mode == "loss":
        assert net >= -budget - .03 - L7.PERT7["extra_fee"] * len(positions), (t.day, net, budget)
    else:
        assert spent <= budget + .02 and net >= -spent - .03 - L7.PERT7["extra_fee"] * len(positions), (t.day, spent, budget, net)
    mw = L6.marked_worst(sp, t, positions)
    tim = sum(max(0, int(p.get("exit_i", t.n)) - int(p["entry_i"])) for p in positions)
    return dict(day=t.day, net=net, trades=len(positions), spent=round(spent, 2),
                fees=round(sum(p["fees"] for p in positions), 2), unresolved=unresolved, rejected=rejected,
                positions=positions if details else [], marked_worst=mw, calm=False, missed=missed if details else [], intents=intents,
                minutes_in=tim)

ARMS={
    'E03_env':R8(), 'E032_native':R8(L7.E032), 'EN55_native':R8(L7.EN55),
    'EN83':R8(setup8='RAW'),
    'EN87':R8(setup8='GATE'), 'EN87_unrelated_ctl':R8(setup8='GATE_UNRELATED'),
    'EN88':R8(setup8='RESID'), 'EN88_px_ctl':R8(setup8='RESID_PX'),
    'EN89':R8(setup8='PULL',selector8='pullback'),
    'EN89_delay_ctl':R8(setup8='DELAY',selector8='pullback'),
    'EN89_unrelated_ctl':R8(setup8='PULL_UNRELATED',selector8='pullback'),
    'EN90':R8(setup8='CONTRACT'), 'EN90_growth_ctl':R8(setup8='CONTRACT_GROWTH'),
    'EN90_raw_ctl':R8(setup8='CONTRACT_RAW'),
    'EN91':R8(setup8='RAW',hold=24),
    'EN92':R8(setup8='RAW',selector8='highest',max_lots=1),
    'EN92_one_ctl':R8(setup8='RAW',max_lots=1),
    'EN93':R8(setup8='PAYOFF'), 'EN93_icpt_ctl':R8(setup8='PAYOFF_ICPT'),
    'EN93_noinfo_ctl':R8(setup8='PAYOFF_NOINFO'),
    'EN94':R8(setup8='RAW',info_exit8=True),
    'EN95':R8(setup8='PULL_HIGH',selector8='pullback_high',max_lots=1,info_exit8=True),
    'EN95_noentry_ctl':R8(setup8='RAW',selector8='highest',max_lots=1,info_exit8=True),
    'EN95_nochooser_ctl':R8(setup8='PULL',selector8='pullback',info_exit8=True),
    'EN95_noexit_ctl':R8(setup8='PULL_HIGH',selector8='pullback_high',max_lots=1),
}
PRIMARY=tuple(f'EN{i}' for i in range(87,96))

def run_fixed(book,r,scenario='ordinary',details=False):
    return [run_day8(t,r,scenario,30000.,L7.budget_of(r),details) for t in book]

def wallet(book,r,scenario='ordinary',start=30000.,retain=.5):
    P=W=peak=liq=0.; rows=[]
    for t in book:
        cash=start+P-W; dd=peak-P
        scale=0. if dd>=4000 else .25 if dd>=3000 else .5 if dd>=1500 else 1.
        row=run_day8(t,r,scenario,cash,min(L7.budget_of(r)*scale,cash),False)
        liq=max(liq,peak-(P+min(0.,row['marked_worst'])))
        P=round(P+row['net'],2); peak=max(peak,P)
        W=round(W+max(0.,round(retain*max(P,0.)-W,2)),2)
        assert cash>=0 and start+P-W>=-.01
        row.update(P=P,W=W,scale=scale,cash_after=round(start+P-W,2));rows.append(row)
    return dict(P=P,swept=W,wallet=round(start+P-W,2),combined=round(start+P,2),liq_dd=round(liq,2),
                halted=sum(x['scale']==0 for x in rows),first_halt=next((x['day'] for x in rows if x['scale']==0),None),days=rows)

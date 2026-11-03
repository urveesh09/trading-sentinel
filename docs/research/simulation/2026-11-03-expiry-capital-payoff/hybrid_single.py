"""Generated one-trigger trade engines; inspect asserted edits in hybrid_study.py."""
from hybrid_lab import E,X,D,L,LOT,PARTIAL,stalled,timed_out,recover_lots,single_dirs
from credit_lab import contracts,entry,close_quote,close_position,reserve,CLOSE_EXTRA,FEE_BUFFER
import math
import numpy as np

def long_single(t, decision_index, signal, fixed_pick, rule, scenario="ordinary", cash=E.START_CASH, budget=E.BUDGET, details=False):
    dirs = single_dirs(t.n, decision_index, signal)
    spent = 0.0; positions = []; next_i = 0; pending_entry = None; pending_exit = None; pos = None
    rejected = 0; marks = []
    for i in range(int(np.searchsorted(t.minute, rule.start)), t.n):
        if pending_exit:
            qty, reason, decided = pending_exit
            filled, price = E.executable(t, i, pos["j"], "SELL", scenario, min(qty, pos["open"]))
            if filled:
                cost = E.fee(price, filled * LOT, False); gross = round((price - pos["entry"]) * filled * LOT, 2)
                pos["net"] = round(pos["net"] + gross - cost, 2); pos["fees"] = round(pos["fees"] + cost, 2); pos["open"] -= filled
                pos["events"].append(dict(i=i, decision_i=decided, side="SELL", reason=reason, lots=filled, price=price, fees=cost))
                if reason == "BANK":
                    pos["banked"] = True
                if reason == "TARGET_BASE":
                    pos["runner"] = True
                    pos["stop"] = max(round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
                if not pos["open"]:
                    cash = round(cash + pos["net"], 2); pos["exit_i"] = i; positions.append(pos); pos = None; pending_exit = None; next_i = i + 5
                else:
                    pending_exit = (pos["open"], reason, decided) if reason not in PARTIAL else None
            elif reason in PARTIAL:
                pending_exit = None
            if pending_exit:
                continue
        if pending_entry:
            j, lots, limit, decision, sign, atr, room = pending_entry; pending_entry = None
            filled, price = E.executable(t, i, j, "BUY", scenario, lots)
            if filled < max(1, math.ceil(lots * .25)) or price is None or price > limit:
                rejected += 1; continue
            risk = E.reserve(price, filled); assert risk <= room + .01
            spent += risk
            pos = dict(day=t.day, j=j, symbol=t.symbols[j], direction=sign, entry_i=i, decision_i=decision, entry=price, lots=filled,
                       open=filled, reserve=round(risk, 2), peak=price, stop=round(price * (1 - rule.stop), 2), banked=False,
                       net=-E.fee(price, filled * LOT, True), fees=E.fee(price, filled * LOT, True),
                       underlying_stop=float(t.close[decision] - sign * atr * rule.underlying_stop),
                       events=[dict(i=i, decision_i=decision, side="BUY", lots=filled, price=price, fees=E.fee(price, filled * LOT, True))])
        if pos:
            row = t.q[i, pos["j"]]
            bid = E.down(float(row[3]) - E.half(float(row[3]))) if np.isfinite(row[3]) and np.isfinite(row[4]) and row[4] * .2 >= LOT else None
            reason = None; qty = pos["open"]
            if t.minute[i] >= 928:
                reason = "FLAT_TIME"
            elif bid is not None and bid > 0 and pos.get("runner") and rule.split:
                # The free runner: no idle or index stop, a floor at runner_floor x entry, a wide trail.
                pos["peak"] = max(pos["peak"], bid)
                pos["stop"] = max(pos["stop"], round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
                if bid <= pos["stop"]:
                    reason = "RUNNER_TRAIL"
                elif rule.hero_target and bid >= pos["entry"] * (1 + rule.hero_target):
                    reason = "HERO_TARGET"
                mark = pos["net"] + (bid - pos["entry"]) * pos["open"] * LOT - E.fee(bid, pos["open"] * LOT, False)
                marks.append(mark + sum(p["net"] for p in positions))
            elif bid is not None and bid > 0:
                pos["peak"] = max(pos["peak"], bid)
                gain = pos["peak"] / pos["entry"] - 1
                if gain >= rule.arm:
                    pos["stop"] = max(pos["stop"], round(pos["peak"] * rule.keep, 2))
                if rule.lock_arm and gain >= rule.lock_arm:
                    pos["stop"] = max(pos["stop"], round(pos["entry"] * rule.lock_floor, 2))
                if rule.runner_keep and not rule.split and (pos["banked"] or gain >= rule.runner_arm):
                    # A runner's floor is its own, wider share of the peak, and only rises from there.
                    pos["runner"] = True
                    pos["runner_stop"] = max(pos.get("runner_stop", 0.0), round(pos["peak"] * rule.runner_keep, 2))
                    pos["stop"] = pos["runner_stop"]
                if bid <= pos["stop"]:
                    reason = "TRAIL" if pos["stop"] >= pos["entry"] else "STOP"
                elif np.isfinite(t.close[i]) and rule.underlying_stop > 0 and not pos.get("runner") \
                        and pos["direction"] * (t.close[i] - pos["underlying_stop"]) < 0:
                    reason = "STRUCTURE"
                elif bid >= pos["entry"] * (1 + rule.target):
                    reason = "TARGET"
                    if rule.split and pos["open"] >= 2:
                        reason, qty = "TARGET_BASE", pos["open"] - pos["open"] // 2
                    elif rule.split and rule.solo_runner:
                        # Decided on this bar's bid, like the sale it replaces; nothing is sold.
                        reason = None
                        pos["runner"] = True
                        pos["stop"] = max(round(pos["entry"] * rule.runner_floor, 2), round(pos["peak"] * rule.runner_keep, 2))
                elif rule.bank_mult and not pos["banked"] and pos["open"] >= 2 and bid >= pos["entry"] * rule.bank_mult:
                    take = recover_lots(pos, bid)
                    if take:
                        reason, qty = "BANK", take
                elif stalled(rule, i, pos, bid):
                    reason = "STALL"
                elif timed_out(t, rule, i, pos, bid, gain):
                    reason = "TIME"
                mark = pos["net"] + (bid - pos["entry"]) * pos["open"] * LOT - E.fee(bid, pos["open"] * LOT, False)
                marks.append(mark + sum(p["net"] for p in positions))
            if reason and i < t.n - 1:
                pending_exit = (qty, reason, i)
            continue
        if pending_exit or pending_entry or i < next_i or i >= t.n - 1 or len(positions) >= rule.slots:
            continue
        sign = int(dirs[i])
        if not sign:
            continue
        room = min(E.BUDGET / rule.slots, budget - spent, cash)
        if room <= 0:
            continue
        pick = fixed_pick if E.reserve(fixed_pick[2], fixed_pick[1]) <= room + .01 else None
        if pick:
            j, lots, limit = pick
            pending_entry = (j, lots, limit, i, sign, t.features[rule.look][i, 4], room)
    unresolved = 0
    if pos:
        unresolved = 1
        pos["net"] = round(pos["net"] - pos["entry"] * pos["open"] * LOT, 2)
        pos["unresolved"] = True; positions.append(pos)
    net = round(sum(p["net"] for p in positions), 2)
    assert spent <= budget + .02 and net >= -spent - .03
    return dict(day=t.day, net=net, trades=len(positions), spent=round(spent, 2), fees=round(sum(p["fees"] for p in positions), 2),
                unresolved=unresolved, rejected=rejected, positions=positions if details else [], marked_worst=min(marks, default=0.))


def credit_single(t,decision_index,signal,rule,scenario,cash,budget,details=False):
    dirs=single_dirs(t.n,decision_index,signal);positions=[];pending=None;closing=None;pos=None;spent=0.;next_i=0;rejected=0;marks=[]
    for i in range(int(np.searchsorted(t.minute,780)),t.n):
        if closing:
            reason,decision=closing;q=close_quote(t,i,pos['legs'],scenario)
            if q and close_position(pos,q,i,decision,reason):
                cash=round(cash+pos['net'],2);positions.append(pos);pos=None;closing=None;next_i=i+5
            if closing:continue
        if pending:
            legs,signal,decision,atr,limit,room=pending;pending=None;q=entry(t,i,legs,scenario)
            if not q or not 0<q['credit']<rule.width or q['credit']<limit:
                rejected+=1;continue
            risk=reserve(q['credit'],q['fees'],rule);collateral=(rule.width+CLOSE_EXTRA)*LOT+q['fees']+FEE_BUFFER
            if risk>room+.01 or collateral>cash+.01 or q['hedge']*LOT+E.fee(q['hedge'],LOT,True)>cash+.01:
                rejected+=1;continue
            if q['credit']*LOT<=q['fees']+2*E.ORDER:rejected+=1;continue
            spent+=risk
            pos=dict(day=t.day,entry_i=i,decision_i=decision,legs=list(legs),direction=int(signal),
              symbols=[t.symbols[j] for j in legs],width=rule.width,short_entry=q['short'],hedge_entry=q['hedge'],credit=q['credit'],
              entry_fees=q['fees'],reserve=risk,collateral=collateral,underlying_stop=float(t.close[decision]-signal*2*atr))
        if pos:
            q=close_quote(t,i,pos['legs'],scenario,mark=True);reason=None
            if t.minute[i]>=rule.flat:reason='FLAT_PRE_AUCTION'
            elif q:
                mark=(pos['credit']-q['cost'])*LOT-pos['entry_fees']-q['fees'];marks.append(mark+sum(p['net'] for p in positions))
                if pos['direction']*(t.close[i]-pos['underlying_stop'])<0:reason='STRUCTURE'
                elif q['cost']>=pos['credit']*rule.stop:reason='CREDIT_STOP'
                elif q['cost']<=pos['credit']*rule.take:reason='TAKE_HALF_CREDIT'
                elif rule.hold and i-pos['entry_i']>=rule.hold:reason='TIME'
            if reason and i<t.n-1:closing=(reason,i)
            continue
        if i<next_i or len(positions)>=2 or i>=t.n-1 or t.minute[i]>=900:continue
        signal=int(dirs[i])
        if not signal:continue
        legs=contracts(t,i,signal,rule)
        if not legs:continue
        q=entry(t,i,legs,scenario,mark=True)
        if not q or not 0<q['credit']<rule.width:continue
        room=min(budget-spent,cash)
        if reserve(q['credit']*.9,q['fees'],rule)>room+.01:continue
        pending=(legs,signal,i,float(t.features[10][i,4]),E.up(q['credit']*.9),room)
    unresolved=0
    if pos:
        unresolved=1;pos.update(unresolved_short=1,residual_long=1,net=-pos['reserve'],filled_fee=-pos['entry_fees'],
           assumed=round(-pos['reserve']+pos['entry_fees'],2),fees=pos['entry_fees'],reason='UNRESOLVED_SHORT',exit_i=None)
        positions.append(pos)
    assert spent<=budget+.02
    net=round(sum(p['net'] for p in positions),2)
    return dict(day=t.day,net=net,filled_fee=round(sum(p['filled_fee'] for p in positions),2),assumed=round(sum(p['assumed'] for p in positions),2),
      fees=round(sum(p['fees'] for p in positions),2),trades=len(positions),spent=round(spent,2),unresolved=unresolved,
      residual_longs=sum(p['residual_long'] for p in positions),rejected=rejected,positions=positions if details else [],marked_worst=min(marks,default=0.))

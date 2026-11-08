"""N012 round three. Use actual chain alternatives under the original planner."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import copy
import hashlib
import json
import subprocess

import round1 as r
from config import settings
from fno_chain import RISK_FREE_RATE, years_to_expiry
from fno_costs import calc_fno_costs
from options_math import black76_price

HERE=Path(__file__).resolve().parent
T=r.f.T
planner_previous=T._planner
plain=r.f.L._native
REFUSALS={"min_oi","min_volume","two_sided_market","max_spread","quote_freshness",
          "quote_envelope","pool_min_viable","pool_below_min_viable","reward_risk_below_min"}


def books():
    base=r.books()["N11T"]
    return {k:{**copy.deepcopy(base),"label":"N12|"+k,"n12":k}
            for k in ("CHAIN_FALLBACK","STRIKE_DOMINANCE")}


def economics(plan,sig,snap,now,qty,stress):
    """Conservative comparable scenarios, used only to rank observed candidates."""
    q=plan.quote
    remaining=max(0.,years_to_expiry(q.contract.expiry,now)-45/(365*24*60))
    vol=max(.01,plan.iv-.015)
    sign=1 if sig.direction.value=="LONG" else -1
    if min(sign*(sig.target_underlying-snap.forward),sign*(snap.forward-sig.stop_underlying))<=0:
        return None
    spread=(q.ask-q.bid)/2
    def net(future):
        bid=max(0.,black76_price(float(future),q.contract.strike,remaining,vol,RISK_FREE_RATE,sign==1)-spread)
        return (bid-q.ask)*qty-calc_fno_costs(q.ask,bid,qty)-stress
    return net(sig.target_underlying),max(0.,-net(sig.stop_underlying))


def state_for(engine):
    return (getattr(engine,"_n11_last",None),getattr(engine,"_n11t_limit",None),engine.notes.copy())


def restore(engine,state):
    engine._n11_last,engine._n11t_limit,notes=state
    engine.notes.clear()
    engine.notes.update(notes)


def planner(sig,snap,regime,now,state):
    engine=T.ENGINE["now"]
    mode=engine.book.get("n12") if engine is not None else None
    if mode not in ("CHAIN_FALLBACK","STRIKE_DOMINANCE"):
        return planner_previous(sig,snap,regime,now,state)
    before=state_for(engine)
    native=planner_previous(sig,snap,regime,now,state)
    if native.quote is None or (mode=="CHAIN_FALLBACK" and (native.accepted or native.reject_reason not in REFUSALS)) or (
            mode=="STRIKE_DOMINANCE" and not native.accepted):
        return native
    saved=state_for(engine)
    q=native.quote
    cap=native.lots if native.accepted else 1
    if state.lot_ceiling is not None:
        cap=min(cap,state.lot_ceiling)
    if cap<1:
        return native
    capped=replace(state,lot_ceiling=cap)
    stress=T.R.extra_cost(engine.book["cost"],cap)
    quantity=cap*native.lot_size
    control=economics(native,sig,snap,now,quantity,stress) if native.accepted else None
    if mode=="STRIKE_DOMINANCE" and control is None:
        return native

    # At most two neighboring strikes. Keep expiry, instrument side, native
    # moneyness, liquidity and all subsequent admission checks in the planner.
    candidates=sorted(((k,z) for k,z in snap.quotes.items() if z.contract.instrument_type==q.contract.instrument_type
                      and z.contract.expiry==q.contract.expiry and 0<abs(z.contract.strike-q.contract.strike)<=100),
                      key=lambda x:(abs(x[1].contract.strike-q.contract.strike),x[0]))
    scored=[]
    for key,quote in candidates[:2]:
        narrowed=replace(snap,quotes={key:quote})
        trial=plain(sig,narrowed,regime,now,capped)
        if not trial.accepted or trial.lots!=cap or not .43<=abs(trial.delta)<=.67:
            continue
        estimated=economics(trial,sig,snap,now,quantity,stress)
        if estimated is None:
            continue
        reward,loss=estimated
        if mode=="CHAIN_FALLBACK" and reward>=1.3*loss and reward>=250:
            scored.append((reward/max(loss,1.),key,narrowed))
        if mode=="STRIKE_DOMINANCE" and (quote.ask<=q.ask and loss<=control[1]
                                       and reward>=control[0]+250*cap and reward>0):
            scored.append((reward-control[0],key,narrowed))
    if not scored:
        return native
    _,_,selected=max(scored,key=lambda item:(item[0],item[1]))
    restore(engine,before)
    replacement=planner_previous(sig,selected,regime,now,capped)
    if not replacement.accepted or replacement.lots!=cap:
        restore(engine,saved)
        return native
    engine.notes["n12_"+mode.lower()]+=1
    return replacement


T._planner=planner


def main():
    spec=HERE/"round3-freeze.json"
    rel=spec.relative_to(r.ROOT).as_posix()
    cfg=json.loads(spec.read_bytes())
    assert cfg==json.loads(subprocess.check_output(["git","show",f"HEAD:{rel}"],cwd=r.ROOT))
    for name,sha in cfg["files"].items():
        assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==sha
    r.verify_freeze()
    selected=books()
    r.f.Z.N.run_books(selected,2)
    out={k:r.metrics(r.raw_for(b)) for k,b in selected.items()}
    for k,v in out.items():
        print(r.YEAR,k,v["net"],v["closed"],v["worst_day"],v["drawdown_pct"],v["notes"].get("n12_"+k.lower(),0),flush=True)
    with (HERE/f"round3-{r.YEAR}.json").open("x",encoding="utf-8") as f:
        json.dump(out,f,indent=2,sort_keys=True)
        f.write("\n")


if __name__=="__main__":
    main()

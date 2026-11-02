"""Two predeclared exit mechanisms; research only, no entry/size/clock change."""
from dataclasses import replace
import math


def loss_reason(net,paid,fraction):
    if net is None or not math.isfinite(net) or not math.isfinite(paid) or paid<=0:
        return None
    if not 0<fraction<1:
        raise ValueError("invalid loss fraction")
    return "E01_PAIR_LOSS" if net<=-fraction*paid else None


def install(module,policy):
    family,number=policy.rsplit("_",1);fraction=int(number)/100
    if family=="CSTOP":
        module.POLICIES["C"]=replace(module.POLICIES["C"],hard_stop=fraction)
        return
    if family!="PAIR":raise ValueError(policy)
    original=module._pair_target

    def target(pair,quotes,now):
        # The native predicate is called before position management. A pair loss
        # latches its OWN reason and returns False, so it cannot be labelled a target.
        if original(pair,quotes,now):return True
        if len(pair)==2 and all(p["play"]=="B" and p["status"]=="OPEN" and not p["exit_pending"] for p in pair):
            value=module.liquidation_net(pair,quotes,now)
            paid=sum(p["entry_price"]*p["lots"]*p["lot_size"] for p in pair)
            why=loss_reason(value,paid,fraction)
            if why:
                for p in pair:p["exit_pending"]=why
        return False
    module._pair_target=target


PRIMARY=("PAIR_30","CSTOP_30")
NEIGHBOURS=("PAIR_20","PAIR_40","CSTOP_20","CSTOP_40")

"""Independent validation cases; added after source freeze, changes no rule."""
import copy
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import score_n101 as S
from test_n101 import AT, lab, setup_add


def case():
    return {"total":{"net":100,"worst_day":-10,"fall_pct":2},"annual":{y:{"net":25} for y in S.YEARS},
            "double_net":50,"without_top5":30,"accounts":{"200":{"end":300000}}}


def test_more_profit_alone_cannot_pass_if_the_continuous_account_is_worse():
    base=case(); a=copy.deepcopy(base); a["total"]["net"]=200; a["accounts"]["200"]["end"]=290000
    checks=S.superiority(a,base)
    assert checks["annual_net_above_n10"] and not checks["every_continuous_cost_no_worse"]
    assert not all(checks.values())


def test_equal_profit_is_not_strict_economic_superiority():
    assert not S.superiority(case(),case())["annual_net_above_n10"]


def test_short_view_buys_and_protects_the_put_using_its_own_option_price(lab):
    engine,book,leg,obs=setup_add(lab)
    leg.direction="SHORT"
    leg.stop_underlying=23050
    obs.future.ltp=22940
    lab.maybe_add(engine,book,leg,obs,AT)
    assert len(leg._n10["children"])==1 and leg.premium_stop>100


def test_bad_quoting_cannot_raise_stop_or_admit_a_child(lab):
    engine,book,leg,obs=setup_add(lab,bid=float("nan"))
    lab.maybe_add(engine,book,leg,obs,AT)
    assert not leg._n10["children"] and leg.premium_stop==75


def test_native_halt_remains_authoritative_even_with_enough_profit(lab):
    engine,book,leg,obs=setup_add(lab)
    engine._halts=lambda *args:("daily_loss_halt",)
    lab.maybe_add(engine,book,leg,obs,AT)
    assert not leg._n10["children"] and leg.premium_stop==75


def test_half_paise_stress_is_reconciled_from_the_frozen_function_not_rounded_display():
    from audit_n101 import exact_extra
    value=exact_extra([199,4.975],1)
    assert abs(value-203.975)<1e-9
    assert abs(value-round(value,2))>0.0049

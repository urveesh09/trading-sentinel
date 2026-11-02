import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import policies as P
import score_e01 as S
from verify_controls import normalize_absent_schema


@pytest.mark.parametrize("value",[None,float('nan'),float('inf')])
def test_unknown_pair_is_not_a_zero_mark_or_a_loss_trigger(value):
    assert P.loss_reason(value,100,.3) is None


def test_pair_stop_is_net_and_uses_the_declared_boundary():
    assert P.loss_reason(-30,100,.3)=="E01_PAIR_LOSS"
    assert P.loss_reason(-29.99,100,.3) is None
    assert P.loss_reason(20,100,.3) is None


def test_loss_never_becomes_a_profit_target_label():
    module=NS(_pair_target=lambda *a:False,liquidation_net=lambda *a:-40)
    P.install(module,"PAIR_30")
    pair=[dict(play="B",status="OPEN",exit_pending=None,entry_price=5,lots=1,lot_size=10) for _ in range(2)]
    assert not module._pair_target(pair,{},None)
    assert {p["exit_pending"] for p in pair}=={"E01_PAIR_LOSS"}


def test_thin_or_missing_pair_cannot_create_a_pending_exit():
    module=NS(_pair_target=lambda *a:False,liquidation_net=lambda *a:None)
    P.install(module,"PAIR_30")
    pair=[dict(play="B",status="OPEN",exit_pending=None,entry_price=5,lots=1,lot_size=10) for _ in range(2)]
    assert not module._pair_target(pair,{},None)
    assert all(p["exit_pending"] is None for p in pair)


def test_existing_pending_reason_is_never_replaced():
    module=NS(_pair_target=lambda *a:False,liquidation_net=lambda *a:-90)
    P.install(module,"PAIR_30")
    pair=[dict(play="B",status="OPEN",exit_pending="FLAT_TIME",entry_price=5,lots=1,lot_size=10) for _ in range(2)]
    module._pair_target(pair,{},None)
    assert all(p["exit_pending"]=="FLAT_TIME" for p in pair)


def sample(net=100,worst=-20,dd=20):
    return dict(net=net,worst_day=worst,drawdown_rupees=dd,without_best=-20,by_underlying=dict(NIFTY=60,SENSEX=40),unresolved=0)


def test_more_profit_with_a_worse_tail_is_not_an_improvement_pass():
    r=S.routes(sample(110,-25,25),sample())
    assert not r["profit_pass"] and not r["loss_pass"]


def test_worst_day_only_cannot_hide_a_drawdown_regression():
    assert not S.routes(sample(100,-10,30),sample())["loss_pass"]


def test_unresolved_money_cannot_pass_either_route():
    a=sample(200,-10,10);a["unresolved"]=1;r=S.routes(a,sample())
    assert not r["profit_pass"] and not r["loss_pass"]


def test_only_exact_legacy_schema_default_can_be_normalized():
    assert normalize_absent_schema(dict(field="bank_pending",replay=None,observed=0))
    assert not normalize_absent_schema(dict(field="net_pnl",replay=None,observed=0))
    assert not normalize_absent_schema(dict(field="bank_pending",replay=None,observed=1))

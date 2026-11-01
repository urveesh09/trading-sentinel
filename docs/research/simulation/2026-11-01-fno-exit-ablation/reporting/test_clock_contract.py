import sys
from pathlib import Path
from datetime import datetime,timedelta
from types import SimpleNamespace as NS
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import exit_lab as L
from fno_exit_rules import evaluate_single_leg_exit,live_single_leg_exit_params
@pytest.mark.parametrize('age,progress,expected',[(61.,1.,''),(91.,1.,''),(121.,1.,''),(61.,.5,''),(61.,.49,'time_stop')])
def test_native_soft_clock_already_keeps_sufficient_progress(age,progress,expected):
    now=datetime.fromisoformat('2024-01-02T10:00:00+05:30')+timedelta(minutes=age)
    leg=NS(direction='LONG',entry_time='2024-01-02T10:00:00+05:30',entry_premium=100.,premium_stop=70.,entry_underlying=1000.,stop_underlying=980.,target_underlying=1036.,atr_at_entry=10.,trail_active=0,trail_stop_underlying=None,best_underlying=1000.,best_premium=None)
    params={**live_single_leg_exit_params(L.X.settings),'FNO_TIME_STOP_MIN':60.,'FNO_TIME_STOP_MIN_R':.5,'FNO_TIME_STOP_RESPECTS_PREMIUM':False,'FNO_PROFIT_LOCK_ENABLED':False}
    decision=evaluate_single_leg_exit(leg,now_ist=now,fut_price=1000.+20*progress,exit_px_basis=100.,hard_flat=False,params=params)
    assert decision.exit_reason==expected

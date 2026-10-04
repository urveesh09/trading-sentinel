"""Regressions for actual rounding risk, A/B contamination and exit availability."""
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from penny_engine_breakout import evaluate_breakout_entry, noise_floor_stop
from penny_executor import PennyExecutor, snap_to_tick
from penny_models import PennyLeg


@pytest.mark.parametrize("entry,stop,shares,tick", [(5.10,5.07,98,.01), (10.10,10.09,49,.01),
                                                   (20.3,20.1,24,.01), (5.10,5.07,98,.05)])
def test_final_tick_distance_meets_floor_and_preserves_original_risk(entry,stop,shares,tick):
    new_stop, quantity = noise_floor_stop(entry,stop,shares,tick_size=tick)
    e,s,n,t = map(lambda v: Decimal(str(v)), (entry,stop,new_stop,tick))
    assert e-n >= max(e-s,e*Decimal('.015'),Decimal('.03'))
    assert quantity*(e-n) <= shares*(e-s)
    assert n%t == 0


def test_instrument_tick_preserves_penny_protection_and_does_not_chase_by_a_tenth():
    assert snap_to_tick(5.02,-1,.01) == 5.02
    assert snap_to_tick(5.102,1,.01) == 5.11
    assert snap_to_tick(5.102,-1,.05) == 5.10


def test_explicit_old_and_new_stop_ignore_runtime_flag(monkeypatch):
    from config import settings
    monkeypatch.setattr(settings,'PENNY_NOISE_STOP_ENABLED',True)
    risk=MagicMock(); risk.position_size.return_value=98
    kwargs=dict(ticker='X',cum_vol_today=30000,median_vol_20d=10000,
                breakout_bar={'open':5.07,'high':5.09,'low':5.07,'close':5.08},
                day_high=5.06,rsi_14=55.,as_of=datetime(2026,10,1,11,0),risk_engine=risk,stop_tick_size=.01)
    old=evaluate_breakout_entry(**kwargs,noise_stop_enabled=False)
    new=evaluate_breakout_entry(**kwargs,noise_stop_enabled=True)
    assert old['accept'] and new['accept']
    assert (old['stop_loss'],old['shares']) == (5.07,98)
    assert (new['stop_loss'],new['shares']) == (5.02,36)


def test_runtime_noise_stop_sizes_against_current_instrument_tick(monkeypatch):
    import penny_prices
    from config import settings
    monkeypatch.setattr(settings,'PENNY_NOISE_STOP_ENABLED',True)
    monkeypatch.setattr(penny_prices,'instrument_tick_size',lambda *args,**kwargs:.05)
    risk=MagicMock(); risk.position_size.return_value=98
    decision=evaluate_breakout_entry(ticker='X',cum_vol_today=30000,median_vol_20d=10000,
                breakout_bar={'open':5.07,'high':5.09,'low':5.07,'close':5.08},
                day_high=5.06,rsi_14=55.,as_of=datetime(2026,10,1,11,0),risk_engine=risk)
    assert (decision['stop_loss'],decision['shares'])==(5.0,29)
    assert Decimal(decision['shares'])*(Decimal('5.1')-Decimal(str(decision['stop_loss'])))<=Decimal('2.94')


@pytest.mark.asyncio
async def test_live_entry_with_unknown_tick_refuses_before_any_quote_or_order(monkeypatch):
    import penny_executor
    monkeypatch.setattr(penny_executor,'instrument_tick_size',lambda *a,**k:None)
    kite=AsyncMock()
    executor=PennyExecutor(kite,paper_mode=False)
    result=await executor.execute_entry('X',PennyLeg.MIS,5.1,5.02,36)
    assert result['entry_status']=='tick_metadata_missing'
    kite.get_quote.assert_not_awaited()
    kite.place_order.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_metadata_does_not_block_protective_stop(monkeypatch):
    import penny_executor
    monkeypatch.setattr(penny_executor,'instrument_tick_size',lambda *a,**k:None)
    kite=AsyncMock(); kite.place_order.return_value={'order_id':'STOP'}
    executor=PennyExecutor(kite,paper_mode=False)
    assert await executor._place_sl_m_with_retry('X',PennyLeg.MIS,5.02,36)=='STOP'
    assert kite.place_order.call_args.kwargs['trigger_price']==5.0


@pytest.mark.asyncio
async def test_stop_uses_supplied_instrument_tick():
    kite=AsyncMock(); kite.place_order.return_value={'order_id':'STOP'}
    executor=PennyExecutor(kite,paper_mode=False,tick_size_lookup=lambda ticker:.01)
    await executor._place_sl_m_with_retry('X',PennyLeg.MIS,5.02,36)
    assert kite.place_order.call_args.kwargs['trigger_price']==5.02


def test_pending_study_has_distinct_policies_and_owner_budget():
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
    import run_preregistered_study as runner
    study=runner.STUDIES['penny-noise-t3']
    assert study.arms['BASELINE']['stop_policy']=='BAR_LOW'
    assert study.arms['PEN_NOISE_STOP']['stop_policy']=='NOISE_FLOOR'
    assert study.books[study.decision_book]['bankroll']==2000.


def test_freeze_binding_detects_environment_resolved_penny_settings(monkeypatch):
    import run_preregistered_study as runner
    from config import settings
    monkeypatch.setattr(runner,'verify_snapshot',lambda path:{'rows_sha256':'unchanged'})
    monkeypatch.setattr(runner,'_sha',lambda path:'unchanged')
    study=runner.STUDIES['penny-noise-t3']
    before=runner._bound(study)
    monkeypatch.setattr(settings,'PENNY_BREAKOUT_VOL_MULT',settings.PENNY_BREAKOUT_VOL_MULT+.1)
    assert runner._bound(study)!=before


def test_cached_metadata_freshness_refresh_and_malformed_file(tmp_path,monkeypatch):
    import json
    import os
    from zoneinfo import ZoneInfo
    from config import settings
    from penny_prices import instrument_tick_size
    path=tmp_path/'universe.json'
    monkeypatch.setattr(settings,'PENNY_UNIVERSE_JSON_PATH',str(path))
    today=datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat()
    path.write_text(json.dumps({'tickers':[{'symbol':'X','tick_size':.01,'tick_size_as_of':today}]}))
    assert instrument_tick_size('x',require_today=True)==.01
    old_mtime=path.stat().st_mtime_ns
    path.write_text(json.dumps({'tickers':[{'symbol':'X','tick_size':.05,'tick_size_as_of':'2000-01-01'}]}))
    os.utime(path,ns=(old_mtime+1000000,old_mtime+1000000))
    assert instrument_tick_size('X',require_today=True) is None
    assert instrument_tick_size('X')==.05
    path.write_text('[]')
    os.utime(path,ns=(old_mtime+2000000,old_mtime+2000000))
    assert instrument_tick_size('X') is None


def test_replay_stop_and_budget_validation():
    from penny_lifecycle_replay import PennyLifecycleConfig
    for config in ({'stop_policy':'UNKNOWN'},{'bankroll':float('nan')},{'bankroll':0},
                   {'candidate_policy':'PEN_NOISE_STOP','stop_policy':'BAR_LOW'}):
        with pytest.raises(ValueError):
            PennyLifecycleConfig(tickers=('X',),**config)


def test_freeze_binding_detects_execution_cost_drift(monkeypatch):
    import run_preregistered_study as runner
    import penny_shadow
    monkeypatch.setattr(runner,'verify_snapshot',lambda path:{'rows_sha256':'unchanged'})
    monkeypatch.setattr(runner,'_sha',lambda path:'unchanged')
    study=runner.STUDIES['penny-noise-t3']
    before=runner._bound(study)
    snapshot=penny_shadow._execution_snapshot
    monkeypatch.setattr(penny_shadow,'_execution_snapshot',lambda context: {**snapshot(context),'slippage_override':.123})
    assert runner._bound(study)!=before

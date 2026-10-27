"""Independent synthetic checks; no market dataset scored by these tests."""
from dataclasses import asdict
from datetime import datetime
import importlib.util
from pathlib import Path
import random
import sys

import pandas as pd
import pytest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('o27e_lab',HERE/'lab.py')
lab=importlib.util.module_from_spec(spec); sys.modules[spec.name]=lab; spec.loader.exec_module(lab)


def bars():
    frames=[]
    for day in ['2026-09-10','2026-09-11','2026-09-14','2026-09-15','2026-09-16','2026-09-17']:
        idx=pd.date_range(day+' 09:15',periods=16,freq='5min')
        frames.append(pd.DataFrame({'open':100.,'high':101.,'low':99.,'close':100.,'volume':100.},index=idx))
    x=pd.concat(frames); x.iloc[-1]=[100.,104.,100.,103.5,200.]
    return x


def genome(family='EFFICIENCY_BREAK'):
    return {'family':family,'lookback':4,'efficiency':.35,'buffer':.1,'body':.35,'vwap':True,
            'compression':2.,'rvol':1.2,'stop':1.5,'target':1.8,'exit':'LIVE'}


def call(x,g=None,regime='REGIME_1_BULL',now=None):
    return lab.signal(x,regime,now or lab.replay.IST.localize(datetime(2026,9,17,10,35)),lab.NovelSignal('test',g or genome()))


def mirror(x):
    y=x.copy(); y['open']=200-x.open; y['close']=200-x.close
    y['high']=200-x.low; y['low']=200-x.high
    return y


@pytest.mark.parametrize('family',lab.FAMILIES[:2])
def test_breakout_and_compression_are_directionally_symmetric(family):
    x=bars(); a=call(x,genome(family)); b=call(mirror(x),genome(family))
    assert a.direction==lab.FnoDirection.LONG
    assert b.direction==lab.FnoDirection.SHORT
    assert a.stop_underlying==pytest.approx(200-b.stop_underlying)
    assert a.target_underlying==pytest.approx(200-b.target_underlying)
    assert a.bar_ts=='2026-09-17 10:30:00'


def test_compression_threshold_rejects_a_wide_setup():
    assert call(bars(),{**genome('COMPRESSION_RELEASE'),'compression':.5}).reject_reason=='novel:not_compressed'


def test_failed_auction_reclaims_the_range_and_is_symmetric():
    x=bars(); x.iloc[-2]=[100.,103.,99.8,102.,100.]; x.iloc[-1]=[102.,102.3,100.5,100.6,200.]
    a=call(x,genome('FAILED_AUCTION')); b=call(mirror(x),genome('FAILED_AUCTION'))
    assert a.direction==lab.FnoDirection.SHORT
    assert b.direction==lab.FnoDirection.LONG
    assert a.stop_underlying>103.
    assert a.target_underlying<a.close


def test_no_incomplete_bar_can_trigger():
    x=bars(); now=lab.replay.IST.localize(datetime(2026,9,17,10,31))
    a=call(x,now=now); b=call(x.iloc[:-1],now=now)
    assert asdict(a)==asdict(b)
    assert a.direction is None


def test_future_rows_do_not_change_a_signal_or_any_past_feature():
    x=bars(); future=pd.DataFrame({'open':900.,'high':2000.,'low':1.,'close':1500.,'volume':1e9},index=pd.date_range('2026-09-17 10:35',periods=8,freq='5min'))
    longer=pd.concat([x,future])
    assert asdict(call(x))==asdict(call(longer))
    pd.testing.assert_frame_equal(lab.features(x),lab.features(longer).loc[x.index])


def test_rvol_matches_the_actual_shipped_calendar_slot_definition():
    from fno_engine_mom import _rvol_time_adjusted
    x=bars(); t=x.index[-1]
    assert lab.features(x).loc[t,'rvol']==pytest.approx(_rvol_time_adjusted(x,t))


def test_crisis_and_missing_volume_refuse_entry():
    assert call(bars(),regime='REGIME_3_CRISIS').reject_reason=='novel:crisis'
    x=bars(); x.loc[x.index.date<pd.Timestamp('2026-09-17').date(),'volume']=0.
    assert call(x).direction is None


def test_missing_intraday_bars_are_not_treated_as_continuous():
    x=bars().drop(pd.Timestamp('2026-09-17 10:20'))
    assert call(x).reject_reason=='novel:bar_gap'


def test_independent_money_drawdown_and_cost_arithmetic():
    days=['2026-09-10','2026-09-11','2026-09-14']
    trades=[{'entry_time':d+'T10:00:00','exit_time':d+f'T11:0{i}:00','net_pnl':net,'gross_pnl':net+fee,'entry_qty':10,'exit_reason':'TEST'}
            for i,(d,net,fee) in enumerate([(days[0],100.,10.),(days[1],-40.,20.),(days[1],20.,5.)])]
    m=lab.metrics(trades,days)
    assert m['net']==80.
    assert m['charges']==35.
    assert m['drawdown_closed_trades']==40.
    assert m['net_without_best_trade']==-20.
    assert m['net_without_best_day']==-20.
    assert m['stressed_net_fixed_trades']==11.25
    assert m['active_days']==2 and m['green_days']==1 and m['red_days']==1
    assert m['daily'][days[2]]==0.


def test_empty_and_sparse_winners_are_never_eligible():
    m=lab.metrics([],['2026-09-10','2026-09-11','2026-09-14'])
    assert not lab.eligible(m) and lab.score(m)==-10.
    m.update(trades=50,net=1e6,net_without_best_day=5e5,stressed_net_fixed_trades=1e5)
    assert not lab.eligible(m)  # no trades in the three blocks


def test_unresolved_positions_are_counted_without_inventing_a_sale():
    m=lab.metrics([{'entry_time':'2026-09-10T10:00:00','status':'UNRESOLVED'}],['2026-09-10'])
    assert m['unresolved']==1 and m['trades']==0 and not lab.eligible(m)


def test_breeding_is_reproducible_and_inactive_genes_are_canonical():
    r=random.Random(42); a=lab.random_genome(lab.FAMILIES[0],r); b=lab.random_genome(lab.FAMILIES[0],r)
    assert lab.breed(a,b,random.Random(9))==lab.breed(a,b,random.Random(9))
    assert a['compression']==3.
    for n in lab.neighbours(a):
        assert n['family']==a['family'] and n['compression']==3.
        assert sum(n[k]!=a[k] for k in lab.GENES)==1


def test_dispatch_delegates_normal_variants_and_restores_the_original(monkeypatch):
    expected=object()
    def original(*args): return expected
    monkeypatch.setattr(lab.fno_shadow,'_variant_signal',original)
    with lab.research_dispatch():
        assert lab.fno_shadow._variant_signal(None,None,None,object()) is expected
    assert lab.fno_shadow._variant_signal is original

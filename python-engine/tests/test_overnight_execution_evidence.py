from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import sqlite3

import pytest
from config import settings
import edge_overnight_paper as eop
import overnight_execution_evidence as evidence
from tests.test_overnight_v2 import v2
from tests.test_edge_overnight_paper import TODAY,_at


def at(clock):return datetime.fromisoformat('2026-11-04T'+clock).replace(tzinfo=evidence.IST)


def observations():
    out={}
    for phase,clock,trade,volume in [('PRE','15:49:00','15:45:00',100000),
                                    ('DECISION','15:51:00','15:50:45',102000),
                                    ('END','16:03:00','15:59:00',202000)]:
        out[phase]={'received_at':at(clock).isoformat(),'quote_time':at(clock).isoformat(),
                    'last_trade_time':at(trade).isoformat(),'volume':volume,'last_price':20.}
    return out


def test_capacity_met_never_becomes_an_order_fill():
    r=evidence.assess(observations())
    assert r['status']=='CAPACITY_PROXY_MET'
    assert r['later_volume']==100000 and r['participation_quantity']==1000
    assert r['hypothetical_quantity']==623
    assert r['actual_fill']=='UNKNOWN' and r['supports_fill_claim'] is False


@pytest.mark.parametrize('phase,field,value,reason',[
    ('PRE','received_at',at('15:32:00').isoformat(),'outside_window_pre'),
    ('DECISION','quote_time',at('15:49:00').isoformat(),'stale_or_future_quote_decision'),
    ('DECISION','quote_time',at('15:52:00').isoformat(),'stale_or_future_quote_decision'),
    ('DECISION','last_trade_time',at('15:32:00').isoformat(),'no_supported_session_trade_decision'),
    ('END','last_trade_time',at('16:01:00').isoformat(),'no_supported_session_trade_end'),
    ('END','last_trade_time',at('15:50:59').isoformat(),'no_later_trade_after_decision'),
    ('END','volume',1000,'cumulative_volume_reset'),
    ('END','volume',102000,'later_trade_without_volume_increment'),
    ('END','last_price',20.05,'postclose_price_changed'),
    ('END','volume',float('nan'),'invalid_values_end'),
    ('PRE','quote_time',None,'missing_or_invalid_timestamp_pre'),
])
def test_uncertain_packets_stay_unknown(phase,field,value,reason):
    obs=observations();obs[phase][field]=value
    r=evidence.assess(obs)
    assert (r['status'],r['reason'])==('UNKNOWN',reason)
    assert r['supports_fill_claim'] is False


def test_missing_and_cross_day_evidence_not_silently_dropped():
    obs=observations();del obs['PRE'];assert evidence.assess(obs)['reason']=='missing_pre'
    obs=observations();obs['END']['last_trade_time']='2026-11-03T15:59:00+05:30'
    assert evidence.assess(obs)['reason']=='cross_date_end'
    obs=observations();obs['END']['volume']=102100
    assert evidence.assess(obs)['status']=='CAPACITY_PROXY_SHORT'


@pytest.mark.asyncio
async def test_disabled_collector_makes_no_reads_or_quotes(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'EDGE_OVERNIGHT_EXECUTION_EVIDENCE_ENABLED',False)
    out=await evidence.collect(object(),'PRE',str(tmp_path/'none.db'),now=at('15:49:00'))
    assert out=={'status':'disabled'} and list(tmp_path.iterdir())==[]
    evidence.capture_entry(str(tmp_path/'none.db'),day='2026-11-04',decided=at('15:20:00'),
                           picks=None,quotes=None,nights=None,late=None)
    assert list(tmp_path.iterdir())==[]


@pytest.mark.asyncio
async def test_collector_preserves_denominators_is_idempotent_and_keeps_old_books(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'EDGE_OVERNIGHT_EXECUTION_EVIDENCE_ENABLED',True)
    cache=str(tmp_path/'cache.db');store=eop.overnight_db_path(cache)
    with eop._store(store) as c:
        c.execute('INSERT INTO edge_overnight_paper_runs VALUES(?,?,?,?)',
            ('2026-11-04','ENTRY',json.dumps({'opened':[{'ticker':'AAA'}],'skipped':[{'ticker':'BBB'}]}),'entry'))
    before=Path(store).read_bytes();calls=[];obs=observations()
    for phase in evidence.WINDOWS:
        snap=obs[phase]
        async def quotes(_kite,tickers):
            calls.append(tickers)
            return {'AAA':{'volume':snap['volume'],'last_price':20.,'timestamp':snap['quote_time'],
                           'last_trade_time':snap['last_trade_time'],'ohlc':{'close':999.}}}
        monkeypatch.setattr(eop,'_quotes',quotes)
        r=await evidence.collect(object(),phase,cache,now=evidence.stamp(snap['received_at']))
        assert (r['requested'],r['quoted'])==(2,1)
        assert (await evidence.collect(object(),phase,cache,now=evidence.stamp(snap['received_at'])))['status']=='repeat'
    assert calls==[['AAA','BBB']]*3 and Path(store).read_bytes()==before
    out=evidence.summary(cache)
    assert out['pairs']==2 and out['counts']=={'CAPACITY_PROXY_MET':1,'UNKNOWN':1}
    assert out['rows'][0]['reference_price']==20. # prior-day ohlc.close ignored
    with sqlite3.connect(evidence.evidence_path(cache)) as c:assert c.execute('SELECT COUNT(*) FROM observations').fetchone()[0]==6


def test_comparison_read_has_evidence_without_creating_a_store(tmp_path):
    cache=str(tmp_path/'cache.db')
    r=eop.overnight_shadow_comparison(cache)['execution_evidence']
    assert r['status']=='not_collected' and r['actual_fill']=='UNKNOWN'
    assert list(tmp_path.iterdir())==[]


def test_incomplete_evidence_store_does_not_break_existing_comparison(tmp_path):
    cache=str(tmp_path/'cache.db')
    Path(evidence.evidence_path(cache)).write_bytes(b'broken evidence')
    r=eop.overnight_shadow_comparison(cache)['execution_evidence']
    assert r['status']=='unreadable_evidence' and r['actual_fill']=='UNKNOWN'


@pytest.mark.asyncio
async def test_real_entry_archives_known_inputs_without_more_quotes_or_new_positions(v2,monkeypatch):
    monkeypatch.setattr(settings,'EDGE_OVERNIGHT_EXECUTION_EVIDENCE_ENABLED',True)
    result=await eop.run_overnight_entry(v2.kite,v2.cache,now=_at(TODAY,15,20))
    assert len(v2.kite.calls)==2 and len(result['opened'])==3
    out=evidence.summary(v2.cache);shortlist=out['entry_shortlists'][0]
    assert [p['ticker'] for p in shortlist['picks']]==['AAA','BBB','CCC']
    assert shortlist['picks'][0]['night_mean']>0
    assert shortlist['picks'][1]['night_mean']<0
    assert shortlist['late'] is None and shortlist['actual_fill']=='UNKNOWN'
    assert out['pairs']==3 and out['counts']=={'UNKNOWN':3}
    assert out['reasons']=={'missing_pre':3}
    with sqlite3.connect(evidence.evidence_path(v2.cache)) as c:
        assert c.execute('SELECT COUNT(*) FROM shortlists').fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM observations').fetchone()[0]==0
    again=await eop.run_overnight_entry(v2.kite,v2.cache,now=_at(TODAY,15,21))
    assert again['repeat'] and len(v2.kite.calls)==2

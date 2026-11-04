from datetime import datetime
from pathlib import Path
import sqlite3

import pytest
import penny_smart_v3 as v3
import penny_smart_morning_evidence as evidence
from penny_instrument_identity import is_known_etf


def at(clock):return datetime.fromisoformat('2026-11-04T'+clock).replace(tzinfo=evidence.IST)


def quote(clock='09:30:00',volume=5000):
    return {'timestamp':at(clock),'last_trade_time':at('09:29:00' if clock>'09:20:00' else '09:10:30'),
            'volume':volume,'last_price':21.,'depth':{'buy':[{'price':21.,'quantity':3},{'price':20.9,'quantity':7}]}}


@pytest.mark.parametrize('symbol',['GROWWSLVR','METAL','SILVER1','SILVERADD','SILVERCASE','TATAGOLD','TATSILV'])
def test_official_registry_identifies_known_contaminating_funds(symbol):
    assert is_known_etf(symbol)


def test_exact_identity_keeps_real_companies_with_related_names():
    assert not is_known_etf('ASHOKAMET') and not is_known_etf('GOLDIAM')
    assert not v3.eq_series('METAL') and v3.eq_series('ASHOKAMET')
    from penny_universe import _is_non_equity_symbol
    assert not _is_non_equity_symbol('METAL') # shared universe intentionally unchanged


def test_bid_projection_walks_quantity_and_keeps_fill_unknown():
    r=evidence.bid_projection({'entry_price':20.,'shares':10},quote(),at('09:30:00'))
    assert r['status']=='FULL_BID_CAPACITY_PROXY' and r['exit_vwap']==pytest.approx(20.93)
    assert r['modeled_net']==pytest.approx(9.3-r['fees'],abs=1e-4)
    assert r['actual_fill']=='UNKNOWN' and r['native_quantity_was_frozen_preopen'] is False


def test_missing_depth_or_stale_packet_never_fabricates_full_sale():
    q=quote();q['depth']['buy']=q['depth']['buy'][:1]
    r=evidence.bid_projection({'entry_price':20.,'shares':10},q,at('09:30:00'))
    assert r['status']=='PARTIAL_BID_CAPACITY' and r['modeled_net'] is None
    q=quote();q['timestamp']=at('09:28:00')
    assert evidence.bid_projection({'entry_price':20.,'shares':10},q,at('09:30:00'))['reason']=='stale_or_future_packet'


def test_auction_packet_must_precede_continuous_trading():
    assert evidence.packet_quality(quote('09:12:00'),at('09:12:00'),'AUCTION') is None
    assert evidence.packet_quality(quote('09:16:00'),at('09:16:00'),'AUCTION')=='outside_receipt_window'


@pytest.mark.asyncio
async def test_disabled_is_zero_io(tmp_path,monkeypatch):
    monkeypatch.setattr(evidence,'enabled',lambda:False)
    assert await evidence.collect(object(),'AUCTION',str(tmp_path/'cache.db'),now=at('09:12:00'))=={'status':'disabled'}
    assert list(tmp_path.iterdir())==[]


@pytest.mark.asyncio
async def test_collector_is_idempotent_and_never_mutates_native_book(tmp_path,monkeypatch):
    monkeypatch.setattr(evidence,'enabled',lambda:True)
    cache=str(tmp_path/'cache.db');native=Path(v3.store_path(cache))
    with v3._store(str(native)) as c:
        c.execute('INSERT INTO sv3_trades(variant,trade_date,ticker,status,prev_close,entry_price,shares,entry_at) VALUES(?,?,?,?,?,?,?,?)',
            ('SV3_PREOPEN','2026-11-04','AAA','OPEN',21.,20.,10,at('09:16:00').isoformat()))
    before=native.read_bytes();calls=[]
    async def quotes(_kite,names):calls.append(names);return {'AAA':quote()}
    monkeypatch.setattr(v3,'_quotes',quotes)
    await evidence.collect(object(),'MORNING',cache,now=at('09:30:00'))
    assert (await evidence.collect(object(),'MORNING',cache,now=at('09:30:10')))['status']=='repeat'
    assert calls==[['AAA']] and native.read_bytes()==before
    r=evidence.summary(cache)
    assert r['variants']['SV3_PREOPEN']['bid_complete']==1 and r['actual_fill']=='UNKNOWN'
    assert r['rows'][0]['entry_capacity_grade']=='UNKNOWN'


@pytest.mark.asyncio
async def test_before_continuous_volume_is_not_replaced_by_first_minute_volume(tmp_path,monkeypatch):
    monkeypatch.setattr(evidence,'enabled',lambda:True)
    cache=str(tmp_path/'cache.db');native=Path(v3.store_path(cache))
    with v3._store(str(native)) as c:
        c.execute('INSERT INTO sv3_trades(variant,trade_date,ticker,status,prev_close,limit_price) VALUES(?,?,?,?,?,?)',
            ('SV3_PREOPEN','2026-11-04','AAA','DECIDED',21.,20.))
    async def match_quotes(_kite,names):return {'AAA':quote('09:12:00',volume=50)}
    monkeypatch.setattr(v3,'_quotes',match_quotes)
    before=native.read_bytes();await evidence.collect(object(),'AUCTION',cache,now=at('09:12:00'))
    assert native.read_bytes()==before
    with v3._store(str(native)) as c:
        c.execute("UPDATE sv3_trades SET status='OPEN',entry_price=20,shares=10,plan_shares=10,capacity_volume=10000")
    async def bid_quotes(_kite,names):return {'AAA':quote()}
    monkeypatch.setattr(v3,'_quotes',bid_quotes)
    await evidence.collect(object(),'MORNING',cache,now=at('09:30:00'))
    r=evidence.summary(cache);morning=next(x for x in r['rows'] if x['phase']=='MORNING')
    assert morning['observed_auction_10pct_quantity']==5
    assert morning['entry_capacity_grade']=='EXCEEDS_PARTICIPATION_PROXY'
    auction=next(x for x in r['rows'] if x['phase']=='AUCTION')
    assert auction['quantity_not_frozen_before_matching'] is True


def test_previously_held_etf_is_still_settled_after_new_entry_exclusion(tmp_path):
    cache=str(tmp_path/'cache.db');path=v3.store_path(cache)
    with v3._store(path) as c:
        c.execute('INSERT INTO sv3_trades(variant,trade_date,ticker,status,prev_close,entry_price,shares,open_price) VALUES(?,?,?,?,?,?,?,?)',
            ('SV3_REF','2026-11-03','METAL','OPEN',21.,20.,10,20.))
        rows=[('SV3_REF','2026-11-03','METAL',20.,10,20.,None,None,None,None)]
        closed=v3._settle(c,rows,{'METAL':{'ohlc':{'close':21.,'open':21.2}}},'2026-11-04','2026-11-03')
        assert closed and c.execute("SELECT status FROM sv3_trades WHERE ticker='METAL'").fetchone()[0]=='CLOSED'


def test_summary_missing_and_damaged_store_is_read_only(tmp_path):
    cache=str(tmp_path/'cache.db');assert evidence.summary(cache)['status']=='not_collected'
    assert not list(tmp_path.iterdir())
    Path(evidence.store_path(cache)).write_bytes(b'broken')
    assert evidence.summary(cache)['status']=='unreadable_evidence'

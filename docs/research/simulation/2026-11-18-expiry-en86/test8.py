"""Round8 mechanics, causality and full historical control parity. No candidate P&L printed."""
from pathlib import Path
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
from datetime import datetime,timedelta
import concurrent.futures,copy,json,sqlite3,sys,tempfile,unittest
import numpy as np
import offline8
import data8,lab8,signals8,execution8,forward8,payoff8
L=lab8.L7
HERE=Path(__file__).resolve().parent

def synthetic():
    import check7
    t,_,_,_=check7._syn_tape()
    ks=[(25000+50*off,d) for off in range(-4,5) for d in (1,-1)]
    q=np.empty((375,len(ks),5));q[:,:,:4]=15.;q[:,:,4]=1e6
    out=L.D4._D().Tape(t.day,t.x.copy(),t.f.copy(),q,np.array([k for k,d in ks]),np.array([d for k,d in ks]),
                           [str(x) for x in ks],t.now,t.minute,0)
    out.und='NIFTY';out.oi8=np.full((375,len(ks)),100.);out.signals8={};out.picks8={}
    return out

class Mechanics(unittest.TestCase):
    def test_source_2027_and_zero(self):
        t=synthetic();t.day='2027-01-01'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'s.db'
            with sqlite3.connect(p) as c:
                c.execute('CREATE TABLE candles(kind,underlying,expiry,strike,opt,datetime,oi,interval)')
                c.execute('INSERT INTO candles VALUES(?,?,?,?,?,?,?,?)',('option','NIFTY',t.day,25000,'CE',t.day+' 13:00:00',0,'1minute'))
            c.close()
            a=data8.read_panel(t,data8.Source(p,True,'test'))
            j=list(zip(t.strikes,t.kinds)).index((25000,1));self.assertEqual(a[225,j],0)
            self.assertFalse(np.isfinite(data8.read_panel(t,data8.Source(p,False,'test'))).any())
    def test_oi_identity_and_missing(self):
        t=synthetic();i=230
        for c,p in data8.basket(t,i):t.oi8[i,c]=80;t.oi8[i,p]=130
        s,u,d,n=data8.components(t,i);self.assertEqual(n,5);self.assertAlmostEqual(s,u+d);self.assertGreater(u,0);self.assertGreater(d,0)
        t.oi8[i,:]=np.nan;self.assertTrue(np.isnan(data8.components(t,i)[0]))
    def test_crossing_is_not_repeated(self):
        self.assertEqual(signals8.crossing(np.array([0,2,2,0,-2]),1,np.ones(5,bool)).tolist(),[0,1,0,0,-1])
    def test_partial_liquidation_fees(self):
        t=synthetic();sp=L.L4.spec_of(t)
        calls=[]
        def exe(sp,t,i,j,side,sc,n):calls.append(n);return (1,9.)
        with patch.object(L.L6,'_exe',exe):r=execution8.liquidate(sp,t,5,0,2,10.)
        self.assertEqual(calls,[2,1]);self.assertEqual(r['remaining'],0)
        self.assertEqual(r['fees'],2*L.L4.fee(sp,9.,sp.lot,False));self.assertEqual(len(r['events']),2)
    def test_partial_unresolved_remainder(self):
        t=synthetic();sp=L.L4.spec_of(t)
        with patch.object(L.L6,'_exe',lambda sp,t,i,j,side,sc,n:(1,9.) if i==5 else (0,None)):
            r=execution8.liquidate(sp,t,5,0,2,10.)
        self.assertEqual(r['remaining'],1);self.assertEqual(r['assumed_net'],-10*sp.lot)
    def test_passive_one_unit_not_full_fill(self):
        import pk6
        epoch=1794871800
        raw=dict(recv=np.array([epoch,epoch+2],np.int64)*10**9,exch=np.array([epoch,epoch+2]),lt=np.array([epoch-60]*2),
                 ltp=np.array([10.1,10.1]),vol=np.array([100,100]),oi=np.array([0,0]),bp=np.full((2,5),9.9),
                 ap=np.full((2,5),10.1),bq=np.full((2,5),100),aq=np.full((2,5),100))
        raw['ap'][1,0]=9.95;raw['aq'][1,0]=1;b=pk6.Book(raw);s=float(b.s[0])
        for mode in ('STRICT_TRADE','QUOTE_OPPORTUNITY'):self.assertIsNone(execution8.passive_scenario(b,s,10,65,s+10,mode))
        raw['aq'][1,0]=65;b=pk6.Book(raw)
        self.assertEqual(execution8.passive_scenario(b,s,10,130,s+10,'QUOTE_OPPORTUNITY')['units'],65)
    def test_higher_sensitivity_affordability(self):
        t=synthetic();i=230;sp=L.L4.spec_of(t)
        pick=lab8.highest(sp,t,i,1,lab8.ARMS['EN92'],2500,30000)
        self.assertEqual(pick[1],1);self.assertLessEqual(L.L4.reserve(sp,pick[2],1),2500)
        self.assertEqual(t.strikes[pick[0]],min(t.strikes[t.kinds==1]))
        self.assertIsNone(lab8.highest(sp,t,i,1,lab8.ARMS['EN92'],100,30000))
    def test_pullback_reclaim_and_ceiling_source(self):
        t=synthetic();i=230;t.f[i:,3]=100;t.f[i+1,3]=98;t.f[i+1,1]=99;t.f[i+2,3]=100.5
        t.features[10][i,4]=2.
        raw=np.zeros(375,np.int8);raw[i]=1;S=np.ones(375)
        with patch.object(L.L4,'choose4',lambda *x:(0,1,20.)):
            a,p,logs=signals8.pullbacks(t,raw,S,.5)
        self.assertEqual(a[i+2],1);self.assertEqual(p[i+2]['event_i'],i)
        S[i+1]=-.2
        with patch.object(L.L4,'choose4',lambda *x:(0,1,20.)):
            a,_,_=signals8.pullbacks(t,raw,S,.5)
        self.assertFalse(a.any())
    def test_frozen_price_ceiling(self):
        t=synthetic();t.picks8[('PULL',230)]={'j':0,'ask0':10.,'event_i':228}
        self.assertIsNone(lab8.choose8(L.L4.NIFTY,t,230,1,lab8.ARMS['EN89'],2500,30000))
    def test_information_missing_resets(self):
        t=synthetic();p=dict(direction=1,entry_i=230,open=1);r=lab8.ARMS['EN94']
        with patch.object(L.L6,'decide6',lambda *x:(None,1)),patch.object(lab8,'components',side_effect=[(-1,0,0,5),(np.nan,0,0,0),(-1,0,0,5),(-1,0,0,5)]):
            self.assertIsNone(lab8.decide8(None,t,231,p,r,1,None)[0]);self.assertIsNone(lab8.decide8(None,t,232,p,r,1,None)[0])
            self.assertIsNone(lab8.decide8(None,t,233,p,r,1,None)[0]);self.assertEqual(lab8.decide8(None,t,234,p,r,1,None)[0],'OI_REVERSAL')
    def test_native_exit_precedes_info(self):
        t=synthetic();p=dict(direction=1,entry_i=230,open=1)
        with patch.object(L.L6,'decide6',lambda *x:('STOP',1)):
            self.assertEqual(lab8.decide8(None,t,231,p,lab8.ARMS['EN94'],1,None),('STOP',1))
    def test_ridge_known_signal(self):
        rng=np.random.default_rng(11);parts=[]
        for d in range(30):
            x=rng.normal(size=(20,3));parts.append((x,2*x[:,0]-x[:,1]+rng.normal(0,.01,20)))
        m=signals8.ridge_fit(parts);x=rng.normal(size=(100,3))
        self.assertGreater(np.corrcoef(signals8.predict(m,x),2*x[:,0]-x[:,1])[0,1],.999)
    def test_room_and_remainder_conservation(self):
        t=synthetic();sig=np.zeros(375,np.int8);sig[[230,260,290]]=1;t.signals8['RAW']=sig
        t.q[235:,:,0:4]=10.
        r=lab8.run_day8(t,lab8.ARMS['EN83'],details=True)
        self.assertLessEqual(r['intents'],2);self.assertGreaterEqual(r['net'],-2500.03)
        loss=0.
        for p in r['positions']:
            self.assertLessEqual(p['reserve'],2500-loss+.02);loss+=max(0,-p['net'])
            buys=sum(e['lots'] for e in p['events'] if e['side']=='BUY');sells=sum(e['lots'] for e in p['events'] if e['side']=='SELL')
            self.assertEqual(buys,sells+p['open'])
    def test_ledger_immutable_and_pending_retry(self):
        with tempfile.TemporaryDirectory() as d:
            l=forward8.Ledger(Path(d)/'f.db');key=('EN87','NIFTY','2026-01-01')
            l.record(key,'PENDING',{'missing':['OI']});self.assertEqual(l.rows(),[])
            self.assertTrue(l.claim(key,'a',100));self.assertFalse(l.claim(key,'b',101))
            self.assertEqual(l.record(key,'ELIGIBLE',{'net':0},'a'),'INSERTED')
            self.assertEqual(l.record(key,'ELIGIBLE',{'net':0}),'EXISTS')
            with self.assertRaises(ValueError):l.record(key,'ELIGIBLE',{'net':1})
    def test_lease_crash_expiry(self):
        with tempfile.TemporaryDirectory() as d:
            l=forward8.Ledger(Path(d)/'f.db');key=('EN87','NIFTY','2026-01-01')
            self.assertTrue(l.claim(key,'crashed',100,ttl=2));self.assertTrue(l.claim(key,'restart',103))
            l.record(key,'ELIGIBLE',{'net':0},'restart');self.assertFalse(l.claim(key,'c',200))
    def test_duplicate_workers(self):
        with tempfile.TemporaryDirectory() as d:
            l=forward8.Ledger(Path(d)/'f.db');key=('EN87','NIFTY','2026-01-01')
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                x=list(pool.map(lambda owner:l.claim(key,owner,100),['a','b']))
            self.assertEqual(sum(x),1)
    def test_deadline_and_dated_calendar(self):
        with tempfile.TemporaryDirectory() as d:
            l=forward8.Ledger(Path(d)/'f.db');key=('EN87','NIFTY','2026-01-01');close=datetime(2026,1,1,15,30,tzinfo=forward8.IST)
            cov=dict(eligible=False,missing=['future'])
            self.assertEqual(forward8.record_availability(l,key,cov,close+timedelta(hours=1),{}),'PENDING')
            self.assertEqual(forward8.record_availability(l,key,cov,close+timedelta(hours=49),{}),'MISSING')
            self.assertEqual(len(l.rows()),1)
            cal=dict(source='synthetic-test-only',verified_through='2026-01-01',sessions=[dict(underlying='NIFTY',day='2026-01-01')])
            self.assertEqual(len(forward8.due(cal,close,{'NIFTY':'2026-01-01'})),1)
            with self.assertRaises(ValueError):forward8.due({},close,{'NIFTY':'2026-01-01'})
    def test_sqlite_uncommitted_crash_is_recoverable(self):
        import subprocess
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'f.db';l=forward8.Ledger(path)
            code="import sqlite3,sys,os;c=sqlite3.connect(sys.argv[1]);c.execute('BEGIN IMMEDIATE');c.execute(\"INSERT INTO receipts VALUES('p','NIFTY','2027-01-01','ELIGIBLE','{}','x')\");os._exit(7)"
            r=subprocess.run([sys.executable,'-c',code,str(path)],capture_output=True)
            self.assertEqual(r.returncode,7);self.assertEqual(l.rows(),[])
    def test_coverage_does_not_sum_future_series(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'s.db';c=sqlite3.connect(path)
            c.execute('CREATE TABLE candles(kind,underlying,expiry,strike,opt,datetime,open,high,low,close,volume,oi,interval)')
            day='2027-01-01';rows=[]
            for i,m in enumerate(range(720,915)):
                stamp=day+f' {m//60:02d}:{m%60:02d}:00'
                rows.append(('index','NIFTY','',0,'',stamp,25000,25000,25000,25000,1000,0,'1minute'))
                expiry='2027-01-20' if i<90 else '2027-02-20'
                rows.append(('future','NIFTY',expiry,0,'',stamp,25000,25000,25000,25000,1000,0,'1minute'))
            c.executemany('INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',rows);c.commit();c.close()
            v=forward8.coverage(path,'NIFTY',day)
            self.assertFalse(v['eligible']);self.assertEqual(v['front'],'2027-01-20')
            self.assertTrue(any(isinstance(x,dict) and x.get('kind')=='future' for x in v['missing']))
    def test_24_minute_rule_changes_only_time(self):
        a=lab8.ARMS['EN83'];b=lab8.ARMS['EN91']
        from dataclasses import asdict
        x,y=asdict(a),asdict(b);self.assertEqual({k for k in x if x[k]!=y[k]},{'hold'});self.assertEqual(b.hold,24)
    def test_combination_is_fixed(self):
        a=lab8.ARMS['EN95'];self.assertEqual(a.setup8,'PULL_HIGH');self.assertEqual(a.selector8,'pullback_high')
        self.assertTrue(a.info_exit8);self.assertEqual(a.max_lots,1)
        self.assertFalse(a.patient);self.assertFalse(a.scout);self.assertEqual(a.hold,8)
    def test_group_test_reports_insufficient_short_sample(self):
        import stats8
        a=stats8.group_t(np.ones(20),np.ones(20));self.assertEqual(a['p'],1);self.assertIsNone(a['lo'])
    def test_replay_network_is_denied(self):
        import socket
        with self.assertRaises(PermissionError):socket.getaddrinfo('example.com',443)
    def test_latest_invalid_quote_does_not_resurrect_old_depth(self):
        import information8
        b=SimpleNamespace(s=np.array([100.,101.]),e=np.array([100.,101.]),
            a=dict(bp=np.array([[10.],[10.]]),ap=np.array([[10.1],[10.1]]),bq=np.array([[65],[65]]),aq=np.array([[65],[0]])))
        self.assertIsNotNone(information8.strict_at(b,100.5));self.assertIsNone(information8.strict_at(b,101.5))

def parity():
    B,bindings=data8.historical_books();checks=0
    for name in ('E03_env','E032_native','EN55_native'):
        for und,book in B.items():
            for scenario in ('ordinary','adverse','catastrophe'):
                for t in book:
                    r=lab8.ARMS[name];old=L.run_day7(t,r,scenario,30000.,L.budget_of(r),True)
                    new=lab8.run_day8(t,r,scenario,30000.,L.budget_of(r),True)
                    fields=('day','net','trades','fees','spent','unresolved','marked_worst','minutes_in','intents')
                    assert all(old[k]==new[k] for k in fields),(name,und,scenario,t.day)
                    assert [p['events'] for p in old['positions']]==[p['events'] for p in new['positions']]
                    checks+=1
    (HERE/'parity8.json').write_text(json.dumps(dict(checks=checks,bindings=bindings,status='PASS'),indent=2)+'\n')
    print('PARITY PASS',checks,'arm-days, all order events equal',flush=True)

def causal():
    B,_=data8.historical_books();book=B['NIFTY'];signals8.prepare(book);checks=0
    for n in range(30,len(book),20):
        t=book[n]
        for cut in (L.at(t,810),L.at(t,850)):
            u=L.D4._D().Tape(t.day,t.x.copy(),t.f.copy(),t.q.copy(),t.strikes.copy(),t.kinds.copy(),list(t.symbols),t.now,t.minute.copy(),0)
            u.und='NIFTY';u.oi8=t.oi8.copy()
            u.x[cut+1:]=np.nan;u.f[cut+1:]=np.nan;u.q[cut+1:]=np.nan;u.oi8[cut+1:]=np.nan
            prefix=book[max(0,n-30):n]
            signals8.prepare(prefix+[u])
            for key,a in u.signals8.items():
                assert np.array_equal(a[:cut+1],t.signals8[key][:cut+1]),(t.day,key,cut);checks+=1
            for key,v in u.picks8.items():
                if key[1]<=cut:assert v==t.picks8[key]
    (HERE/'causal8.json').write_text(json.dumps(dict(checks=checks,status='PASS'),indent=2)+'\n')
    print('CAUSAL PASS',checks,'signal prefixes and frozen picks',flush=True)

def model_causal():
    B,_=data8.historical_books();book=B['NIFTY'];signals8.prepare(book);full=payoff8.prepare(book)
    valid=[m for m in full['models'] if m['eligible']]
    for m in valid:
        assert max(m['train_dates'])<min(m['calibration_dates'])<m['day']
        assert max(m['calibration_dates'])<m['day']
    if not valid:
        raise AssertionError('no eligible model to exercise; need synthetic chronology test instead')
    target=valid[-1]['day'];n=next(i for i,t in enumerate(book) if t.day==target);t=book[n];cut=L.at(t,840)
    u=L.D4._D().Tape(t.day,t.x.copy(),t.f.copy(),t.q.copy(),t.strikes.copy(),t.kinds.copy(),list(t.symbols),t.now,t.minute.copy(),0)
    u.und='NIFTY';u.oi8=t.oi8.copy();u.x[cut+1:]=np.nan;u.f[cut+1:]=np.nan;u.q[cut+1:]=np.nan;u.oi8[cut+1:]=np.nan
    short=book[:n]+[u];signals8.prepare(short);again=payoff8.prepare(short)
    a={(r['i'],r['setup']):r for r in full['predictions'] if r['day']==target and r['i']<=cut}
    b={(r['i'],r['setup']):r for r in again['predictions'] if r['day']==target and r['i']<=cut}
    assert a.keys()==b.keys()
    for key in a:
        for field in ('forecast_return','conservative_return','selected'):
            assert a[key][field]==b[key][field],(target,key,field)
    assert full['models'][n]['parameters']==again['models'][n]['parameters']
    (HERE/'model-causal8.json').write_text(json.dumps(dict(status='PASS',eligible_model_dates=len(valid),target=target,forecast_checks=len(a),
        chronological_models=len(valid),note='actual later labels may change; forecasts, selection and parameters must not'),indent=2)+'\n')
    print('MODEL CAUSAL PASS',len(valid),'chronological models',len(a),'prefix forecasts',flush=True)

if __name__=='__main__':
    mode=sys.argv[1] if len(sys.argv)>1 else 'unit'
    if mode=='unit':
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Mechanics))
        (HERE/'unit8.json').write_text(json.dumps(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),status='PASS' if result.wasSuccessful() else 'FAIL'),indent=2)+'\n')
        sys.exit(0 if result.wasSuccessful() else 1)
    elif mode=='parity':parity()
    elif mode=='causal':causal()
    elif mode=='modelcausal':model_causal()
    else:raise ValueError(mode)

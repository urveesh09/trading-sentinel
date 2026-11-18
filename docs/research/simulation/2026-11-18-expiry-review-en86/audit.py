"""Focused independent round-7 checks; no scorer outputs or registrations changed."""
from pathlib import Path
from collections import defaultdict
from types import SimpleNamespace
import hashlib, json, sys, time
import numpy as np

HERE = Path(__file__).resolve().parent
ROUND = HERE.parent / '2026-11-18-expiry-en71'
sys.path.insert(0, str(ROUND))
import score7 as S
L, P, F = S.L7, S.P7, S.F7

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def partial_witness():
    original_pick, original_exe = L.L4.choose4, L.L6._exe
    t = SimpleNamespace(n=30, close=np.full(30, 100.), f=np.full((30, 5), 100.),
                        q=np.full((30, 1, 5), 10.), minute=np.arange(780, 810))
    L.L4.choose4 = lambda *args, **kw: (0, 2, 20.)
    calls = []
    def exe(sp, tape, i, j, side, scenario, lots):
        filled, price = (2, 10.) if side == 'BUY' else (1, 9.)
        calls.append(dict(side=side, requested=lots, filled=filled, price=price))
        return filled, price
    L.L6._exe = exe
    try:
        got = F.act(t, 0, 1)
    finally:
        L.L4.choose4, L.L6._exe = original_pick, original_exe
    assert calls[-1]['filled'] < calls[-1]['requested']
    assert got['lots'] == 2 and not got.get('unresolved')
    return dict(calls=calls, reported=got, unsold_lots=1,
                finding='frontier act prices all bought lots as sold after a partial exit')

def partial_population(book):
    """Inspect delay-zero canonical actions, not a corrected/re-tuned score."""
    partial = []; actions = 0; filled = 0
    for t in book:
        e03 = dict(F.e03_bars(t))
        inds = [(L.L6.at(t, m), 'grid') for m in F.GRID]
        inds += [(i, 'e03') for i in e03]
        for i, clock in inds:
            if i >= t.n or i + 1 + F.HOLD >= t.n:
                continue
            for d in (1, -1):
                actions += 1
                sp = L.L4.spec_of(t)
                pick = L.L4.choose4(sp, t, i, d, L.E03_ENV, 2500., 30000.)
                if not pick: continue
                j, lots, limit = pick
                b = i + 1
                n, px = L.L6._exe(sp, t, b, j, 'BUY', 'ordinary', lots)
                if not n or px is None or px > limit: continue
                filled += 1
                e0 = b + F.HOLD; ef = L.L6.at(t, 915)
                for k in range(min(e0, ef), t.n):
                    fs, p2 = L.L6._exe(sp, t, k, j, 'SELL', 'ordinary', n)
                    if fs:
                        if fs < n:
                            partial.append(dict(day=t.day, clock=clock, minute=int(t.minute[i]), side=d,
                                                bought=n, sold=fs, sale_bar=k, strike=float(t.strikes[j])))
                        break
    return dict(actions=actions, filled=filled, partial_exit_actions=len(partial), witnesses=partial[:12])

def main():
    started = time.time()
    r = json.loads((ROUND/'results7.json').read_text())
    a = json.loads((ROUND/'anatomy7.json').read_text())
    freeze = json.loads((ROUND/'freeze7.json').read_text())
    paths, _ = S._paths()
    hashes = {k: sha(p) == freeze['files'][k] for k,p in paths.items()}
    assert all(hashes.values()), hashes
    checked = 0
    for key, rows in a['days'].items():
        ref = r['arms'][key]['ordinary']
        v = [x['net'] for x in rows]
        top = sorted(v, reverse=True)+[0,0]
        vals = dict(net=round(sum(v),2), tickets=sum(x['trades'] for x in rows), sessions=len(rows),
                    traded_expiries=sum(x['trades']>0 for x in rows), worst=round(min(v),2),
                    without_top2=round(sum(v)-max(0,top[0])-max(0,top[1]),2))
        if all('fees' in x for x in rows):
            vals['fees']=round(sum(x['fees'] for x in rows),2)
        for k,vv in vals.items():
            assert abs(vv-ref[k])<.011,(key,k,vv,ref[k])
            checked += 1
        if key in a['tickets']:
            assert abs(sum(x['net'] for x in a['tickets'][key])-ref['net'])<.011,key
    out = dict(source_hashes=hashes, financial_checks=checked, day_views=len(a['days']),
               results_sha256=sha(ROUND/'results7.json'), anatomy_sha256=sha(ROUND/'anatomy7.json'),
               synthetic_partial_exit=partial_witness(), replays={}, partial_exits={}, signals={})
    print('hashes/accounting/synthetic witness checked', len(hashes),checked,flush=True)
    L.L5.install()
    B=L.L6.books()
    by=S.S6.daymap(B)
    controls={}
    for bk,book in B.items():
        for t in book: P.syn75(t)
        if bk=='NIFTY': P.oi83(book)
        for name in ('E03_env','EN75','EN83'):
            if name=='EN83' and bk!='NIFTY': continue
            for sc in ('ordinary','adverse'):
                rr=L.run_fixed7(book,L.ARMS[name],sc,details=(sc=='ordinary'))
                got=S.metrics(rr['days'])
                assert got==r['arms'][name+'|'+bk][sc],(name,bk,sc,got,r['arms'][name+'|'+bk][sc])
                if sc=='ordinary':
                    for x,y in zip(rr['days'],a['days'][name+'|'+bk]):
                        assert all(x[k]==y[k] for k in ('day','net','trades','fees','marked_worst','minutes_in'))
                out['replays'][name+'|'+bk+'|'+sc]=got
                print('reproduced',name,bk,sc,got['net'],flush=True)
        out['partial_exits'][bk]=partial_population(book)
        out['signals'][bk]={}
        for setup in (('SYNF75','OI83') if bk=='NIFTY' else ('SYNF75',)):
            events=[e for t in book for e in L.META7.get((setup,bk,t.day),[])]
            out['signals'][bk][setup]=dict(events=len(events))
        print('partial population',bk,out['partial_exits'][bk],flush=True)
        if bk=='NIFTY':
            for ctl in ('EN75_fut_ctl','EN83_px_ctl'):
                rr=L.run_fixed7(book,L.ARMS[ctl],'ordinary',details=True)
                assert S.metrics(rr['days'])==r['arms'][ctl+'|'+bk]['ordinary']
                controls[ctl]=S.S6.tickets(rr['days'],by)
    # Compare signal decisions to price controls at the actual filled parent clocks.
    for name, ctl in (('EN75','EN75_fut_ctl'),('EN83','EN83_px_ctl')):
        xs=a['tickets'][name+'|NIFTY']; ys=controls[ctl]
        kk=lambda x:(x['day'],x['minute'])
        xm={kk(x):x for x in xs}; ym={kk(x):x for x in ys}
        common=xm.keys() & ym.keys()
        out.setdefault('filled_clock_controls',{})[name]=dict(candidate=len(xs), control=len(ys),
            shared_clock=len(common), candidate_only=len(xm.keys()-ym.keys()), control_only=len(ym.keys()-xm.keys()))
    # Exact binomial interval for 1 rejection in 20 (Clopper-Pearson).
    from scipy.stats import beta
    out['calibration_1_of_20_interval_95']=[float(beta.ppf(.025,1,20)),float(beta.ppf(.975,2,19))]
    out['harness_published']=r['harness']
    import sqlite3
    for label,path in [('sealed_2026',P.SEALED['2026']),('forward_history',S.fut7.DB)]:
        c=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
        row=c.execute("SELECT count(*), max(datetime) FROM candles WHERE kind='option' AND underlying='NIFTY' AND expiry='2026-11-17' AND oi>0").fetchone()
        c.close()
        out.setdefault('forward_oi_source_check',{})[label]=dict(rows=row[0],max_datetime=row[1],path=str(path))
    out['elapsed_seconds']=round(time.time()-started,2)
    (HERE/'verification.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
    print('FOCUSED AUDIT PASS',out['elapsed_seconds'],flush=True)

if __name__=='__main__': main()

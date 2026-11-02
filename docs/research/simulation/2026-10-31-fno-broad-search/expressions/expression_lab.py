"""O31i-E matched expression diagnostics; exact research binding, no orders."""
from __future__ import annotations

import argparse,hashlib,json,re,sqlite3,subprocess,sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict,Counter

HERE=Path(__file__).resolve().parent
PARENT=HERE.parent
ROOT=next(p for p in HERE.parents if (p/'python-engine/fno_policy_replay.py').is_file())
sys.path[:0]=[str(PARENT),str(ROOT/'python-engine')]
import lab_broad as B
import spread_pairs as V
from fno_costs import calc_fno_costs


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def spec():
    return [{'kind':'SAME_DIRECTION_CREDIT','width':w,'offset':None} for w in (50,100,150)]+[
        {'kind':'NEUTRAL_IRON','width':w,'offset':o} for w in (50,100) for o in (0,50,100)]


def validate_parent(trades,file_hash,evidence):
    assert file_hash==evidence['file_sha256'] and len(trades)==len(evidence['record_sha256']),'parent control changed'
    for i,t in enumerate(trades):
        assert hashlib.sha256(json.dumps(t,sort_keys=True).encode()).hexdigest()==evidence['record_sha256'][i], 'parent economic mismatch'


def combine_credits(call,put,width,extra):
    """Join two bounded credit verticals; their ranges cannot overlap here."""
    if call['status']!='AVAILABLE' or put['status']!='AVAILABLE':
        return {'status':'UNAVAILABLE','reason':'call_'+call.get('reason','ok')+'|put_'+put.get('reason','ok')}
    credit=call['entry_cashflow']+put['entry_cashflow']
    if not 0<credit<width*65:return {'status':'UNAVAILABLE','reason':'incoherent_iron_credit'}
    # Constituents priced with extra=0; charge the full structure stress ONCE.
    gross=call['gross']+put['gross'];fees=call['fees']+put['fees']
    risk=width*65-credit+400+extra
    reserve=2*width*65+400+extra
    return {'status':'AVAILABLE','net':gross-fees-extra,'gross':gross,'fees':fees,'extra':extra,
            'entry_cashflow':credit,'planned_risk':risk,'reserved_own_cash':reserve,
            'cash_feasible':reserve<=250000,'risk_compatible':risk<=5000}


def freeze():
    parent=json.loads((PARENT/'freeze.json').read_text())
    data={y:{k:v for k,v in b.items() if k in ('dataset','manifest','data','daily','settings')} for y,b in parent['bindings'].items()}
    B.Y.write_new(HERE/'freeze.json',{'schema':'o31i_expression_v1','parent_freeze':sha(PARENT/'freeze.json'),
        'sources':{p.relative_to(ROOT).as_posix():sha(p) for p in [HERE/'expression_lab.py',HERE/'test_expression.py',HERE/'PLAN.md',PARENT/'spread_pairs.py']},
        'specs':spec(),'extra_costs':[200.,400.],'data':data,'mode':'MATCHED_DIAGNOSTIC_NOT_LIFECYCLE','qualified':False,'can_place_orders':False})


def main():
    B.O27F.deny_network();f=json.loads((HERE/'freeze.json').read_text())
    assert f['parent_freeze']==sha(PARENT/'freeze.json')
    assert all(sha(ROOT/p)==h for p,h in f['sources'].items())
    rel=(HERE/'freeze.json').relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(['git','show','HEAD:'+rel],cwd=ROOT))==f
    manifest=json.loads((HERE/'parent-evidence.json').read_text())
    rel=(HERE/'parent-evidence.json').relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(['git','show','HEAD:'+rel],cwd=ROOT))==manifest,'parent economics not committed'
    all_rows=[];repriced=0
    for year in ('2024','2025','2026'):
        db=ROOT/f['data'][year]['dataset']/'breeze.sqlite'
        assert sha(db)==f['data'][year]['data']['breeze.sqlite']
        con=sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True);cache={}
        def quote(exp,k,opt,stamp):
            key=(exp,k,opt,stamp)
            if key not in cache:
                row=con.execute("SELECT close,volume FROM candles WHERE kind='option' AND expiry=? AND strike=? AND opt=? AND datetime=?",key).fetchone()
                if row:
                    bid,ask=B.Y.yeardata.bid_ask(float(row[0]));cache[key]={'close':float(row[0]),'bid':bid,'ask':ask,'volume':float(row[1] or 0)}
                else:cache[key]=None
            return cache[key]
        keys=json.loads((PARENT/f'_local/keys-screen-{year}.json').read_text())
        for control in ('RAW|MAIN','RAW|E|tpb_puts'):
            file=PARENT/'_local/evals'/f'{keys[control]}.json';trades=json.loads(file.read_text())['trades'];parent_sha=sha(file)
            evidence=manifest['controls'][year][control]
            validate_parent(trades,parent_sha,evidence)
            for index,t in enumerate(trades):
                assert hashlib.sha256(json.dumps(t,sort_keys=True).encode()).hexdigest()==evidence['record_sha256'][index], 'parent economic mismatch'
                assert t.get('net_pnl') is not None and t['entry_qty']==65 and t['lots_at_exit']==1 and not t.get('adds')
                m=re.fullmatch(r'NIFTY(\d{6})(\d+)(CE|PE)',t['tradingsymbol']);assert m
                exp=datetime.strptime(m[1],'%y%m%d').date().isoformat();k=int(m[2]);opt=m[3]
                assert opt==('CE' if t['direction']=='LONG' else 'PE'),'signal/option direction mismatch'
                e=datetime.fromisoformat(t['entry_time']).strftime('%Y-%m-%d %H:%M:00');x=datetime.fromisoformat(t['exit_time']).strftime('%Y-%m-%d %H:%M:00')
                orig_e,orig_x=quote(exp,k,opt,e),quote(exp,k,opt,x)
                base_ok=all(q is not None and q['volume']>0 for q in (orig_e,orig_x))
                if base_ok:
                    assert abs(orig_e['ask']-t['entry_premium'])<.001 and abs(orig_x['bid']-t['exit_premium'])<.001
                    base=(orig_x['bid']-orig_e['ask'])*65-calc_fno_costs(orig_e['ask'],orig_x['bid'],65)
                    assert abs(base-t['net_pnl'])<.011;repriced+=1
                binding={n:t.get(n) for n in ('tradingsymbol','entry_time','exit_time','entry_qty','entry_premium','exit_premium','entry_underlying','stop_underlying','bar_ts','member')}
                binding.update(parent_eval_sha256=parent_sha,parent_record_index=index)
                identity=hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()
                for s in f['specs']:
                    for extra in f['extra_costs']:
                        if not base_ok:r={'status':'UNAVAILABLE','reason':'original_common_cohort_unavailable'}
                        elif s['kind']=='SAME_DIRECTION_CREDIT':
                            cp='PE' if t['direction']=='LONG' else 'CE';wing=k+(-s['width'] if cp=='PE' else s['width'])
                            r=V.vertical(quote(exp,k,cp,e),quote(exp,k,cp,x),quote(exp,wing,cp,e),quote(exp,wing,cp,x),s['width'],'INVERSE_CREDIT',extra)
                        else:
                            center=round(t['entry_underlying']/50)*50;ce=center+s['offset'];pe=center-s['offset'];w=s['width']
                            call=V.vertical(quote(exp,ce,'CE',e),quote(exp,ce,'CE',x),quote(exp,ce+w,'CE',e),quote(exp,ce+w,'CE',x),w,'INVERSE_CREDIT',0.)
                            put=V.vertical(quote(exp,pe,'PE',e),quote(exp,pe,'PE',x),quote(exp,pe-w,'PE',e),quote(exp,pe-w,'PE',x),w,'INVERSE_CREDIT',0.)
                            r=combine_credits(call,put,w,extra)
                        if r['status']=='AVAILABLE':
                            r['same_clock_single_net']=base-extra;r['delta_vs_single']=r['net']-r['same_clock_single_net']
                        member=('SHIPPED','OR20','EFF','TPB')[t['member']] if control=='RAW|MAIN' else 'TPB_CLOSED'
                        r.update(year=year,day=t['entry_time'][:10],direction=t['direction'],control=control,member=member,
                                 spec=s,extra=extra,trade_identity=identity,immutable_parent=binding)
                        all_rows.append(r)
        con.close()
    summary={}
    for control in ('RAW|MAIN','RAW|E|tpb_puts'):
        for direction in ('LONG','SHORT'):
            for s in f['specs']:
                for extra in f['extra_costs']:
                    part=[r for r in all_rows if r['control']==control and r['direction']==direction and r['spec']==s and r['extra']==extra]
                    if not part:continue
                    name=f"{control}|{direction}|{s['kind']}|w{s['width']}|o{s['offset']}|{int(extra)}"
                    summary[name]={y:V.summarize([r for r in part if r['year']==y]) for y in ('2024','2025','2026')}
    leads=[]
    for n,ys in summary.items():
        if not n.endswith('|400'):continue
        ps=[ys[y]['entry_risk_compatible_subset'] for y in ('2024','2025','2026')]
        ok=all(ys[y]['requested']>0 and ys[y]['entry_risk_compatible_subset']['trades']/ys[y]['requested']>=.95 for y in ('2024','2025','2026'))
        if ok and min(p['trades'] for p in ps)>=12 and sum(p['trades'] for p in ps)>=40 and all(p['net'] is not None and p['net']>0 and p['without_best_day']>0 and p['delta']>0 for p in ps):leads.append(n)
    members={}
    for member in ('SHIPPED','OR20','EFF','TPB','TPB_CLOSED'):
        members[member]={}
        for s in f['specs']:
            part=[r for r in all_rows if r['member']==member and r['spec']==s and r['extra']==400]
            if part:members[member][json.dumps(s,sort_keys=True)]={y:V.summarize([r for r in part if r['year']==y]) for y in ('2024','2025','2026')}
    B.P.write(HERE/'results.json',{'schema':'o31i_expression_results_v1','summary':summary,'member_slices_exploratory':members,
          'exploratory_leads':leads,'original_repricing_parity':repriced,'bound_parent_identities':len({r['trade_identity'] for r in all_rows}),
          'scope':'MATCHED_EXPRESSION_NOT_LIFECYCLE_OR_PORTFOLIO','qualified':False,'can_place_orders':False})
    B.P.write(PARENT/'_local/expression-bound-rows.json',all_rows)
    print('Same-direction/neutral expressions',len(summary),'cells; exact parent identities',len({r['trade_identity'] for r in all_rows}),'leads',leads,flush=True)


if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('action',choices=['freeze','run']);args=a.parse_args()
    freeze() if args.action=='freeze' else main()

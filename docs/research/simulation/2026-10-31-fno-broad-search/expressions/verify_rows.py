"""Post-run economic rebinding/repricing; original rows remain intact."""
import hashlib,json,re,sqlite3,sys
from datetime import datetime
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];ROOT=next(p for p in HERE.parents if (p/'python-engine').is_dir())
sys.path[:0]=[str(HERE),str(HERE/'expressions')]
import lab_broad as B
import spread_pairs as V
import expression_lab as E

load=lambda p:json.loads(p.read_text())
manifest=load(HERE/'expressions/parent-evidence.json');original=load(HERE/'_local/spread-pairs.json')
bound=[];position=0;parents=0
freeze=load(HERE/'freeze.json')
for year in ('2024','2025','2026'):
    path=ROOT/freeze['bindings'][year]['dataset']/'breeze.sqlite'
    assert E.sha(path)==freeze['bindings'][year]['data']['breeze.sqlite']
    con=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True);cache={}
    def quote(exp,k,opt,stamp):
        key=(exp,k,opt,stamp)
        if key not in cache:
            row=con.execute("SELECT close,volume FROM candles WHERE kind='option' AND expiry=? AND strike=? AND opt=? AND datetime=?",key).fetchone()
            if row:
                bid,ask=B.Y.yeardata.bid_ask(float(row[0]));cache[key]={'close':float(row[0]),'volume':float(row[1] or 0),'bid':bid,'ask':ask}
            else:cache[key]=None
        return cache[key]
    keys=load(HERE/f'_local/keys-screen-{year}.json')
    for control in ('RAW|MAIN','RAW|E|tpb_puts'):
        path=HERE/'_local/evals'/f'{keys[control]}.json';file_sha=E.sha(path);trades=load(path)['trades']
        E.validate_parent(trades,file_sha,manifest['controls'][year][control])
        for index,t in enumerate(trades):
            parents+=1;m=re.fullmatch(r'NIFTY(\d{6})(\d+)(CE|PE)',t['tradingsymbol']);assert m
            expiry=datetime.strptime(m[1],'%y%m%d').date().isoformat();strike=int(m[2]);opt=m[3]
            assert opt==('CE' if t['direction']=='LONG' else 'PE') and t['entry_qty']==65
            e=datetime.fromisoformat(t['entry_time']).strftime('%Y-%m-%d %H:%M:00');x=datetime.fromisoformat(t['exit_time']).strftime('%Y-%m-%d %H:%M:00')
            binding={k:t.get(k) for k in ('tradingsymbol','entry_time','exit_time','entry_qty','entry_premium','exit_premium','entry_underlying','stop_underlying','bar_ts','member')}
            binding.update(parent_eval_sha256=file_sha,parent_record_index=index)
            identity=hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()
            for width in V.WIDTHS:
                wing=strike+(width if opt=='CE' else -width)
                for mode in ('DEBIT','INVERSE_CREDIT'):
                    for extra in V.COSTS:
                        r=V.vertical(quote(expiry,strike,opt,e),quote(expiry,strike,opt,x),quote(expiry,wing,opt,e),quote(expiry,wing,opt,x),width,mode,extra)
                        r.update(year=year,day=t['entry_time'][:10],control=control,direction=t['direction'],width=width,mode=mode,extra=extra)
                        assert original[position]==r,('reprice mismatch',year,control,index,width,mode,extra)
                        if r['status']=='AVAILABLE':
                            assert abs(r['gross']-r['fees']-r['extra']-r['net'])<1e-8
                            assert abs(r['net']-r['same_clock_single_net']-r['delta_vs_single'])<1e-8
                            assert r['reserved_own_cash']==width*65+200+extra
                        bound.append({**r,'trade_identity':identity,'immutable_parent':binding});position+=1
        assert E.sha(path)==file_sha,'parent mutated during pricing'
    con.close()
assert position==len(original)==parents*12
B.P.write(HERE/'_local/spread-pairs-bound.json',bound)
other=load(HERE/'_local/expression-bound-rows.json')
assert len(other)==parents*18
for r in other:
    b=r['immutable_parent'];assert hashlib.sha256(json.dumps(b,sort_keys=True).encode()).hexdigest()==r['trade_identity']
    if r['status']=='AVAILABLE':
        assert abs(r['gross']-r['fees']-r['extra']-r['net'])<1e-8
        assert abs(r['net']-r['same_clock_single_net']-r['delta_vs_single'])<1e-8
        s=r['spec'];assert r['reserved_own_cash']==(2 if s['kind']=='NEUTRAL_IRON' else 1)*s['width']*65+(400 if s['kind']=='NEUTRAL_IRON' else 200)+r['extra']
out={'parent_records':parents,'original_rows_bound_and_repriced':position,'extension_bound_rows':len(other),'financial_identity_failures':0,'parent_economics_mismatches':0,
     'raw_bound_hashes':{p.name:E.sha(p) for p in (HERE/'_local/spread-pairs-bound.json',HERE/'_local/expression-bound-rows.json')},
     'stored_stop_limitation':'closing/trailing stop only, not immutable initial risk evidence','diagnostic_not_lifecycle':True}
B.P.write(HERE/'expression-crosschecks.json',out);print(json.dumps(out))

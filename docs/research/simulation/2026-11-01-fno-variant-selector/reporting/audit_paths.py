"""Verify actual archived prices, admissions, retests and first exit observations."""
import importlib.util,json,sys
from collections import Counter
from datetime import date
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import variant_lab as L
spec=importlib.util.spec_from_file_location('n05_independent_paths',L.PARENT/'reporting/audit_paths.py');V=importlib.util.module_from_spec(spec);spec.loader.exec_module(V)


def run():
    L.B.O27F.deny_network();L.verify('candidate');L.B.L._init();y=L.B.YEAR;data=L.Y.dataset('year');table=L.C.table('year');days={};frames={};counts=Counter();hashes={}
    decisions=json.loads((L.LOCAL/f'decisions-{y}.json').read_text())
    for phase in ('reference','candidate'):
        for name,key in json.loads((L.LOCAL/f'keys-{phase}-{y}.json').read_text()).items():
            file=L.LOCAL/'evals'/f'{key}.json';obj=json.loads(file.read_text());trace=json.loads((L.LOCAL/'traces'/f'{key}.json').read_text());accepted=[r for r in trace['decisions'] if r['outcome']=='accepted']
            assert len(accepted)==len(obj['trades']);hashes[file.relative_to(L.ROOT).as_posix()]=L.B.P.sha(file)
            for t in obj['trades']:
                day=t['entry_time'][:10];d=date.fromisoformat(day)
                if day not in days:days[day]=data.observations(day)[0];frames[day]=data.futures_frame(data.future_contract(data.front_expiry(d)).token,d)
                frame=frames[day];packets={o.at.isoformat():o for o in days[day]}
                a=packets[t['entry_time']];b=packets[t['exit_time']]
                es=[q for q in a.options.values() if q.contract.tradingsymbol==t['tradingsymbol']];xs=[q for q in b.options.values() if q.contract.tradingsymbol==t['tradingsymbol']]
                assert len(es)==len(xs)==1 and abs(es[0].ask-t['entry_premium'])<.001 and abs((xs[0].bid if xs[0].bid>0 else xs[0].ltp)-t['exit_premium'])<.001
                matches=[r for r in accepted if r['at']==t['entry_time'] and r['bar_ts']==t['bar_ts'] and r['entry_expert']==t['entry_expert']]
                assert len(matches)==1 and matches[0]['n06_variant']==t['n06_variant'] and matches[0]['n06_decision']==t['n06_decision']
                assert L.Y.ROUTER.allowed(t['entry_gate'],table[day])
                v=t['n06_variant'];assert t['selected_profile']==('MAIN' if v=='MAIN' else 'TPB_ONE')
                if phase=='candidate':assert t['n06_decision']==decisions[name][day]
                if t['entry_expert']=='EFF' and v!='MAIN':V.V4.V.check_retest(t,frame,data);counts['retest_paths']+=1
                if t['entry_expert']=='EFF' and v in ('STRUCT30','STALL30'):
                    looks,structures=V.exit_path(t,frame,days[day]);counts['exit_lifecycles']+=1;counts['management_observations']+=looks;counts['structure_reviews']+=structures
                counts['admissions_and_trace_bindings']+=1;counts['archive_prices']+=2
    L.verify('candidate');out=dict(year=y,counts=dict(counts),path_or_price_or_admission_errors=0,file_sha256=hashes);L.X.write(L.LOCAL/f'path-check-{y}.json',out);print('PATHS_VERIFIED',y,dict(counts),flush=True)


if __name__=='__main__':run()

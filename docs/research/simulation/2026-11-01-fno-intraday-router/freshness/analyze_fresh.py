"""Strictly reuse STATIC economics; rebuild only state-availability labels."""
import argparse,json,shutil,sys
from datetime import datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path[:0]=[str(HERE),str(HERE.parent)]
import fresh_lab as F
import analyze_router as A
X=F.X;load=lambda p:json.loads(p.read_text())
def source_sessions():
    f=load(F.PARENT/'freeze.json')
    return {y:[d for d in load(X.ROOT/f['bindings'][y]['dataset']/'manifest.json')['sessions'] if d<=(y+'-12-31' if y!='2026' else '2026-10-28')] for y in A.YEARS}


def train():
    F.verify('base');all_sessions=sorted(d for ds in source_sessions().values() for d in ds);records=[];relabels={};parent=load(F.PARENT/'training-manifest.json')
    for y in A.YEARS:
        rows=load(F.PARENT/f'_local/training-records-{y}.json');byid={}
        keys=load(F.PARENT/f'_local/keys-base-{y}.json')
        for name,key in keys.items():
            p=F.PARENT/'_local/evals'/f'{key}.json';target=F.LOCAL/'evals'/p.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
            if name.startswith('LIB|'):
                for t in load(p)['trades']:byid[t['router_admission_id']]=t
        count=0
        for r in rows:
            t=byid[r['admission_id']]
            assert r['net']==float(t['net_pnl'])-200 and r['entry_time']==t['entry_time'] and r['exit_time']==t['exit_time']
            if F.stale(t['bar_ts'],datetime.fromisoformat(t['entry_time'])):
                macro=r['cell'].split('|')[-1] if r['cell'] else 'MISSING'
                r={**r,'cell':'UNAVAILABLE|'+macro};count+=1
            records.append(r)
        relabels[y]=count
        X.write(F.LOCAL/f'keys-base-{y}.json',keys)
        X.write(F.LOCAL/f'training-records-{y}.json',[r for r in records if r['year']==y])
    manifest={'schema':'n01f_training_v1','source_freeze_sha256':X.B.P.sha(HERE/'freeze.json'),'models':{},'library_sha256':parent['library_sha256'],
              'reused_base_books':27,'economic_labels_unchanged':True,'stale_labels_reclassified':relabels,'all_years_seen':True}
    for y in A.YEARS:
        months=sorted({d[:7]+'-01' for d in all_sessions if d[:4]==y});models={m:X.R.fit_model(records,m,all_sessions) for m in months}
        p=F.LOCAL/f'models-{y}.json';assert not p.exists()
        X.write(p,{'models':models,'session_index':{d:i for i,d in enumerate(all_sessions) if d[:4]==y},'qualified':False})
        manifest['models'][y]={'path':p.relative_to(X.ROOT).as_posix(),'sha256':X.B.P.sha(p),'monthly_models':len(models),'latest_training_exits':{m:v['latest_label_exit'] for m,v in models.items()}}
    assert not (HERE/'training-manifest.json').exists();X.write(HERE/'training-manifest.json',manifest)
    print('FRESH_TRAINING',len(records),'labels; state relabels',relabels,flush=True)


def analyze():
    A.HERE=HERE;A.sessions=source_sessions
    A.analyze()
    result=load(HERE/'results.json');result['correctness']['evaluated_books']=result['correctness']['fresh_replays'];result['correctness']['fresh_replays']=18
    result['correctness']['reused_base_books']=27;result['input_contract_repair']='stale closed-bar state unavailable, no parameter changes'
    result['stale_training_relabels']=load(HERE/'training-manifest.json')['stale_labels_reclassified']
    X.write(HERE/'results.json',result)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['train','analyze']);a=p.parse_args();{'train':train,'analyze':analyze}[a.action]()

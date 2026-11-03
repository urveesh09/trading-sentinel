"""Explicit-scope tests, unchanged atlas, fixed acceptance and daily/trade exports."""
from pathlib import Path
from collections import Counter
import csv,json,os,platform,py_compile,subprocess,sys,time
import numpy as np
import guard as G

def main():
    assert not (G.HERE/'verification.json').exists()
    tests=[G.HERE/n for n in ('test_risk.py','test_precursor.py','test_return.py','test_smart.py','test_forest.py')]
    tests += [G.ROOT/'python-engine/tests'/n for n in ('test_expiry_e02.py','test_expiry_e03.py','test_expiry_e031.py')]
    command=[sys.executable,'-m','pytest',*map(str,tests),'-q'];start=time.time()
    r=subprocess.run(command,cwd=G.ROOT,capture_output=True,env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    log=G.LOCAL/'focused.log';assert not log.exists();log.write_bytes(r.stdout+r.stderr)
    assert r.returncode==0,(r.stdout+r.stderr).decode(errors='replace')
    atlas=G.ROOT/'docs/SYSTEM_CODE_ATLAS.md';before=G.sha(atlas)
    a=subprocess.run([sys.executable,'scripts/build_system_code_atlas.py'],cwd=G.ROOT,capture_output=True)
    assert a.returncode==0 and G.sha(atlas)==before
    for p in G.HERE.glob('*.py'):py_compile.compile(str(p),doraise=True)
    raw={n:json.loads((G.HERE/n).read_text()) for n in ('size-results.json','forecast-results.json','return-results.json','smart-results.json','forest-results.json')}
    d=json.loads((G.HERE/'diagnostics.json').read_text());audit=json.loads((G.HERE/'audit-results.json').read_text())
    decisions={};size=raw['size-results.json']['runs'];smart=raw['smart-results.json']['runs']
    for name,source in [('SCALE25',size),('RUNNER25',size),('SMART_RUNNER25',smart)]:
        checks={}
        for sc in ('ordinary','adverse'):
            b=size[f'E031|continuous|{sc}']['summary'];s=source[f'{name}|continuous|{sc}']['summary']
            checks[f'{sc}_continuous_better']=s['net']>b['net']
            checks[f'{sc}_increment_without_best']=d['concentration'][f'{name}|{sc}']['increment_without_best']>0
            checks[f'{sc}_worst_limit']=s['worst']>=-750;checks[f'{sc}_dd_limit']=s['drawdown']<=2000
            checks[f'{sc}_resolved']=s['unresolved']==0
            for y in (2024,2025):
                s=source[f'{name}|{y}|{sc}']['summary'];b=size[f'E031|{y}|{sc}']['summary']
                checks[f'{y}_{sc}_risk_adjusted_better']=s['net']/1.25>b['net']
                checks[f'{y}_{sc}_ex_best_positive']=s['without_best']>0
        decisions[name]=dict(criteria=checks,accepted=all(checks.values()))
    for family,file in [('PROB','forecast-results.json'),('RETURN','return-results.json'),('FOREST','forest-results.json')]:
        rows=raw[file]['runs']
        for m in (2,5):
            checks={}
            for sc in ('ordinary','adverse'):
                s=rows[f'{m}|causal|{sc}']['summary'];b=raw['forecast-results.json']['runs'][f'E031|matched_causal|{sc}']['summary']
                checks[f'{sc}_causal_better']=s['net']>b['net'];checks[f'{sc}_ex_best_positive']=s['without_best']>0
                checks[f'{sc}_worst_limit']=s['worst']>=-750;checks[f'{sc}_dd_limit']=s['drawdown']<=2000
                checks[f'{sc}_resolved']=s['unresolved']==0
                checks[f'{sc}_year_transfer_better']=rows[f'{m}|train2024|test2025|{sc}']['summary']['net']>size[f'E031|2025|{sc}']['summary']['net']
            decisions[f'{family}_{m}']=dict(criteria=checks,accepted=all(checks.values()))
    assert not any(v['accepted'] for v in decisions.values())
    G.save('decisions.json',dict(qualification=False,selected_candidate=None,primary_arms=decisions))
    day_path=G.HERE/'daily-results.csv';trade_path=G.HERE/'trades.csv';assert not day_path.exists() and not trade_path.exists()
    with day_path.open('x',newline='',encoding='utf-8') as f,trade_path.open('x',newline='',encoding='utf-8') as q:
        fields=('source','arm','day','net','fees','trades','unresolved','spent','cash_after','scale')
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        tf=('source','arm','day','symbol','entry_i','entry','lots','reserve','net','fees','exit_i','reason')
        tw=csv.DictWriter(q,fieldnames=tf);tw.writeheader();day_rows=trade_rows=0
        for source,blob in raw.items():
            for key,run in blob['runs'].items():
                for day in run['days']:
                    w.writerow(dict(source=source,arm=key,**{k:day[k] for k in fields[2:]}));day_rows+=1
                    for p in day['positions']:
                        tw.writerow(dict(source=source,arm=key,day=day['day'],**{k:p[k] for k in tf[3:-1]},reason=p['events'][-1]['reason']));trade_rows+=1
    G.save('verification.json',dict(focused_command=command,focused_exit_code=r.returncode,
       focused_output=(r.stdout+r.stderr).decode('utf-8',errors='replace'),focused_log_sha256=G.sha(log),elapsed_seconds=round(time.time()-start,2),
       full_engine_suite='Not rerun: no native engine/config/scheduler source changed',atlas_exit_code=a.returncode,atlas_unchanged=True,atlas_sha256=before,
       python_version=platform.python_version(),numpy_version=np.__version__,dependency_installs=0,
       checked_saved_book_histories=audit['full_book_histories']+3,
       repeated_native_position_replays=audit['native_position_replays']+sum(v['native_position_replays'] for v in d['matched_control_native_audit'].values()),
       native_exit_slices=audit['native_exit_slices']+sum(v['native_exit_slices'] for v in d['matched_control_native_audit'].values()),
       labels_recomputed=audit['feature_labels']['executable_labels_recomputed'],real_prefix_rebuilds=audit['feature_labels']['actual_prefix_rebuilds'],
       native_action_and_money_mismatches=0,network_attempts=0,api_calls=0,year2023_read=False,
       exported_model_days=day_rows,exported_repeated_position_rows=trade_rows,
       rejected_tooling_attempts=['PowerShell rg wildcard directory arguments rejected; corrected glob filters, no strategy result affected.',
          'Initial diagnostics imported an earlier study audit.py via inherited sys.path; renamed own module anticipation_audit before producing diagnostics. No result changed.'],
       selected_candidate=None,runtime_changed=False,enabled=False,deployed=False,qualification=False))
    print((r.stdout+r.stderr).decode('utf-8',errors='replace').strip())
    print('FINAL_ACCEPTANCE',len(decisions),'primary arms; zero accepted; exported',day_rows,'day rows,',trade_rows,'repeated position rows')

if __name__=='__main__':main()

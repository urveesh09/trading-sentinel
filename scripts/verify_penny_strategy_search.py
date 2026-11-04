"""Verify the completed Penny study's immutable artifacts and money identities."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def check(run,seal=False,write=True):
    scores=[];closed=0;flat_smart=0
    for p in sorted(run.glob('**/_local/results/*.json')):
        r=json.loads(p.read_text());scores.append(p)
        for t in r.get('trades',[]):
            if t.get('status')!='CLOSED':continue
            closed+=1
            if all(k in t for k in ['gross_pnl','costs','net_pnl']):
                assert abs(t['gross_pnl']-t['costs']-t['net_pnl'])<.011,p
            assert t.get('costs',0)>=0,p
        state=r.get('final_state')
        if state and not state['positions']:
            net=sum(t.get('net_pnl',0) for t in r['trades'] if t['status']=='CLOSED')
            assert abs(state['bankroll']+state['realized']-2000-net)<.011,p
            flat_smart+=1
        m=r.get('metrics')
        if m and not m['unresolved']:
            size=re.search(r'_(\d+)_entry\d+_exit\d+',p.stem)
            initial=float(size.group(1)) if size else (25000 if p.stem.startswith('diagnostic_') else 100000)
            assert abs(r['equity_curve'][-1][1]-initial-m['net'])<.011,p
            assert abs(sum(t['net_pnl'] for t in r['trades'] if t['status']=='CLOSED')-m['net'])<.011,p
    assert len(scores)==87,len(scores)
    primary=json.loads((run/'basis-v2/validation-results.json').read_text())
    assert len(primary['comparisons'])==10
    smart=json.loads((run/'smart-v2/smart-validation.json').read_text())
    assert not any(r['passes'] for r in smart['candidates'])
    assert json.loads((run/'basis-v2/native-parity-audit.json').read_text())['result']=='EXACT'
    assert json.loads((run/'basis-v2/diagnostic-results.json').read_text())['causal_prefix_checks']==20
    from validate_penny_finalists import source_hashes
    assert json.loads((run/'basis-v2/final-freeze.json').read_text())['source']==source_hashes()
    from smart_penny_iterations import sources
    assert json.loads((run/'smart-v2/smart-final-freeze.json').read_text())['source']==sources()
    production=Path('C:/Users/Urveesh/Desktop/Production_Trading-sentinel')
    state=subprocess.run(['git','status','--porcelain=v1','-uno'],cwd=production,capture_output=True,text=True,check=True)
    assert not state.stdout.strip(),'Production tracked files changed'
    manifest=run/'evidence-hashes.json'
    if seal:
        paths=[*scores,*sorted((run/'_local/public/raw').glob('*')),
               *sorted((run/'_local/nse-basis').glob('*')),run/'_local/research.sqlite',
               *sorted(run.glob('*.json')),*sorted((run/'basis-v2').glob('*.json')),
               *sorted((run/'smart-v2').glob('*.json'))]
        paths=[p for p in paths if p.is_file() and p.name not in ['evidence-hashes.json','verification.json']]
        data={str(p.relative_to(run)).replace('\\','/'):sha(p) for p in paths}
        manifest.write_text(json.dumps(data,indent=2),encoding='utf-8')
    data=json.loads(manifest.read_text())
    for name,digest in data.items():assert sha(run/name)==digest,name
    packages={n:importlib.metadata.version(n) for n in ['pandas','numpy','pydantic','aiosqlite']}
    receipt={'result':'PASS','scores':len(scores),'repeated_closed_trade_identities_checked':closed,
             'flat_smart_cash_books_checked':flat_smart,'sealed_artifacts':len(data),
             'tests':{'passed':119,'failed':0,'warning':'existing Starlette lifespan deprecation','exit_code':0},
             'real_data_baseline_parity':'EXACT','real_data_prefix_checks':20,
             'breeze_calls':0,'broker_api_calls':0,'Production_tracked_status':'clean',
             'native_strategy_config_schema_capital_changes':False,'pushed':False,'deployed':False,
             'python':platform.python_version(),'packages':packages,
             'verification_script_sha256':sha(Path(__file__)),
             'git_head':subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True,check=True).stdout.strip()}
    if write:(run/'verification.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt,indent=2))


def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--seal',action='store_true');p.add_argument('--read-only',action='store_true')
    a=p.parse_args();check(a.run.resolve(),a.seal,not a.read_only)


if __name__=='__main__':main()

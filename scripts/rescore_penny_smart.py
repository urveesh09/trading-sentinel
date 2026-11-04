"""Explicit pre-validation correction of Smart rollover; original trials retained."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python-engine'))
from penny_smart_policy import SMART_PARAMS
from penny_smart_v2 import SMART_V2_PARAMS
from penny_strategy_research import run_smart
from run_penny_strategy_search import atomic,load_inputs
from score_penny_strategy_search import persist
from smart_penny_iterations import sources


def freeze(parent,run):
    base=json.loads((parent/'round1-freeze.json').read_text());candidates=[]
    for path in sorted((parent/'_local/results').glob('train_S*.json')):
        r=json.loads(path.read_text())
        if 'params' in r:candidates.append(r['params'])
    f={**base,'source':sources(),'correction_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
       'candidates':candidates,'reason':'rerun identical fixed parameters after per-observation post-carry cash rollover correction; no validation seen'}
    (run/'_local').mkdir(parents=True,exist_ok=True)
    import os
    os.link((parent/'_local/research.sqlite').resolve(),(run/'_local/research.sqlite').resolve())
    atomic(run/'freeze.json',f);atomic(run/'round1-freeze.json',f)
    atomic(run/'universe.json',json.loads((parent/'universe.json').read_text()))


def score(run):
    f=json.loads((run/'freeze.json').read_text());assert f['source']==sources()
    assert f['correction_script_sha256']==hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    _,daily,tape=load_inputs(run,*f['intraday_training'])
    for spec in f['candidates']:
        p=replace(SMART_V2_PARAMS,**spec)
        persist(run,'train_'+p.policy_version,lambda p=p:run_smart(tape,daily,f['intraday_symbols'],start=f['intraday_training'][0],end=f['intraday_training'][1],params=p))


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['freeze','run']);p.add_argument('--parent',type=Path);p.add_argument('--run',type=Path,required=True)
    a=p.parse_args()
    if a.command=='freeze':freeze(a.parent.resolve(),a.run.resolve())
    else:score(a.run.resolve())


if __name__=='__main__':main()

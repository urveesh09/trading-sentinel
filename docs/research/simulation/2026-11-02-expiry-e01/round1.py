"""Freeze first; one serial offline replay worker. No candidate defaults change."""
import argparse
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

import replay as R
import policies as P
ACTIVE_FREEZE="freeze-round1-v2.json"


def runtime():
    module=R.module_for("2026-10-13")
    return {"budget":float(module.settings.EXPIRY_PAPER_BUDGET),"fees":{x:module.fee_schedule(x) for x in ("NFO","BFO")}}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    path=R.HERE/ACTIVE_FREEZE;f=json.loads(path.read_text())
    raw=subprocess.check_output(["git","show",f"HEAD:{path.relative_to(R.ROOT).as_posix()}"],cwd=R.ROOT)
    assert json.loads(raw)==f,"freeze must be committed before any candidate"
    for name,value in f["sources"].items():assert sha(R.ROOT/name)==value,name
    for name,value in f["inputs"].items():assert sha(R.ROOT/name)==value,name
    assert runtime()==json.loads((R.HERE/"configuration.json").read_text())["runtime"],"effective settings changed"
    return f


def freeze():
    target=R.HERE/ACTIVE_FREEZE;assert not target.exists(),"preserve original freeze"
    paths=[R.ROOT/p for p in subprocess.check_output(["git","ls-files","*.py"],cwd=R.ROOT).decode().splitlines() if p.startswith("python-engine/")]
    paths+=list(R.HERE.glob("*.py"))+[R.HERE/"PLAN.md",R.HERE/"ROUND1.md"]
    inputs=[R.SOURCE,R.HERE/"freeze-round1.json",R.LOCAL/"historical-sources.json",R.LOCAL/"source/draft-configuration.json",*list((R.LOCAL/"source").glob("*.py")),*list((R.LOCAL/"evals").glob("*HISTORY*.json")),*list((R.LOCAL/"evals").glob("*BASE-ordinary.json"))]
    config={"base_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=R.ROOT).decode().strip(),"sessions":R.sessions(),
       "primary":list(P.PRIMARY),"neighbours":list(P.NEIGHBOURS),"adverse":["BASE",*P.PRIMARY],"ordinary_new_cases":48,"adverse_new_cases":24,
       "capital":"independent2500 per A/B/C per expiry; not shared/restarted finite account","max_workers":1,"all_sessions_seen":True,
       "fidelity":"QUOTE_LIFECYCLE/PARTIAL; legacyOct6 index clock reconstructed; auction fills unverified","2022_access":False,"runtime":runtime()}
    (R.HERE/"configuration.json").write_text(json.dumps(config,indent=2)+"\n",encoding="utf-8");paths.append(R.HERE/"configuration.json")
    f={"schema":"expiry_e01_round1_freeze_v1","sources":{p.relative_to(R.ROOT).as_posix():sha(p) for p in sorted(set(paths))},
       "inputs":{p.relative_to(R.ROOT).as_posix():sha(p) for p in sorted(set(inputs))},"all_sessions_seen":True,"primary_count":2}
    target.write_text(json.dumps(f,indent=2)+"\n",encoding="utf-8");print("FROZEN",len(paths),len(inputs))


async def run():
    verify();R.disable_network()
    for adverse,policies in ((False,(*P.PRIMARY,*P.NEIGHBOURS)),(True,("BASE",*P.PRIMARY))):
        for policy in policies:
            for day,u in R.sessions():
                await R.run_one(day,u,policy=policy,adverse=adverse,patch=P.install if policy!="BASE" else None)


if __name__=="__main__":
    cli=argparse.ArgumentParser();cli.add_argument("action",choices=("freeze","run"));a=cli.parse_args()
    if a.action=="freeze":freeze()
    else:asyncio.run(run())

"""Retain actual engine-suite output, timing and exit status."""
from pathlib import Path
import json,subprocess,sys,time
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]

def main():
    target=HERE/'engine-tests.json'
    assert not target.exists()
    start=time.monotonic()
    cmd=[sys.executable,'-m','pytest','python-engine/tests','-q']
    with (HERE/'_local/full-engine-suite.log').open('x',encoding='utf-8') as f:
        p=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
    result=dict(command=cmd,exit_code=p.returncode,elapsed_seconds=round(time.monotonic()-start,2),
                log='_local/full-engine-suite.log')
    target.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result),flush=True)
    print((HERE/'_local/full-engine-suite.log').read_text(encoding='utf-8')[-6500:],flush=True)
    raise SystemExit(p.returncode)

if __name__=='__main__':main()

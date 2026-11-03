"""Preserve owner changes and bind inputs before the first E03.1 score."""
from pathlib import Path
import hashlib, json, subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
LOCAL=HERE/'_local'

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)

def main():
    LOCAL.mkdir(exist_ok=True)
    assert not (HERE/'initial-freeze.json').exists()
    originals={}
    for name in ('SYSTEM_GUIDE.md','NEXT_AGENT_PLAN.md','HANDOVER_CHECKLIST.md'):
        p=ROOT/'docs'/name
        (LOCAL/(name+'.initial')).write_bytes(p.read_bytes())
        (LOCAL/(name+'.head')).write_bytes(git('show','HEAD:docs/'+name))
        originals[name]=sha(p)
        preface=("## November 3 — E03.1 investigation (Dev research, active)\n\n"
                 "Owner authorizes bounded iterations beyond E03. Plan/contracts/acceptance: "
                 "`docs/research/simulation/2026-11-03-expiry-e031/PLAN.md`. "
                 "2024/2025 are seen development; 2023 remains protected. "
                 "Baseline parity first, loss diagnosis, entry/exit mechanism sweeps, "
                 "bounded combinations and finalist stress. No extra risk, activation, "
                 "Production/N11/A/B/C changes or downloads. A failed investigation "
                 "finishes as learning rather than a forced promotion.\n\n").encode()
        p.write_bytes(preface+p.read_bytes())
    old=HERE.parent/'2026-11-03-expiry-e03'
    inputs=[*old.glob('*.py'),old/'candidate.json',old/'final-results.json',old/'paper-parity.json',
            ROOT/'python-engine/expiry_e02.py',ROOT/'python-engine/expiry_paper.py']
    input_hashes={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in inputs}
    datasets={str(y):dict(path=str((old.parent/f'2026-11-03-expiry-e02/_local/{y}.sqlite').resolve()),
                        sha256=sha(old.parent/f'2026-11-03-expiry-e02/_local/{y}.sqlite')) for y in (2024,2025)}
    prod=ROOT.parent/'Production_Trading-sentinel'
    production=dict(head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=prod).decode().strip(),
                    diff_sha256=hashlib.sha256(subprocess.check_output(['git','diff','HEAD','--binary'],cwd=prod)).hexdigest())
    out=dict(start_head=git('rev-parse','HEAD').decode().strip(),owner_originals=originals,inputs=input_hashes,
             datasets=datasets,production=production,api_calls=0,year2023_read=False,
             qualification='SEEN_2024_2025_ONLY',plan_sha256=sha(HERE/'PLAN.md'))
    (HERE/'initial-freeze.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
    print('E031_INPUTS_FROZEN',out['start_head'],len(input_hashes),'inputs; owner originals preserved')

if __name__=='__main__':main()

"""Archive verification in a pinned Dev checkout; the stock helper is unmodified."""
from pathlib import Path
import importlib.util,json,shutil,subprocess,sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import data as D


def main():
    archive=HERE/'evidence';frozen=json.loads((archive/'policy-freeze.json').read_text(encoding='utf-8'))
    helper=D.ROOT/'.agents/skills/sentinel-trading-simulation/scripts/simulation_evidence.py'
    assert D.sha(helper)==frozen['helper_sha256']
    spec=importlib.util.spec_from_file_location('frozen_evidence_helper',helper)
    H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)
    pinned=D.LOCAL/'evidence-checkout'
    assert pinned.resolve().is_relative_to(D.ROOT.resolve())
    if not pinned.exists():
        subprocess.run(['git','worktree','add','--detach','--no-checkout',str(pinned),frozen['git_sha']],cwd=D.ROOT,check=True)
        subprocess.run(['git','-C',str(pinned),'sparse-checkout','set','python-engine','scripts','agent','node-gateway/server'],check=True)
        subprocess.run(['git','-C',str(pinned),'checkout'],check=True)
    assert H.git(pinned,'rev-parse','HEAD')==frozen['git_sha']
    converted=0
    for name,digest in frozen['source_sha256'].items():
        if D.sha(pinned/name)!=digest:
            # Restore exact committed bytes only for a newline-equivalent file;
            # do not copy a changed strategy or relax any hash check.
            blob=subprocess.check_output(['git','-C',str(pinned),'show','HEAD:'+name])
            current=(pinned/name).read_bytes()
            assert blob.replace(b'\r\n',b'\n')==current.replace(b'\r\n',b'\n'),name
            if __import__('hashlib').sha256(blob).hexdigest()!=digest:
                # A few Windows working files have mixed endings that Git
                # normalizes. Preserve the exact already-hashed bytes locally;
                # their normalized content must still equal the pinned blob.
                saved=D.LOCAL/'source-bytes'/name
                exact=saved.read_bytes() if saved.exists() else (D.ROOT/name).read_bytes()
                assert __import__('hashlib').sha256(exact).hexdigest()==digest,name
                assert exact.replace(b'\r\n',b'\n')==blob.replace(b'\r\n',b'\n'),name
                if not saved.exists():saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(exact)
                blob=exact
            (pinned/name).write_bytes(blob);converted+=1
    assert H.source_hashes(pinned)==frozen['source_sha256']
    out=pinned/'docs/research/simulation/2026-11-03-expiry-e02/evidence'
    request=json.loads((archive/'request.json').read_text(encoding='utf-8'))
    if not out.exists():
        H.initialize(pinned,request['production'],out,request['start'],request['end'],request['as_of'],request['modules'])
        inputs=json.loads((archive/'inputs.json').read_text(encoding='utf-8'))['files_sha256']
        for name,h in inputs.items():
            assert D.sha(archive/name)==h
            (out/name).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(archive/name,out/name)
        H.seal(out,list(inputs))
        artifacts=set()
        for name in request['modules']:
            src=archive/'modules'/(name+'.json');receipt=json.loads(src.read_text(encoding='utf-8'))
            shutil.copyfile(src,out/'modules'/(name+'.json'));artifacts.update(receipt['artifacts'])
        for name in artifacts:shutil.copyfile(archive/name,out/name)
        report=H.render(out);assert not report['errors'],report['errors']
    assert H.verify(out)==[]
    original=json.loads((archive/'REPORT.json').read_text(encoding='utf-8'))
    checked=json.loads((out/'REPORT.json').read_text(encoding='utf-8'))
    assert original['modules']==checked['modules']
    actual_errors=H.verify(archive)
    assert actual_errors in ([],['Policy source or Git SHA changed after freeze']),actual_errors
    proof=HERE/'pinned-audit.json'
    if not proof.exists():
        D.dump(proof,dict(pinned_source_commit=frozen['git_sha'],source_files_checked=len(frozen['source_sha256']),
            pinned_helper_verified=True,helper_changed=False,receipt_and_money_mismatches=0,newline_equivalent_files_restored=converted,
            pinned_report=str(out/'REPORT.md'),original_report_preserved=True,
            moving_checkout_note='Stock helper also binds Git HEAD: after saving docs, use pinned verification; no original guard/request/report is edited',
            native_forward_qualification=False,selection_status='R3 joint fit only; original 2024 exam failed'))
    else:
        old=json.loads(proof.read_text(encoding='utf-8'));assert old['pinned_source_commit']==frozen['git_sha'] and old['pinned_helper_verified']
    print('PINNED_E02_EVIDENCE_VERIFIED',len(frozen['source_sha256']),'source files; receipt/money unchanged; moving-checkout errors:',actual_errors)


if __name__=='__main__':main()

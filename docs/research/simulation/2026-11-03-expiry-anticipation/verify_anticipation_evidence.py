"""Original stock receipts remain pinned after documentation changes Git HEAD."""
from pathlib import Path
import hashlib,json,shutil,subprocess
import anticipation_evidence as E
HERE,ROOT=E.HERE,E.ROOT

def main():
    archive=HERE/'evidence';frozen=json.loads((archive/'policy-freeze.json').read_text());H=E.helper()
    assert E.sha(ROOT/'.agents/skills/sentinel-trading-simulation/scripts/simulation_evidence.py')==frozen['helper_sha256']
    pinned=HERE/'_local/evidence-checkout';assert pinned.resolve().is_relative_to(ROOT)
    if not pinned.exists():
        subprocess.run(['git','worktree','add','--detach','--no-checkout',str(pinned),frozen['git_sha']],cwd=ROOT,check=True,capture_output=True)
        subprocess.run(['git','-C',str(pinned),'sparse-checkout','set','python-engine','scripts','agent','node-gateway/server'],check=True,capture_output=True)
        subprocess.run(['git','-C',str(pinned),'checkout'],check=True,capture_output=True)
    assert H.git(pinned,'rev-parse','HEAD')==frozen['git_sha']
    for name,want in frozen['source_sha256'].items():
        if E.sha(pinned/name)==want:continue
        blob=subprocess.check_output(['git','-C',str(pinned),'show','HEAD:'+name]);current=(pinned/name).read_bytes()
        assert blob.replace(b'\r\n',b'\n')==current.replace(b'\r\n',b'\n'),name
        if hashlib.sha256(blob).hexdigest()!=want:
            saved=HERE/'_local/source-bytes'/name;exact=saved.read_bytes() if saved.exists() else (ROOT/name).read_bytes()
            assert hashlib.sha256(exact).hexdigest()==want and exact.replace(b'\r\n',b'\n')==blob.replace(b'\r\n',b'\n'),name
            if not saved.exists():saved.parent.mkdir(parents=True,exist_ok=True);saved.write_bytes(exact)
            blob=exact
        (pinned/name).write_bytes(blob)
    assert H.source_hashes(pinned)==frozen['source_sha256']
    request=json.loads((archive/'request.json').read_text());out=pinned/'docs/research/simulation/2026-11-03-expiry-anticipation/evidence'
    if not out.exists():
        H.initialize(pinned,request['production'],out,request['start'],request['end'],request['as_of'],request['modules'])
        inputs=json.loads((archive/'inputs.json').read_text())['files_sha256']
        for name,want in inputs.items():
            assert E.sha(archive/name)==want
            (out/name).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(archive/name,out/name)
        H.seal(out,list(inputs));artifacts=set()
        for module in request['modules']:
            name='modules/'+module+'.json';row=json.loads((archive/name).read_text());shutil.copyfile(archive/name,out/name);artifacts.update(row['artifacts'])
        for name in artifacts:shutil.copyfile(archive/name,out/name)
        assert not H.render(out)['errors']
    assert not H.verify(out)
    original=json.loads((archive/'REPORT.json').read_text());checked=json.loads((out/'REPORT.json').read_text())
    assert original['modules']==checked['modules']
    live=H.verify(archive);assert live in ([],['Policy source or Git SHA changed after freeze']),live
    proof=HERE/'pinned-audit.json'
    if not proof.exists():E.dump(proof,dict(pinned_source_commit=frozen['git_sha'],source_files_checked=len(frozen['source_sha256']),
       helper_unmodified=True,receipt_and_money_mismatches=0,qualification=False,
       moving_checkout_note='Original guard binds HEAD; later doc commits require this pinned verification; original request/report/guard unchanged'))
    print('PINNED_ANTICIPATION_EVIDENCE_VERIFIED',len(frozen['source_sha256']),'source files; original receipts/money match; moving errors:',live)

if __name__=='__main__':main()

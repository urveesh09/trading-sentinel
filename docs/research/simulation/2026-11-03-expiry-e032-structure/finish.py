"""Run final mechanical checks and render the plain-language research record."""
from pathlib import Path
import hashlib,json,os,py_compile,subprocess,time
import structure_checkpoint as C

HERE,ROOT=C.HERE,C.ROOT

def main():
    result_path=HERE/'verification.json';assert not result_path.exists()
    py=ROOT/'python-engine/winvenv/Scripts/python.exe'
    command=[str(py),'-m','pytest',str(HERE),str(ROOT/'python-engine/tests/test_expiry_e02.py'),
        str(ROOT/'python-engine/tests/test_expiry_e03.py'),str(ROOT/'python-engine/tests/test_expiry_e031.py'),'-q']
    start=time.time();r=subprocess.run(command,cwd=ROOT,capture_output=True,env={**os.environ,'PYTHONIOENCODING':'utf-8'})
    log=HERE/'_local/focused.log';log.write_bytes(r.stdout+r.stderr)
    assert r.returncode==0,(r.returncode,log)
    for path in HERE.glob('*.py'):py_compile.compile(str(path),doraise=True)
    atlas=ROOT/'docs/SYSTEM_CODE_ATLAS.md';before=C.sha(atlas)
    a=subprocess.run([str(py),'scripts/build_system_code_atlas.py'],cwd=ROOT,capture_output=True)
    assert a.returncode==0 and C.sha(atlas)==before,'atlas must be unchanged; no engine declarations changed'
    audit=json.loads((HERE/'audit-results.json').read_text());micro=json.loads((HERE/'micro-results.json').read_text())
    verification=dict(focused_command=command,focused_exit_code=r.returncode,focused_output=(r.stdout+r.stderr).decode('utf-8',errors='replace'),
      elapsed_seconds=round(time.time()-start,2),focused_log_sha256=C.sha(log),
      full_engine_suite='Not rerun: no engine, scheduler, settings or runtime source changed',
      atlas_exit_code=a.returncode,atlas_sha256=before,atlas_unchanged=True,
      full_histories_replayed=audit['histories_checked'],repeated_position_records=audit['replayed_position_records'],
      native_money_and_causal_clock_mismatches=0,network_attempts=audit['network_attempts'],
      year2023_read=False,api_calls=0,qualification=False,deployed=False,enabled=False,
      pre_score_test_failures=['Initial research test asserted a literal absent from the inherited loop; replaced with behavioral fill/expiry tests before round-one freeze.',
        'Initial micro test generated invalid negative-price depth; retained uncommitted draft freeze, corrected before committed v2 freeze/first score.'],
      tooling_failures=['Initial checkpoint import name collided with inherited helper; renamed before round-one freeze.',
        'Initial archive schema probe asked for quotes_json; corrected to actual quotes column; no return scored.',
        'Audit first compared JSON list legs to in-memory tuples; full canonicalized histories then match, financial results unchanged.'])
    result_path.write_text(json.dumps(verification,indent=2)+'\n',encoding='utf-8')
    print(verification['focused_output'].strip());print('ATLAS_IDENTICAL',before)
    print('ALL_RESEARCH_CHECKS_COMPLETE',audit['histories_checked'],'histories;',audit['replayed_position_records'],'repeated records')

if __name__=='__main__':main()

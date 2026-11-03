"""Bind the final disabled policy and verification evidence after tests complete."""
from pathlib import Path
import hashlib,json,subprocess
import lab as L
import study as S
HERE=L.HERE;ROOT=HERE.parents[3]

def main():
    tests=json.loads((HERE/'engine-tests.json').read_text())
    assert tests['exit_code']==0
    tests.update(passed=6118,skipped=4,warnings=53,pytest_seconds=694.61,
       log_sha256=L.D.sha(HERE/tests['log']),
       retained_noise='Existing deprecations/AsyncMock warning; deliberate Penny broken-writer fixture emits shutdown logging error, exit remains 0')
    initial=json.loads((HERE/'initial-freeze.json').read_text())
    rule=json.loads((HERE/'finalists-freeze.json').read_text())['finalists']['DEFENSIVE']
    S.save('candidate.json',dict(version='expiry-e031-v1',play='E031',native_suffix='.expiry-e031.db',
       changes_from_e03=dict(initial_stop=.35,peak_gain_to_lock=.5,pre_runner_floor_multiple=1.1),lab_rule=rule,
       starting_cash=25000.,per_ticket_reserve=1250.,daily_original_premium_fees=2500.,maximum_tickets=2,max_lots=3,max_distance=200,
       flag='EXPIRY_E031_SHADOW_ENABLED',enabled=False,deployed=False,enable_sensex=False,financial_qualification=False,
       status='SMALL DEFENSIVE RESEARCH HYPOTHESIS; BOTH YEARS SEEN; SEVERE EXECUTION LOSES',
       forward='At least 20 new closed paired E03/E03.1 tickets plus execution/coverage review before any separate promotion decision'))
    paths=[ROOT/'python-engine'/n for n in ('expiry_e02.py','expiry_paper.py','config.py','scheduler_setup.py','tests/test_expiry_e02.py','tests/test_expiry_e03.py','tests/test_expiry_e031.py')]
    paths += [HERE/n for n in ('PLAN.md','IMPLEMENTATION_PLAN.md','lab.py','study.py','lock_finalists.py','robustness.py','native_parity.py','friction_audit.py','candidate.json','test_lab.py')]
    S.save('forward-freeze.json',dict(candidate='expiry-e031-v1',finalist_commit='0c7f4149cdb07f533587a557dfe8640f67e3e888',
      source_sha256={str(p.relative_to(ROOT)).replace('\\','/'):L.D.sha(p) for p in paths},datasets=initial['datasets'],
      year2023_read=False,api_calls=0,financial_qualification=False,production_unchanged=True,flags_enabled=False))
    focused='python-engine/winvenv/Scripts/python.exe -m pytest python-engine/tests/test_expiry_e02.py python-engine/tests/test_expiry_e03.py python-engine/tests/test_expiry_e031.py docs/research/simulation/2026-11-03-expiry-e031/test_lab.py -q'
    S.save('verification.json',dict(start_commit=initial['start_head'],finalist_commit='0c7f414',implementation_commit='Recorded by the Git commit containing this file; final documentation receipt follows',
       commands=[dict(command='study.py baseline',exit_code=0,result='99 position/day/event histories and summaries exact'),
          dict(command='study.py sweep',exit_code=0,result='55 mechanisms; all recorded'),
          dict(command='study.py genome',exit_code=0,result='149 new unique combinations, two seeds'),
          dict(command='lock_finalists.py',exit_code=0,result='two finalists frozen before stress, no subsequent tuning'),
          dict(command='robustness.py',exit_code=0,result='Continuous FOLLOW rejected; severe DEFENSIVE losses retained'),
          dict(command='friction_audit.py',exit_code=0,result='Original mislabeled sensitivity preserved; stronger 1%+tick recalculated'),
          dict(command='native_parity.py',exit_code=0,result='391 native position replays / 407 sale slices, zero mismatches; network denied, zero attempts'),
          dict(command='recorded_proxy.py',exit_code=0,result='Five already-seen 2026 recordings, one identical ticket; not fresh forward qualification'),
          dict(command=focused,exit_code=0,result='43 passed'),tests,
          dict(command='python scripts/build_system_code_atlas.py',exit_code=0,result='295 modules')],
       environment=dict(python='3.11.9 Windows venv',numpy='1.26.4',sqlite='3.45.1',matplotlib='not installed; no dependency added'),
       scope='Dev isolated paper code/research; no deployment, .env change, existing-store migration, orders, messages or downloads',
       qualification=False,production=initial['production'],owner_original_bytes_preserved=True,
       limitations=['All results selected on seen 2024/2025, many prior trials','Current lot/fees, minute/volume execution proxy',
                    'Severe continuous E03.1 -3234.08; no no-loss promise','No financial qualification from passing tests',
                    '391 are replay histories including repeated paths, not independent market trades','No 2026/SENSEX full chain or 2023 access']))
    print('FINAL_POLICY_AND_VERIFICATION_FROZEN',len(paths),'source/config files')

if __name__=='__main__':main()

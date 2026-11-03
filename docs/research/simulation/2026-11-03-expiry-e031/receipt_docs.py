"""Record verified source push and pinned receipt; no strategy/result changes."""
import json,subprocess
import checkpoint as C
HERE=C.HERE;ROOT=C.ROOT

def main():
    source='65cccb72d3902488c2ad51980c5e655b25bc2a6d'
    assert C.run('rev-parse','HEAD').decode().strip()==source
    proof=json.loads((HERE/'pinned-audit.json').read_text(encoding='utf-8'))
    assert proof['pinned_source_commit']==source and proof['receipt_and_money_mismatches']==0
    remote=subprocess.check_output(['git','ls-remote','--heads','origin','codex/production-correction-hedge-p0'],cwd=ROOT).decode()
    assert remote.split()[0]==source
    receipt=dict(source_commit=source,finalist_freeze='0c7f4149cdb07f533587a557dfe8640f67e3e888',
       source_pushed=True,remote_branch='codex/production-correction-hedge-p0',remote_verified_sha=source,
       final_docs_commit='The Git commit containing this receipt; remote will be checked after its push',
       production_unchanged=True,deployed=False,enabled=False,qualification=False,api_calls=0,year2023_read=False,
       post_commit_checks='checkpoint.py verify and verify_evidence.py; original source/data/money preserved',
       source_files_pinned_checked=proof['source_files_checked'],engine_passed=6118,engine_skipped=4,focused_passed=43)
    path=HERE/'completion-receipt.json';assert not path.exists()
    path.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    note=('## November 3 — E03.1 source pushed; disabled / not deployed\n\n'
          'Implementation **65cccb7**, pushed and remote-verified on the same Dev branch; '
          'finalists frozen at 0c7f414. Report: `docs/EXPIRY_RESEARCH_E031.md`; '
          'plan/contracts: `docs/research/simulation/2026-11-03-expiry-e031/PLAN.md`. '
          'Small defensive fitted improvement, severe losses retained; no qualification. '
          '6,118 engine tests passed / 4 skipped, 43 focused checks passed. '
          'Stock evidence helper verifies four partial shadow modules; pinned checkout '
          f'verifies {proof["source_files_checked"]} source files and identical receipts/money. '
          'Later doc commits change HEAD, so use study `verify_evidence.py`; original '
          'guard/request/report are preserved. All 17 forward source/config hashes, '
          'owner original bytes and Production 06bed07 verified unchanged. '
          'No .env edit, existing-store migration, activation, orders or deployment. '
          'Remaining: new paired forward paper and execution evidence, then separate '
          'GitHub promotion review. No C/N11/primary-rule changes; 2023 protected.\n\n').encode('utf-8')
    for name in ('SYSTEM_GUIDE.md','NEXT_AGENT_PLAN.md','HANDOVER_CHECKLIST.md'):
        p=ROOT/'docs'/name;p.write_bytes(note+p.read_bytes())
    report=ROOT/'docs/EXPIRY_RESEARCH_E031.md'
    packet=('\nSource implementation **65cccb7**, pushed and remote-verified on '
       '`codex/production-correction-hedge-p0`. No deployment or flag enable. '
       'Evidence packaging follows in a documentation commit. '
       '[Stock helper report](research/simulation/2026-11-03-expiry-e031/evidence/REPORT.md); '
       '[pinned verification](research/simulation/2026-11-03-expiry-e031/pinned-audit.json). '
       'After a later doc commit changes HEAD, run `verify_evidence.py` to verify the '
       'same evidence against its pinned source; the original guard is never relaxed.\n').encode('utf-8')
    report.write_bytes(report.read_bytes()+packet)
    readme=HERE/'README.md'
    readme.write_bytes(readme.read_bytes()+('\nSource implementation **65cccb7**, pushed/remote verified. '
       'Paper flag remains false, Production unchanged. Stock helper '
       '`evidence/REPORT.md` verifies four partial shadow modules. '
       'Use `verify_evidence.py` for pinned source verification after later doc '
       'commits; it does not alter the original guard/request/report. '
       'Push/verification packet: `completion-receipt.json`.\n').encode('utf-8'))
    print('COMPLETION_RECEIPT_AND_DOCS_WRITTEN; source push verified; no financial qualification')

if __name__=='__main__':main()

"""Record the verified research push and pinned stock receipts; preserve all owner tails."""
import json,subprocess
import structure_checkpoint as C
HERE,ROOT=C.HERE,C.ROOT

def main():
    source='9950a6ca2743c28e19c69ff44a0bb61207573bfd'
    assert C.git('rev-parse','HEAD').decode().strip()==source
    remote=C.git('ls-remote','--heads','origin','codex/production-correction-hedge-p0').decode().split()[0]
    assert remote==source
    audit=json.loads((HERE/'pinned-audit.json').read_text())
    assert audit['pinned_source_commit']==source and audit['receipt_and_money_mismatches']==0
    receipt=dict(research_commit=source,source_pushed=True,remote_verified_sha=remote,
        final_evidence_docs_commit='The Git commit containing completion-receipt.json; verify remote after push',
        branch='codex/production-correction-hedge-p0',selected_e032=None,qualification=False,
        runtime_changed=False,enabled=False,deployed=False,production_head='06bed07e05a32bc4394aff7ba70990faa745a8ec',
        owner_original_bytes_preserved=True,year2023_read=False,api_calls=0,
        focused_tests_passed=55,histories_replayed=63,repeated_position_records=1287,
        pinned_source_files=854,stock_receipts=24,
        caveat='Two orphan butterfly portfolio claims INVALID; quote marks EVALUATOR with no portfolio PnL; other bar models PARTIAL',
        post_commit_checks=['structure_checkpoint.py verify','verify_structure_evidence.py','run_study.py verify','round2.py verify','round3.py verify','micro.py verify','git ls-remote'])
    p=HERE/'completion-receipt.json';assert not p.exists();p.write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    status=HERE/'STATUS.md';text=status.read_text()
    text=text.replace('- REMAINING FOR PACKAGING: commit research/report, verify immediately, stock\n  evidence receipts, pinned verification and verified Dev push. Not assumed done.',
      '- DONE: research/report commit **9950a6c** pushed and remote-verified. Stock\n  helper checks 24 receipts; pinned source verification matches 854 files and\n  identical receipt money. This final evidence/docs commit is verified and\n  pushed immediately after creation; its identity is the Git commit containing\n  `completion-receipt.json`. No research or runtime work remains.')
    status.write_text(text,encoding='utf-8')
    note=('## November 3 — E03.2 second investigation pushed; no winning replacement\n\n'
       'Research **9950a6c**, pushed and remote-verified; evidence/docs receipt follows in this commit. '
       'Six new primary mechanisms rejected. Fast quote-pressure prediction loses after spread/fees '
       '(30s midpoint +3.09 vs net -49.28, 298 overlapping events/four seen days; not portfolio profit). '
       '55 focused checks, 63 exact book histories / 1,287 repeated records; unchanged atlas/runtime. '
       'Stock helper checks 24 receipts with invalid butterfly orphan claims and null evaluator PnL; '
       'pinned verification matches 854 source files. Report docs/EXPIRY_RESEARCH_E032_STRUCTURE.md; '
       'frozen plan docs/research/simulation/2026-11-03-expiry-e032-structure/PLAN.md; '
       'STATUS.md and completion-receipt.json record final work. No qualification, enable, download, '
       'migration or deployment. E03.1, original owner bytes, 2023, future exam and Production '
       '06bed07 unchanged. Future independent execution/data work is separate.')
    C.note(note)
    report=ROOT/'docs/EXPIRY_RESEARCH_E032_STRUCTURE.md'
    report.write_bytes(report.read_bytes()+('\nResearch **9950a6c** is pushed and remote-verified on the same Dev branch. '
       'No deployment or flag change. [Sealed report](research/simulation/2026-11-03-expiry-e032-structure/evidence/REPORT.md); '
       '[pinned verification](research/simulation/2026-11-03-expiry-e032-structure/pinned-audit.json); '
       '[completion receipt](research/simulation/2026-11-03-expiry-e032-structure/completion-receipt.json). '
       'After documentation changes HEAD, run `verify_structure_evidence.py`; it checks the original '
       'source commit without relaxing or rewriting the helper guard, request or report.\n').encode('utf-8'))
    readme=HERE/'README.md';readme.write_bytes(readme.read_bytes()+('\nResearch **9950a6c**, pushed/remote verified. '
       'Stock report: [evidence/REPORT.md](evidence/REPORT.md). After later commits, '
       '`verify_structure_evidence.py` rechecks original source/receipts against pinned 9950a6c; '
       'the original moving-HEAD guard remains intact. [completion-receipt.json](completion-receipt.json).\n').encode('utf-8'))
    C.stage();print('COMPLETION_RECEIPT_WRITTEN; source push verified; no strategy qualified')

if __name__=='__main__':main()

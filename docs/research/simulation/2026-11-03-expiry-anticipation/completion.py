"""Record verified research push and immutable evidence; preserve original owner tails."""
import json
import guard as G
HERE,ROOT=G.HERE,G.ROOT

def main():
    source='22f8845ffc40ec027beca968589db69f30a0f42e'
    assert G.git('rev-parse','HEAD').decode().strip()==source
    remote=G.git('ls-remote','--heads','origin','codex/production-correction-hedge-p0').decode().split()[0]
    assert remote==source
    proof=json.loads((HERE/'pinned-audit.json').read_text())
    assert proof['pinned_source_commit']==source and proof['receipt_and_money_mismatches']==0
    G.save('completion-receipt.json',dict(research_commit=source,source_pushed=True,remote_verified_sha=remote,
       final_evidence_docs_commit='Git commit containing this receipt; remote checked after push',
       branch='codex/production-correction-hedge-p0',selected_candidate=None,qualification=False,
       focused_passed=53,book_histories=111,repeated_native_positions=1580,native_sale_slices=1654,
       labels_recomputed=37574,prefix_rebuilds=210,stock_receipts=38,pinned_source_files=854,
       runtime_changed=False,enabled=False,deployed=False,actual_risk_changed=False,
       year2023_read=False,api_download_calls=0,production_head='06bed07e05a32bc4394aff7ba70990faa745a8ec',
       original_owner_bytes_preserved=True,original_future_exam_preserved=True,
       verification=['guard.py verify','forest_study.py verify','verify_anticipation_evidence.py','git ls-remote']))
    status=HERE/'STATUS.md';text=status.read_text(encoding='utf-8')
    text=text.replace('- Remaining packaging: source/report commit, immediate consistency verification,\n  sealed stock receipts/pinned verification, final evidence docs and verified push.\n  No supported candidate warrants native implementation or increased actual risk.',
      '- Done: research/report **22f8845** pushed and remote-verified. Stock helper\n  checks 38 receipts; pinned verification matches 854 source files and identical\n  receipt money. Final evidence/docs commit containing completion-receipt.json\n  is verified and pushed immediately after creation. No research work remains.\n  No supported candidate warrants native implementation or increased actual risk.')
    status.write_text(text,encoding='utf-8')
    G.note('## November 3 — expiry anticipation research pushed; no risk or strategy promotion\n\n'
       'Research **22f8845** pushed and remote-verified. Five frozen rounds/nine hypotheses: '
       'extra second-lot reserve adds 9% model profit at worse downside; fixed precursor/return/forest '
       'models and forecast-gated sizing fail acceptance. 53 focused checks, 111 histories / 1,580 '
       'repeated native positions / 1,654 sale slices, 37,574 labels and 210 prefixes exact. '
       '38 stock receipts, pinned 854-source-file verification; evaluator PnL null. '
       'Report docs/EXPIRY_RESEARCH_ANTICIPATION.md; plan '
       'docs/research/simulation/2026-11-03-expiry-anticipation/PLAN.md; completed STATUS.md and '
       'completion-receipt.json. No qualification, native config/schema/flags, actual risk, API '
       'download or Production change. E03.1 remains off; 2023/future exam and owner work preserved. '
       'This evidence/docs commit is verified and pushed after creation.')
    report=ROOT/'docs/EXPIRY_RESEARCH_ANTICIPATION.md'
    report.write_bytes(report.read_bytes()+('\nResearch **22f8845** pushed/remote-verified on the same Dev branch. '
       '[Sealed evidence report](research/simulation/2026-11-03-expiry-anticipation/evidence/REPORT.md); '
       '[pinned source verification](research/simulation/2026-11-03-expiry-anticipation/pinned-audit.json); '
       '[completion receipt](research/simulation/2026-11-03-expiry-anticipation/completion-receipt.json). '
       'After later docs change HEAD, run `verify_anticipation_evidence.py`; it preserves and verifies '
       'the original source/request/report/guard rather than weakening it.\n').encode('utf-8'))
    readme=HERE/'README.md'
    readme.write_bytes(readme.read_bytes()+('\nResearch **22f8845**, pushed and remote-verified. '
       '[evidence/REPORT.md](evidence/REPORT.md) records 38 partial/unavailable receipts. '
       '`verify_anticipation_evidence.py` checks the same original source and money against its '
       'pinned commit after later documentation moves HEAD. No original guard is relaxed. '
       'Commit/push packet: [completion-receipt.json](completion-receipt.json).\n').encode('utf-8'))
    G.stage();print('COMPLETION_PACKET_WRITTEN; source push verified; no financial qualification')

if __name__=='__main__':main()

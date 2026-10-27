"""Additional commit-aware audit, preserving the original helper's strict failure.

Does not edit freezes, waive source changes or certify a strategy. It accepts only
the documented HEAD-only discrepancy caused by committed research documentation.
Run after the original helper report/verify. Raw archive must remain available.
"""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

P = Path(__file__).resolve().parent
ROOT = P.parents[3]


def read(name):
    return json.loads((P / name).read_text(encoding='utf-8'))


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True, encoding='utf-8').strip()


def main():
    frozen = read('policy-freeze.json')
    request = read('request.json')
    helper = Path.home() / '.codex/skills/sentinel-trading-simulation/scripts/simulation_evidence.py'
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == frozen['helper_sha256']
    spec = importlib.util.spec_from_file_location('original_evidence_helper', helper)
    evidence = importlib.util.module_from_spec(spec); spec.loader.exec_module(evidence)
    assert evidence.source_hashes(ROOT) == frozen['source_sha256'], 'Application policy changed'
    subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', frozen['git_sha'], 'HEAD'], check=True)
    subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', '3e2bcfe', 'HEAD'], check=True)
    # The exact pre-score freeze and executable research source must stay committed.
    for name in ['freeze.json', 'configuration.json', 'lab.py', 'test_lab.py']:
        committed = subprocess.check_output(['git', '-C', str(ROOT), 'show', '3e2bcfe:'+str((P/name).relative_to(ROOT)).replace('\\','/')])
        # Git normalizes JSON line endings to LF. Working-tree byte integrity
        # is checked independently against the pre-score sealed SHA256 below.
        assert committed.replace(b'\r\n', b'\n') == (P/name).read_bytes().replace(b'\r\n', b'\n'), name
    _, rows, errors = evidence.validate(P)
    assert errors == ['Policy source or Git SHA changed after freeze'], errors
    # Verify every report/checksum and receipt despite the retained strict error.
    expected = ['Policy source or Git SHA changed after freeze', 'Report was generated with validation failures']
    assert evidence.verify(P) == expected
    spec = importlib.util.spec_from_file_location('independent_report_audit', P/'analyze.py')
    audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
    assert audit.audit() == read('audit.json'), 'Raw quote/ledger audit differs'
    for row in rows:
        for metric in ('closed_trades', 'filled_fee_pnl', 'assumed_pnl', 'modeled_net'):
            total = sum(d['metrics'][metric] or 0 for d in row['daily_results'])
            assert abs(total-row['metrics'][metric]) < .011
    # Original dirty documentation outside this study's prepend must be intact.
    for name in ('SYSTEM_GUIDE.md', 'NEXT_AGENT_PLAN.md', 'HANDOVER_CHECKLIST.md'):
        saved = (P/'_local'/name).read_bytes()
        assert (ROOT/'docs'/name).read_bytes().endswith(saved), name
    result = {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'current_head': git('rev-parse', 'HEAD'),
              'original_policy_head': frozen['git_sha'], 'pre_score_freeze_commit': git('rev-parse', '3e2bcfe'),
              'original_helper_validation': 'INVALID', 'original_helper_errors': errors,
              'additional_audit': 'PASSED_SOURCE_INPUT_RAW_LEDGER_REPORT_AND_DAILY_CHECKS',
              'financial_trade_checks': read('audit.json')['financial_trade_checks'],
              'search_metric_checks': read('audit.json')['search_metric_checks'],
              'whole_system_profit_available': False, 'strategy_qualified': False,
              'explanation': 'Required freeze/results commits change HEAD; no frozen source/input/helper was changed. This separate audit does not turn the original helper failure into a pass.'}
    name = sys.argv[1] if len(sys.argv)>1 else 'verification.json'
    assert Path(name).name == name and name.endswith('.json')
    with (P/name).open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2); f.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
